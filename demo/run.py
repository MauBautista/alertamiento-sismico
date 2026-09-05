"""Hito de salida Fase 1 — demo en vivo con 3 gabinetes, con evidencia verificable.

Levanta 3 ``EdgeSupervisor`` reales (un proceso cada uno), el ``SqsConsumer`` real
sobre el spool, y el ``IncidentEngine`` real. Ejecuta los 3 criterios del hito y
FALLA RUIDOSAMENTE si alguno no se cumple:

  C1  prueba SASMEX dispara actuadores y aparece en el SOC
  C2  sismo simulado en 3 estaciones activa quórum
  C3  corte de internet no detiene la protección local
  C4  un simulacro comandado DESDE LA NUBE suena en los gabinetes, y uno forjado no

Lo único sustituido es IoT Core + SQS (ver ``demo/spool.py``). El SOC se observa por
el mismo ``NOTIFY takab_live`` que alimenta al hub WebSocket de la consola: medir ahí
es medir el instante en que el live wall recibe el frame, sin depender de Cognito.

Honestidad de lo que NO demuestra (gate #3 abierto: no hay WR-1, relés, sirena ni
válvula cableados): la actuación es sobre relés MOCK y la latencia medida es la de
la ruta software. El presupuesto físico <100 ms (debounce + interrupción + relé) se
valida con hardware, y esta demo NO lo acredita.

    python demo/run.py            # requiere DB migrada + seed (make demo-fase1)

[T-5.29] C4 necesita además almacén de objetos para el reporte del simulacro
(MinIO local; `make demo-fase1` lo levanta). Si falta, la escena falla diciéndolo
en vez de saltarse el criterio en silencio.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import demo.aislamiento as aislamiento  # noqa: E402
from demo.aislamiento import entregas_reales, imponer  # noqa: E402
from demo.bridge import Bridge, ingest_conn_factory  # noqa: E402
from demo.spool import SpoolCommandPublisher, downlink_dir  # noqa: E402

from takab_api.auth.claims import ALL_SITES, Claims  # noqa: E402
from takab_api.commands.keys import StaticKeyProvider  # noqa: E402
from takab_api.db.session import SessionCtx, get_tenant_conn  # noqa: E402
from takab_api.demo_mode import ventana_viva_sync  # noqa: E402
from takab_api.incident.engine import IncidentEngine  # noqa: E402
from takab_api.routers.drills import drill_report, start_drill  # noqa: E402
from takab_api.schemas.drills import DrillCreateIn  # noqa: E402
from takab_api.settings import Settings  # noqa: E402

DSN = "postgresql://takab:takab_dev@127.0.0.1:5433/takab"
EDGE_PY = _ROOT / "edge" / ".venv" / "bin" / "python"
TENANT_CODE = "tenant-dev"

# Presupuesto de la ruta SOFTWARE del reflejo (los tests del edge exigen <0.05 s).
REFLEX_BUDGET_S = 0.05
# Criterio T-1.22: el frame llega al live wall en <2 s desde el commit.
SOC_BUDGET_S = 2.0

CHANNELS = ("siren", "strobe", "gas_valve", "elevator", "door_retainer")


@dataclass(frozen=True)
class Gab:
    """Un gabinete. Los sitios son los sembrados por ``db/seeds/sim_fleet.sql``."""

    thing: str
    site: str
    station: str
    port: int


# Sitios deliberadamente separados: dos en Puebla y uno en CDMX (~100 km). La
# ventana de asociación es consciente de la distancia (|Δt| ≤ dist/v_P + margen),
# así que un quórum entre ciudades sólo cierra si los arribos son coherentes.
GABINETES = (
    Gab("gw-sim-0001", "site-sim-001", "SIM001", 9101),
    Gab("gw-sim-0002", "site-sim-006", "SIM006", 9102),
    Gab("gw-sim-0003", "site-sim-011", "SIM011", 9103),
)

_ok = 0
_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  \033[32m✅\033[0m {name}")
    else:
        _fail += 1
        print(f"  \033[31m❌\033[0m {name} — {detail}")


def head(title: str) -> None:
    print(f"\n\033[1m=== {title} ===\033[0m")


# --------------------------------------------------------------------------- http
def _post(gab: Gab, path: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{gab.port}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — localhost
        return json.loads(r.read())


def _status(gab: Gab, timeout: float = 10.0) -> dict:
    url = f"http://127.0.0.1:{gab.port}/status"
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 — localhost
        return json.loads(r.read())


# --------------------------------------------------------------------------- db
def _sql(conn: psycopg.Connection, query: str, params: dict | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(query, params or {})
        return cur.fetchall()


_LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _assert_local_db(conn: psycopg.Connection) -> None:
    """El TRUNCATE de la demo jamás debe alcanzar una DB remota (T-1.47).

    ``conn.info.host`` es el host REAL de la conexión (no el DSN de entrada):
    TCP → hostname/IP; socket UNIX → ruta del directorio (local por definición).
    La flota desplegada comparte convención con la demo: un descuido de DSN
    apuntando al EC2 borraría los incidentes reales.
    """
    host = conn.info.host
    if host and not host.startswith("/") and host not in _LOCAL_DB_HOSTS:
        raise RuntimeError(
            f"reset_state: la conexión apunta a '{host}', que no es localhost — "
            "la pizarra limpia TRUNCATEa tablas de datos y NUNCA debe correr "
            "contra una DB remota. Aborto sin tocar nada."
        )


def _assert_exclusive_db(conn: psycopg.Connection) -> None:
    """La acreditación exige la DB para la demo SOLA (lección A-3 de la auditoría).

    Un worker residente — p.ej. el `python -m takab_api.incident` que deja vivo un
    `make soc-local` mal apagado (no escucha en ningún puerto que lo delate) —
    correlaciona y dispara fail-open ANTES de que los asserts intermedios de C2
    consulten: los 3 incidentes amanecen ya linkeados y aparecen sintéticos
    `trigger='quorum'` ⇒ 33 OK · 2 FALLOS deterministas sin pista del porqué.
    Fail-loud: cualquier 'client backend' ajeno conectado a la DB aborta la
    acreditación ANTES de arrancar un solo criterio. Se llama con la PRIMERA
    conexión de la demo, cuando cualquier otro cliente es, por definición, ajeno.
    """
    rows = _sql(
        conn,
        "SELECT pid, usename, coalesce(application_name, ''), state, "
        "left(coalesce(query, ''), 80) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid() "
        "AND backend_type = 'client backend'",
    )
    if rows:
        detalle = "\n".join(
            f"    pid={pid} user={user} app={app!r} state={state} query={query!r}"
            for pid, user, app, state, query in rows
        )
        raise RuntimeError(
            "demo-fase1: la DB tiene OTROS clientes conectados y la acreditación "
            "exige exclusividad — un worker externo correlacionaría por su cuenta y "
            "contaminaría los asserts de C2 (RUNBOOK-auditoria-cierre, hallazgo A-3). "
            "¿Quedó vivo `make soc-local`? Apaga estos procesos y reintenta:\n"
            f"{detalle}"
        )


def reset_state(conn: psycopg.Connection) -> None:
    """Pizarra limpia entre criterios. Sólo tablas de datos, nunca el registro.

    TRUNCATE (no DELETE): `incident_actions` es append-only por trigger.
    """
    _assert_local_db(conn)
    # [T-5.29] `drills`, `drill_sites` y `commands` entran aquí desde la escena
    # del simulacro: sin ellas, el conteo de comandos publicados arrastraría los
    # de la corrida anterior y la guarda de no-vacuidad mediría el histórico.
    conn.execute(
        "TRUNCATE seismic_events, incidents, incident_actions, quorum_votes, "
        "waveform_features_1s, device_health, drills, drill_sites, commands CASCADE"
    )
    conn.commit()


def wait_for(predicate, timeout_s: float = 20.0, step_s: float = 0.2) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return False


# --------------------------------------------------------------------------- soc
class SocListener:
    """Escucha el mismo ``NOTIFY takab_live`` que alimenta al hub WS de la consola."""

    def __init__(self, dsn: str) -> None:
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("LISTEN takab_live")

    def wait_incident(self, timeout_s: float) -> float | None:
        """Segundos hasta el primer NOTIFY de incidente; None si no llegó."""
        start = time.monotonic()
        deadline = start + timeout_s
        while time.monotonic() < deadline:
            for note in self.conn.notifies(timeout=0.2, stop_after=1):
                payload = json.loads(note.payload)
                if payload.get("t") == "incident":
                    return time.monotonic() - start
        return None

    def close(self) -> None:
        self.conn.close()


# --------------------------------------------------------------------------- run
class Fleet:
    """Los 3 gabinetes, cada uno en su proceso.

    Se reinician entre criterios. No es maquillaje: `rules` sólo publica en
    TRANSICIÓN de tier, así que un gabinete que ya está en `evacuate_or_hold` no
    emitiría un `LocalEvent` nuevo ante un segundo sismo. Un gabinete recién
    arrancado es el estado del que parte cada escenario, y además garantiza que
    nadie siga publicando mientras se limpia la pizarra.
    """

    def __init__(self, workroot: Path) -> None:
        self.workroot = workroot
        self.procs: list[subprocess.Popen] = []
        # [T-5.29] Una clave HMAC por gabinete, GENERADA AQUÍ y solo en memoria.
        # Es lo que permite que la nube firme un comando que el dispatcher real
        # del edge acepte. No va a git ni a disco (regla de oro 6): nace con la
        # demo, viaja al hijo por entorno y muere con el proceso.
        self.hmac = {g.thing: secrets.token_hex(32) for g in GABINETES}
        #: Lo que el gabinete declara como DEFAULT de fábrica de `command_enabled`.
        #: Se le pregunta a él porque la clase vive en el venv del edge y el guion
        #: corre en el de la api: afirmarlo desde aquí sería teclearlo.
        self.default_command_enabled: bool | None = None

    def start(self) -> None:
        for gab in GABINETES:
            proc = subprocess.Popen(  # noqa: S603
                [
                    str(EDGE_PY),
                    str(_ROOT / "demo" / "gabinete.py"),
                    "--thing",
                    gab.thing,
                    "--site",
                    gab.site,
                    "--station",
                    gab.station,
                    "--tenant",
                    TENANT_CODE,
                    "--spool",
                    str(self.workroot / "cola" / gab.thing),
                    "--workdir",
                    str(self.workroot / "gab" / gab.thing),
                    "--downlink",
                    str(self.workroot / "bajada"),
                    # De fábrica va APAGADO (regla de oro 8). La escena C4 lo
                    # enciende a propósito y lo declara: sin esto el gabinete
                    # verifica la firma y acusa `rejected`, que es correcto y no
                    # es lo que la escena tiene que enseñar.
                    "--command-enabled",
                    "--control-port",
                    str(gab.port),
                ],
                cwd=str(_ROOT / "edge"),
                stdout=subprocess.PIPE,
                # [T-5.29] La bitácora del gabinete deja de tirarse. Es la única
                # evidencia de un comando RECHAZADO: el dispatcher no acusa a un
                # emisor no autenticado —a propósito, regla de oro 8—, así que
                # sin este archivo «rechazado» y «no llegó» serían indistinguibles.
                stderr=open(self._log(gab.thing), "w"),  # noqa: SIM115
                text=True,
                env={**os.environ, "TAKAB_EDGE_HMAC_KEY": self.hmac[gab.thing]},
            )
            line = proc.stdout.readline()  # bloquea hasta el {"ready": true}
            if '"ready": true' not in line:
                raise SystemExit(f"el gabinete {gab.thing} no arrancó: {line!r}")
            # Con la clave efímera TODO comando de la nube se rechazaría por firma
            # inválida, y el síntoma —«no llegó nada»— apunta al transporte, que
            # es el diagnóstico equivocado. Se comprueba al arrancar, no al fallar.
            if '"hmac": "fijada"' not in line:
                raise SystemExit(f"{gab.thing} arrancó con clave HMAC efímera: {line!r}")
            self.default_command_enabled = json.loads(line).get("command_default")
            self.procs.append(proc)

    def _log(self, thing: str) -> Path:
        d = self.workroot / "log"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{thing}.log"

    def bitacora(self, thing: str) -> str:
        """Lo que el gabinete escribió en su log. `''` si aún no hay nada."""
        ruta = self._log(thing)
        return ruta.read_text(encoding="utf-8", errors="replace") if ruta.exists() else ""

    def stop(self) -> None:
        for proc in self.procs:
            proc.terminate()
        for proc in self.procs:
            proc.wait(timeout=15)
        self.procs.clear()


def escena(fleet: Fleet, bridge: Bridge, conn: psycopg.Connection) -> int:
    """Pizarra limpia y determinista: nadie publicando, cola vacía, DB reseteada.

    Devuelve el contador de la DLQ para medir DELTAS por criterio (los mensajes que
    un criterio manda a la DLQ, no los heredados).
    """
    fleet.stop()  # primero callar a los gabinetes…
    bridge.drain(30.0)  # …luego vaciar la cola: cero ACKs huérfanos
    reset_state(conn)
    fleet.start()
    return bridge.dlq_count


def criterio_1_sasmex(
    conn: psycopg.Connection, bridge: Bridge, soc: SocListener, dlq0: int
) -> None:
    head("C1 · La prueba SASMEX dispara actuadores y aparece en el SOC")
    g1 = GABINETES[0]

    st = _post(g1, "/sasmex")
    reflex = st["reflex_latency_s"]

    check(
        f"reflejo SASMEX→sirena in-process: {reflex * 1000:.3f} ms"
        f" (<{REFLEX_BUDGET_S * 1000:.0f} ms, ruta software)",
        reflex is not None and reflex < REFLEX_BUDGET_S,
        str(reflex),
    )
    check("el contacto queda enclavado (sasmex_active)", st["sasmex_active"] is True)
    check("la sirena suena", st["siren_sounding"] is True)
    activos = [c for c in CHANNELS if st["relays"][c]]
    check(f"secuencia completa: {len(activos)}/5 relés activados", len(activos) == 5, str(activos))

    # Desde que el edge publica hasta que el hub WS despierta. Incluye el poll del
    # puente (≤0.2 s), que en producción es el long-poll de SQS.
    soc_s = soc.wait_incident(10.0)
    check(
        f"el incidente llega al SOC: publish→NOTIFY takab_live en {soc_s * 1000:.0f} ms"
        if soc_s is not None
        else "el incidente llega al SOC (NOTIFY takab_live)",
        soc_s is not None and soc_s < SOC_BUDGET_S,
        "no llegó NOTIFY" if soc_s is None else f"{soc_s:.3f}s",
    )

    check("la cola se vacía (nada atorado)", bridge.drain(), f"quedan {bridge.sqs.pending_count}")
    check("cero mensajes en la DLQ", bridge.dlq_count == dlq0, str(bridge.dlq_count - dlq0))

    rows = _sql(
        conn,
        "SELECT i.severity, i.trigger, s.code FROM incidents i "
        "JOIN sites s USING (site_id) WHERE i.trigger = 'sasmex'",
    )
    check("incidente 'sasmex' en la DB", len(rows) == 1, str(rows))
    if rows:
        sev, trig, site = rows[0]
        check("severidad critical (tier evacuate_or_hold)", sev == "critical", sev)
        check(f"atribuido al sitio del gabinete ({g1.site})", site == g1.site, site)

    kinds = {k for (k,) in _sql(conn, "SELECT DISTINCT kind FROM incident_actions")}
    check(
        "los ACK de actuador quedan como evidencia inmutable (incident_actions)",
        {"siren_on", "gas_closed"} <= kinds,
        str(sorted(kinds)),
    )


def criterio_2_quorum(
    conn: psycopg.Connection, bridge: Bridge, settings: Settings, dlq0: int
) -> None:
    head("C2 · Sismo simulado en 3 estaciones activa el quórum")

    for gab in GABINETES:  # los 3 sienten el mismo sismo, casi a la vez
        _post(gab, "/quake", timeout=60.0)

    check("la cola se vacía", bridge.drain(), f"quedan {bridge.sqs.pending_count}")
    check("cero mensajes en la DLQ", bridge.dlq_count == dlq0, str(bridge.dlq_count - dlq0))

    pend = _sql(
        conn,
        "SELECT s.code FROM incidents i JOIN sites s USING (site_id) "
        "WHERE i.event_id IS NULL ORDER BY s.code",
    )
    sitios = [c for (c,) in pend]
    # La escalada watch→restricted→evacuate comparte `event_id`, así que el handler
    # hace UPSERT: un incidente por sitio, no uno por transición.
    check(
        f"un incidente SIN corroborar por sitio, en 3 sitios distintos: {sitios}",
        len(sitios) == 3 and len(set(sitios)) == 3,
        str(sitios),
    )
    check(
        "disparados por umbral instrumental (no por SASMEX)",
        all(t == "local_threshold" for (t,) in _sql(conn, "SELECT trigger FROM incidents")),
    )

    # El motor REAL de la nube. Una sola pasada de correlación, como en cada wake
    # del worker `python -m takab_api.incident`. `pool.connect` da filas dict, que es
    # lo que el engine espera; y el rol de ingesta (BYPASSRLS) es el suyo en producción.
    ingest_conn = ingest_conn_factory(DSN)
    engine = IncidentEngine(ingest_conn, settings, lookback_s=300.0)
    with ingest_conn() as work:
        engine.run_correlation(work)

    evs = _sql(conn, "SELECT event_id, source, meta FROM seismic_events")
    # `source='local_quorum'` es el único valor que el motor escribe al FORMAR un
    # evento de red; junto con "existe 1 evento" y node_count≥3, distingue un quórum
    # real de "no hubo quórum". No se comprueba por separado (sería tautológico).
    check(
        f"el motor formó UN evento de red por quórum (source={evs[0][1] if evs else '—'},"
        f" node_count={evs[0][2].get('node_count') if evs else '—'})",
        len(evs) == 1 and evs[0][1] == "local_quorum" and evs[0][2].get("node_count", 0) >= 3,
        str(evs),
    )
    if not evs:
        return
    event_id = evs[0][0]

    # `counted` lo cablea el motor a true, así que NO se afirma "todos cuentan"
    # (sería vacío). Lo sustantivo: el motor colapsó a UNA detección por sitio y
    # asoció 3 SENSORES distintos cuyos offsets caben en la ventana distance-aware.
    votes = _sql(
        conn,
        "SELECT se.sensor_id, s.code, v.delta_s FROM quorum_votes v "
        "JOIN sensors se USING (sensor_id) JOIN sites s ON s.site_id = se.site_id "
        "ORDER BY v.delta_s",
    )
    sensores = {sid for sid, _c, _d in votes}
    deltas = sorted(float(d) for _s, _c, d in votes)
    print(f"      offsets por nodo: {[f'{d:+.2f}s' for d in deltas]}")
    check(
        f"{len(votes)} votos, de {len(sensores)} sensores distintos (uno por sitio)",
        len(votes) == 3 and len(sensores) == 3,
        str(votes),
    )
    # 30 s = tope práctico de la ventana (blueprint §4.5). Offsets fuera de rango
    # significarían que el motor asoció detecciones que NO pueden ser el mismo sismo.
    check(
        "los offsets caben en la ventana de asociación (0 ≤ Δt ≤ 30 s):"
        f" {deltas[0]:+.2f}…{deltas[-1]:+.2f}s",
        len(deltas) == 3 and deltas[0] >= 0.0 and deltas[-1] <= 30.0,
        str(deltas),
    )

    linked = _sql(
        conn,
        "SELECT count(*) FROM incidents WHERE event_id = %(e)s AND trigger = 'local_threshold'",
        {"e": event_id},
    )
    check(
        "los 3 incidentes instrumentales quedan linkeados al evento", linked[0][0] == 3, str(linked)
    )

    # Fail-open (T-1.19): al formarse el evento, los sitios EN RANGO sin heartbeat
    # fresco abren un incidente sintético `trigger='quorum'`. Aquí son los sitios sim
    # sin gabinete corriendo: se prefiere sobre-notificar a callar.
    synth = _sql(
        conn,
        "SELECT count(*), min(severity) FROM incidents "
        "WHERE event_id = %(e)s AND trigger = 'quorum'",
        {"e": event_id},
    )
    n_synth, sev_synth = synth[0]
    check(
        f"fail-open: {n_synth} sitios sin enlace en rango abren incidente sintético ({sev_synth})",
        n_synth > 0 and sev_synth == "warning",
        str(synth),
    )


def criterio_3_corte(conn: psycopg.Connection, bridge: Bridge, dlq0: int) -> None:
    head("C3 · El corte de internet NO detiene la protección local")
    g3 = GABINETES[2]

    _post(g3, "/wan/off")
    st = _status(g3)
    check("el enlace con la nube está caído", st["cloud"]["online"] is False)

    enviados_antes = st["cloud"]["sent"]

    # [T-5.08] DOS estímulos, en este orden, y el orden es la mitad del asunto.
    #
    # Este criterio estaba en ROJO desde el 2026-08-03 y nadie lo vio porque
    # `demo/run.py` no entra en `make test`. Lo que pasó: hasta `T-2.32` una
    # detección instrumental de UNA estación accionaba los relés, y el guion lo
    # daba por hecho. La política RATIFICADA invirtió eso —una estación sola
    # AVISA, no actúa (`supervisor.py`: `visual_only = source is THRESHOLD and not
    # instrumental_actuation`, `False` por defecto)—, así que el guion llevaba un
    # mes exigiendo una conducta que el producto abandonó a propósito.
    #
    # 1) INSTRUMENTAL PRIMERO, con los relés en reposo. Si fuera al revés, el
    #    enclave de SASMEX los tendría encendidos y la comprobación no podría
    #    distinguir «actuó el umbral» de «sigue sonando lo anterior» (pasó al
    #    escribirlo: los cinco salían activos).
    st_inst = _post(g3, "/quake", timeout=60.0)
    activos_inst = [c for c in CHANNELS if st_inst["relays"][c]]
    check(
        "una detección instrumental SOLA no acciona (política ratificada T-2.32)",
        not activos_inst,
        str(activos_inst),
    )
    check(
        f"…pero SÍ encola su evento para la nube: {st_inst['cloud']['queued']} mensajes",
        st_inst["cloud"]["queued"] > 0,
    )

    # 2) SASMEX DESPUÉS: la protección local determinista, que es lo que este
    #    criterio promete. No depende de la nube ni de que la haya (reglas 1 y 2).
    st = _post(g3, "/sasmex", timeout=60.0)
    activos = [c for c in CHANNELS if st["relays"][c]]
    check(
        f"la actuación local ocurre igual: {len(activos)}/5 relés", len(activos) == 5, str(activos)
    )
    check("la sirena suena sin nube", st["siren_sounding"] is True)
    check(
        f"la cola durable del gabinete crece: {st['cloud']['queued']} mensajes",
        st["cloud"]["queued"] > 0,
    )
    # `sent` es el contador acumulado de publicaciones aceptadas por el transporte:
    # que no avance prueba que NADA salió del gabinete durante el corte. (Comparar
    # el tamaño de la cola no serviría: el puente la está drenando en paralelo.)
    check(
        f"nada sale del gabinete durante el corte (sent {enviados_antes} → {st['cloud']['sent']})",
        st["cloud"]["sent"] == enviados_antes,
        f"{enviados_antes} → {st['cloud']['sent']}",
    )
    check(
        "el spool durable sobrevive en disco",
        any((_WORK / "gab" / g3.thing / "spool_durable").glob("*.json")),
    )
    check("la DB no tiene incidentes de este gabinete", not _sql(conn, "SELECT 1 FROM incidents"))

    encolados = st["cloud"]["queued"]
    _post(g3, "/wan/on")
    check(
        "la cola durable drena al reconectar", wait_for(lambda: _status(g3)["cloud"]["queued"] == 0)
    )
    st = _status(g3)
    check(f"se enviaron los {encolados} mensajes encolados", st["cloud"]["sent"] > 0)

    check("la cola de IoT Core se vacía", bridge.drain(30.0), f"quedan {bridge.sqs.pending_count}")
    check("cero mensajes en la DLQ", bridge.dlq_count == dlq0, str(bridge.dlq_count - dlq0))

    incidentes = _sql(conn, "SELECT event_uuid FROM incidents")
    check(
        "el incidente detectado offline SÍ aparece ahora en el SOC",
        len(incidentes) == 1,
        str(len(incidentes)),
    )
    if not incidentes:
        return
    event_uuid = str(incidentes[0][0])

    # Idempotencia REAL: SQS entrega at-least-once y el edge puede re-publicar un
    # evento si se pierde el PUBACK al reconectar. Se RE-ENTREGA el LocalEvent
    # byte-idéntico que el gabinete archivó (`sent_events/`) y se drena de nuevo;
    # el handler REAL hace `ON CONFLICT (event_uuid) DO UPDATE`, así que NO debe
    # aparecer un segundo incidente. Comparar count(*) vs count(DISTINCT event_uuid)
    # NO probaría esto: event_uuid es NOT NULL UNIQUE, esos conteos son iguales siempre.
    archivo = _WORK / "gab" / g3.thing / "sent_events"
    reentregados = 0
    for evt in sorted(archivo.glob("*.json")):
        body = json.loads(evt.read_text())
        if body.get("event_id") == event_uuid.replace("-", ""):
            (bridge.sqs.dirs[-1] / f"reentrega-{evt.name}").write_text(evt.read_text())
            reentregados += 1
    check(f"se re-entrega el LocalEvent archivado ({reentregados})", reentregados >= 1)
    check("la re-entrega se ingiere sin atorarse", bridge.drain(20.0))

    tras = _sql(conn, "SELECT count(*) FROM incidents WHERE event_uuid = %(u)s", {"u": event_uuid})
    check(
        f"tras re-entregar el mismo evento sigue habiendo 1 incidente (ON CONFLICT): {tras[0][0]}",
        tras[0][0] == 1,
        str(tras),
    )


_WORK = Path("/tmp/takab-demo-fase1")  # noqa: S108 — workdir efímero de la demo


# --------------------------------------------------------------- C4 · simulacro
#
# [T-5.29] La escena que `T-5.08` no pudo escribir. Un simulacro son **comandos
# firmados nube→gabinete, uno por sitio**, y hasta esta ficha el arnés de la demo
# era solo edge→nube: no había por dónde bajar.
#
# Lo que esta escena ejerce, y lo que NO:
#
#   · SÍ · el router real (`start_drill`), la firma real
#     (`commands.service.issue_signed_command`), el transporte, la verificación
#     real en el gabinete (`CommandDispatcher` + `SecurityManager`: HMAC, nonce,
#     ventana), el acuse subiendo por el consumer real y el reporte real.
#   · NO · la autenticación. Aquí se construye un `Claims` a mano, igual que las
#     demás escenas construyen un `IncidentEngine` a mano: la demo no levanta
#     Cognito en ninguna de ellas. Lo que se acredita es el camino del COMANDO,
#     no el del token.

#: Ventana del simulacro. Corta a propósito: la escena mide la ENTREGA y el
#: acuse, no la duración del banner en el gabinete.
DRILL_DURATION_S = 60

#: El operador que dispara el simulacro de la demo. Hex válido y reconocible en
#: `audit_log`: quien lea la bitácora después ve de quién fue el acto.
_OPERADOR_DEMO = "d0000000-0000-4000-8000-0000000de300"


def _claims_operador(tenant_id: str) -> Claims:
    """El operador que dispara. `ALL_SITES` porque el guion apunta a los tres."""
    return Claims(
        sub=_OPERADOR_DEMO,
        groups=("tenant_admin",),
        tenant_id=tenant_id,
        role="tenant_admin",
        site_scope=ALL_SITES,
        zone_id="",
        surface="web",
    )


async def _drill(claims: Claims, publisher, keys, body: DrillCreateIn):  # noqa: ANN001, ANN202
    """Llama al router REAL dentro de una conexión con la RLS del operador."""
    async with get_tenant_conn(SessionCtx.from_claims(claims)) as conn:
        return await start_drill(body, claims, conn, publisher, keys)


async def _reporte(claims: Claims, drill_id):  # noqa: ANN001, ANN202
    async with get_tenant_conn(SessionCtx.from_claims(claims)) as conn:
        return await drill_report(drill_id, claims, conn)


def _forjar_comando(root: Path, thing: str) -> None:
    """Deja en el buzón un comando con la firma CAMBIADA.

    Se construye a mano y a propósito: firmarlo con otra clave exigiría tener una
    clave, y lo que se quiere probar es lo contrario — que **cualquier** cosa que
    no venga firmada por la nube legítima no mueve un relé.
    """
    payload = {"channel": "system", "action": "drill_start", "duration_s": DRILL_DURATION_S}
    sobre = {
        "command_id": "00000000-0000-4000-8000-00000000f0f0",
        "nonce": "nonce-forjado-de-la-demo",
        "ts": datetime.now(tz=UTC).isoformat(),
        "sig": "0" * 64,
        "payload": payload,
    }
    (downlink_dir(root, thing) / "999999999999-forjado.json").write_text(
        json.dumps({"meta_topic": f"takab/cmd/{thing}", "payload": sobre}), encoding="utf-8"
    )


def criterio_4_simulacro(conn: psycopg.Connection, bridge: Bridge, fleet: Fleet, dlq0: int) -> None:
    head("C4 · Un simulacro comandado DESDE LA NUBE suena en los gabinetes")

    tenant_id = str(
        _sql(conn, "SELECT tenant_id FROM tenants WHERE code = %(c)s", {"c": TENANT_CODE})[0][0]
    )
    sitios = [
        str(_sql(conn, "SELECT site_id FROM sites WHERE code = %(c)s", {"c": g.site})[0][0])
        for g in GABINETES
    ]
    claims = _claims_operador(tenant_id)
    publisher = SpoolCommandPublisher(_WORK / "bajada")
    # La MISMA clave que el gabinete recibió por entorno. En producción esto es
    # Secrets Manager (`SecretsManagerKeyProvider`); aquí, el mapa en memoria.
    keys = StaticKeyProvider(fleet.hmac)

    # --- 0 · el modo demostración SUPRIME también el simulacro ---------------
    #
    # No es un obstáculo del guion: es `D-27` funcionando, y verlo es media
    # escena. El modo es «un supresor de salida de la nube: notificaciones y
    # comandos firmados», y un simulacro ES un comando firmado. La consecuencia
    # operativa —que con el modo puesto NO se puede enseñar un simulacro— no
    # estaba escrita en ninguna parte hasta esta ficha.
    mudo = asyncio.run(
        _drill(claims, publisher, keys, DrillCreateIn(site_ids=sitios, duration_s=30))
    )
    check(
        "con el MODO DEMOSTRACIÓN puesto, el simulacro NO baja ni un comando (D-27)",
        publisher.published == [],
        f"publicados: {publisher.published}",
    )
    # Y aquí un hecho incómodo que esta escena deja a la vista: `start_drill` es
    # BEST-EFFORT POR SITIO —un gabinete sin clave no puede dejar sin simulacro a
    # los demás—, así que la supresión NO devuelve error: devuelve un simulacro
    # 201 con los tres sitios y sin un solo comando. Se ve después, en el reporte
    # (`no acusaron`), no en el momento de dispararlo.
    check(
        "y el simulacro se registra igual, con sus sitios y SIN comandos: el "
        "operador no se entera en el momento",
        all(s.command_id is None for s in mudo.sites) and len(mudo.sites) == len(GABINETES),
        f"sitios: {[(str(s.site_id)[:8], s.command_id) for s in mudo.sites]}",
    )
    check(
        "y el rechazo queda AUDITADO con su motivo, no se pierde",
        _sql(
            conn,
            "SELECT count(*) FROM audit_log WHERE verb = %(v)s AND meta->>'reason' = 'demo_mode'",
            {"v": "command_rejected"},
        )[0][0]
        >= 1,
    )

    # Para recorrer el simulacro entero hay que levantar la ventana. Se hace
    # explícito y ruidoso: el recuento final de entregas reales cubre TAMBIÉN
    # este tramo, así que la prueba del aislamiento sale reforzada.
    aislamiento.levantar(conn, tenant_code=TENANT_CODE)
    conn.commit()
    print("      \033[33m· ventana de demostración LEVANTADA para esta escena\033[0m")

    # --- 1 · la agenda ------------------------------------------------------
    cuando = datetime.now(tz=UTC) + timedelta(hours=2)
    agenda = asyncio.run(
        _drill(
            claims,
            publisher,
            keys,
            DrillCreateIn(
                site_ids=sitios,
                duration_s=DRILL_DURATION_S,
                note="macrosimulacro de la demo",
                scheduled_at=cuando,
            ),
        )
    )
    check("programar deja el simulacro ARMADO, sin dispararlo", agenda.active is False)
    check(
        "una agenda NO emite ni un comando (el disparo es un acto humano)",
        publisher.published == [],
        f"publicados: {publisher.published}",
    )

    # --- 2 · el disparo humano ---------------------------------------------
    drill = asyncio.run(
        _drill(claims, publisher, keys, DrillCreateIn(from_scheduled=agenda.drill_id))
    )
    esperados = len(GABINETES)
    check(
        f"el disparo publica {esperados} comandos FIRMADOS, uno por sitio",
        len(publisher.published) == esperados,
        f"publicados: {len(publisher.published)}",
    )
    check(
        "la agenda queda consumida: el banner armado deja de anunciar lo ya ocurrido",
        _sql(
            conn,
            "SELECT stop_reason FROM drills WHERE drill_id = %(d)s",
            {"d": str(agenda.drill_id)},
        )[0][0]
        == "executed",
    )

    # --- 3 · el gabinete los VERIFICA y los ejecuta -------------------------
    # El ack llega SOLO si la firma se verificó: el dispatcher no responde a un
    # emisor no autenticado (regla de oro 8). Que sea `acked` y no `rejected`
    # añade que el gabinete tenía la ejecución habilitada, cosa que la demo hizo
    # explícitamente porque de fábrica viene apagada por gateway.
    check(
        "la ejecución de comandos remotos viene APAGADA de fábrica (regla de oro 8)",
        fleet.default_command_enabled is False,
        f"default declarado por el gabinete: {fleet.default_command_enabled!r}",
    )
    entregados = wait_for(
        lambda: sum(_status(g)["downlink"]["delivered"] for g in GABINETES) >= esperados, 20.0
    )
    check(f"los {esperados} comandos llegan al gabinete por la bajada", entregados)

    # El acuse sube por el MISMO consumer real que todo lo demás y actualiza
    # `commands.status`; que llegue prueba que la firma se verificó, porque el
    # dispatcher no acusa nada que no haya verificado antes.
    bridge.drain(20.0)
    acusaron = wait_for(
        lambda: (
            _sql(
                conn,
                "SELECT count(*) FROM commands WHERE event_id = %(e)s AND status = 'acked'",
                {"e": f"DRILL-{drill.drill_id}"},
            )[0][0]
            == esperados
        ),
        25.0,
    )
    check(
        f"los {esperados} gabinetes ACUSAN el simulacro (firma verificada en el edge)",
        acusaron,
        str(
            _sql(
                conn,
                "SELECT status, count(*) FROM commands WHERE event_id = %(e)s GROUP BY status",
                {"e": f"DRILL-{drill.drill_id}"},
            )
        ),
    )

    # --- 4 · un comando FORJADO no mueve nada -------------------------------
    # Es la mitad que hace creíble la otra: si la bajada entregara sin verificar,
    # todo lo de arriba pasaría igual y no probaría nada.
    victima = GABINETES[0]
    _forjar_comando(_WORK / "bajada", victima.thing)
    rechazado = wait_for(
        lambda: "comando rechazado: firma inválida" in fleet.bitacora(victima.thing), 15.0
    )
    check("un comando con firma inválida se RECHAZA y queda en la bitácora", rechazado)
    check(
        "y NO produce acuse: al emisor no autenticado no se le responde",
        _sql(
            conn,
            "SELECT count(*) FROM commands WHERE event_id = %(e)s",
            {"e": f"DRILL-{drill.drill_id}"},
        )[0][0]
        == esperados,
    )

    # --- 5 · el reporte -----------------------------------------------------
    reporte = asyncio.run(_reporte(claims, drill.drill_id))
    check(
        f"el reporte cuenta {esperados} acuses y ningún sitio sin gabinete",
        (reporte.acked, reporte.not_acked, reporte.no_gateway) == (esperados, 0, 0),
        f"acked={reporte.acked} no_acked={reporte.not_acked} sin_gw={reporte.no_gateway}",
    )
    check("el reporte queda inscrito como evidencia con su sha256", len(reporte.sha256) == 64)

    # --- guarda de no-vacuidad ---------------------------------------------
    # Sin esto, una escena en la que NADA bajara pasaría en verde: todos los
    # `wait_for` de arriba comparan contra cero cuando no hay nada que contar.
    bajados = sum(_status(g)["downlink"]["delivered"] for g in GABINETES)
    check(
        f"la demo entregó {bajados} comandos por la bajada (esperados ≥ {esperados + 1})",
        bajados >= esperados + 1,  # los del simulacro + el forjado
        f"entregados: {bajados}",
    )
    check("el simulacro no mandó nada a la DLQ", bridge.dlq_count == dlq0)

    # Se vuelve a poner: dejar la ventana levantada al terminar sería salir de la
    # demo en el estado inseguro, que es lo contrario de lo que `T-5.08` cerró.
    aislamiento.imponer(conn, tenant_code=TENANT_CODE)
    conn.commit()
    check(
        "el MODO DEMOSTRACIÓN queda restaurado al salir de la escena",
        ventana_viva_sync(conn, tenant_id=tenant_id, now=datetime.now(tz=UTC)) is not None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="no borrar el workdir al terminar")
    args = parser.parse_args()

    print("\033[1mTAKAB Ailert · Hito de salida Fase 1 — demo con 3 gabinetes\033[0m")
    print("Sustituido: sólo IoT Core + SQS. Edge, ingesta, motor de quórum y SOC son los reales.")
    print("Gate #3 abierto: relés MOCK; la latencia física <100 ms NO se acredita aquí.\n")

    if _WORK.exists():
        subprocess.run(["rm", "-rf", str(_WORK)], check=True)  # noqa: S603, S607
    (_WORK / "cola").mkdir(parents=True)

    # [T-5.29] Almacén de objetos del reporte del simulacro (C4). Mismos valores
    # que `demo/soc_local.sh`: el compose local ya trae MinIO y su bucket. No se
    # pisa lo que el operador haya puesto: si apunta a otro sitio, manda él.
    os.environ.setdefault("TAKAB_API_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    os.environ.setdefault("TAKAB_API_EVIDENCE_BUCKET", "takab-dev-evidence")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "takab")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "takab_dev_secret")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")

    settings = Settings(database_url=DSN)
    conn = psycopg.connect(DSN, autocommit=False)
    _assert_exclusive_db(conn)  # antes de abrir bridge/soc/fleet: todo otro cliente es ajeno
    reset_state(conn)

    # [T-5.08] El aislamiento deja de ser implícito. Antes descansaba en que este
    # guion no lanza el worker de notificación — una coincidencia de arranque, no
    # un aislamiento: con un `make soc-local` a medio apagar (que sí lo levanta) la
    # cascada saldría por los canales configurados hacia teléfonos reales.
    #
    # Ahora se ENCIENDE el modo demostración del cliente y se comprueba que quedó
    # vivo. Suprime las salidas de la nube y NO puede tocar el gabinete, así que la
    # protección local que esta demo acredita se sigue demostrando de verdad.
    tenant_demo = imponer(conn, tenant_code=TENANT_CODE)
    conn.commit()
    print(
        f"  \033[36mMODO DEMOSTRACIÓN ENCENDIDO\033[0m para {TENANT_CODE} "
        "— entregas y comandos de actuador suprimidos; el gabinete NO se entera.\n"
    )

    fleet = Fleet(_WORK)
    bridge = Bridge([_WORK / "cola" / g.thing for g in GABINETES], _WORK / "dlq", DSN)
    bridge.start()
    soc = SocListener(DSN)

    try:
        criterio_1_sasmex(conn, bridge, soc, escena(fleet, bridge, conn))
        criterio_2_quorum(conn, bridge, settings, escena(fleet, bridge, conn))
        criterio_3_corte(conn, bridge, escena(fleet, bridge, conn))
        criterio_4_simulacro(conn, bridge, fleet, escena(fleet, bridge, conn))
    finally:
        soc.close()
        bridge.stop()
        fleet.stop()
        conn.close()
        if not args.keep:
            subprocess.run(["rm", "-rf", str(_WORK)], check=False)  # noqa: S603, S607

    # [T-5.08] La prueba del aislamiento, al final y sobre HECHOS: si algo salió de
    # verdad por un canal, se dice. `simulated` no cuenta —es lo que produce un
    # canal sin credenciales, y desaparece justo en el entorno de la demostración—.
    with psycopg.connect(DSN, autocommit=True) as c2:
        salidas = entregas_reales(c2)
    check(
        f"NADA salió por un canal real durante la demo (modo demostración de {tenant_demo[:8]}…)",
        not salidas,
        str(salidas),
    )

    print(f"\n{'=' * 66}")
    estado = "\033[32mHITO ACREDITADO\033[0m" if _fail == 0 else "\033[31mHITO NO ACREDITADO\033[0m"
    print(f"  {estado} — {_ok} OK · {_fail} FALLOS")
    print(f"{'=' * 66}")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
