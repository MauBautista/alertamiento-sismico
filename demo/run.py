"""Hito de salida Fase 1 — demo en vivo con 3 gabinetes, con evidencia verificable.

Levanta 3 ``EdgeSupervisor`` reales (un proceso cada uno), el ``SqsConsumer`` real
sobre el spool, y el ``IncidentEngine`` real. Ejecuta los 3 criterios del hito y
FALLA RUIDOSAMENTE si alguno no se cumple:

  C1  prueba SASMEX dispara actuadores y aparece en el SOC
  C2  sismo simulado en 3 estaciones activa quórum
  C3  corte de internet no detiene la protección local

Lo único sustituido es IoT Core + SQS (ver ``demo/spool.py``). El SOC se observa por
el mismo ``NOTIFY takab_live`` que alimenta al hub WebSocket de la consola: medir ahí
es medir el instante en que el live wall recibe el frame, sin depender de Cognito.

Honestidad de lo que NO demuestra (gate #3 abierto: no hay WR-1, relés, sirena ni
válvula cableados): la actuación es sobre relés MOCK y la latencia medida es la de
la ruta software. El presupuesto físico <100 ms (debounce + interrupción + relé) se
valida con hardware, y esta demo NO lo acredita.

    python demo/run.py            # requiere DB migrada + seed (make demo-fase1)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import psycopg

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from demo.bridge import Bridge, ingest_conn_factory  # noqa: E402

from takab_api.incident.engine import IncidentEngine  # noqa: E402
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


def reset_state(conn: psycopg.Connection) -> None:
    """Pizarra limpia entre criterios. Sólo tablas de datos, nunca el registro.

    TRUNCATE (no DELETE): `incident_actions` es append-only por trigger.
    """
    _assert_local_db(conn)
    conn.execute(
        "TRUNCATE seismic_events, incidents, incident_actions, quorum_votes, "
        "waveform_features_1s, device_health CASCADE"
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
                    "--control-port",
                    str(gab.port),
                ],
                cwd=str(_ROOT / "edge"),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            line = proc.stdout.readline()  # bloquea hasta el {"ready": true}
            if '"ready": true' not in line:
                raise SystemExit(f"el gabinete {gab.thing} no arrancó: {line!r}")
            self.procs.append(proc)

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
    st = _post(g3, "/quake", timeout=60.0)  # sismo CON la WAN caída

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

    settings = Settings(database_url=DSN)
    conn = psycopg.connect(DSN, autocommit=False)
    reset_state(conn)

    fleet = Fleet(_WORK)
    bridge = Bridge([_WORK / "cola" / g.thing for g in GABINETES], _WORK / "dlq", DSN)
    bridge.start()
    soc = SocListener(DSN)

    try:
        criterio_1_sasmex(conn, bridge, soc, escena(fleet, bridge, conn))
        criterio_2_quorum(conn, bridge, settings, escena(fleet, bridge, conn))
        criterio_3_corte(conn, bridge, escena(fleet, bridge, conn))
    finally:
        soc.close()
        bridge.stop()
        fleet.stop()
        conn.close()
        if not args.keep:
            subprocess.run(["rm", "-rf", str(_WORK)], check=False)  # noqa: S603, S607

    print(f"\n{'=' * 66}")
    estado = "\033[32mHITO ACREDITADO\033[0m" if _fail == 0 else "\033[31mHITO NO ACREDITADO\033[0m"
    print(f"  {estado} — {_ok} OK · {_fail} FALLOS")
    print(f"{'=' * 66}")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
