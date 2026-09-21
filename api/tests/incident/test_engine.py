"""Correlación de red del quórum contra Postgres real (T-1.19 · B1).

Geometría sintética realista (sitios a 0/40/90/110 km de un origen común al sur
de CDMX/Puebla, colocados con ``ST_Project``): los ``opened_at`` de cada incidente
son los arribos teóricos de la onda P a 6.5 km/s + jitter, así que dos sitios
SIEMPRE asocian (la diferencia de arribos ≤ distancia inter-sitio / v_P, por la
desigualdad triangular). Se verifica que un arribo a 17 s (110 km) todavía asocia
—cosa que una ventana fija de 2–5 s rechazaría erróneamente (blueprint §4.5)—.

La siembra es SQL directo (no toca ``conftest``); el motor corre bajo
``SET ROLE takab_ingest`` (BYPASSRLS), igual que en la nube. Cada test usa un
tenant fresco y limpia su grafo al terminar (los eventos de red se comparten y se
purgan por ``source='local_quorum'``).
"""

from __future__ import annotations

import inspect
import json
import os
import re
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.incident import engine as engine_mod
from takab_api.incident.engine import _CORRELATION_LOCK_KEY, IncidentEngine
from takab_api.settings import Settings

V_P = 6.5
# Origen común de siembra, deliberadamente AISLADO (Pacífico, muy al sur) de toda
# flota fixture del resto de la suite (>500 km): el escaneo del quórum es
# cross-tenant (§4.5) y el fail-open abriría incidentes sintéticos IMBORRABLES
# (``incident_actions`` es append-only) en sitios en rango de otros tenants, que
# contaminarían la correlación. La física es relativa a las distancias inter-sitio,
# así que ubicar el origen aquí no altera ninguna aserción.
SRC_LON, SRC_LAT = -98.5, 13.0
# El engine escanea incidentes de TODA la red (dato cross-tenant, blueprint §4.5).
# En una DB de test compartida eso podría barrer datos de otros archivos; se aísla
# con un BASE en el futuro lejano (fuera de la ventana lookback de cualquier now()).
BASE = datetime(2030, 6, 15, 12, 0, 0, tzinfo=UTC)

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _Scenario:
    """Conexión + tenant + helper de siembra para un escenario de correlación."""

    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant

    def seed(
        self, specs: list[tuple[float, datetime]], *, reverse_insert: bool = False
    ) -> list[dict]:
        """Inserta un sitio+sensor estructural+feature+incidente por ``(dist_km, opened_at)``.

        Devuelve, por sitio, ``{"site","sensor","incident","dist_km","opened_at"}``.
        ``reverse_insert`` inserta en orden inverso al cronológico (prueba que el
        resultado es independiente del orden de inserción).
        """
        rows = list(reversed(specs)) if reverse_insert else specs
        out: list[dict] = []
        for i, (dist_km, opened_at) in enumerate(rows):
            site, sensor = str(uuid.uuid4()), str(uuid.uuid4())
            incident, event_uuid = str(uuid.uuid4()), str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'S', ST_Project("
                "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, 0.0)::geography)",
                (site, self.tenant, f"S{i}-{site[:4]}", SRC_LON, SRC_LAT, dist_km * 1000.0),
            )
            self.conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                "VALUES (%s,%s,%s,'structural','RS4D')",
                (sensor, self.tenant, site),
            )
            self.conn.execute(
                "INSERT INTO waveform_features_1s "
                "(ts, tenant_id, site_id, sensor_id, channel, pga_g) "
                "VALUES (%s,%s,%s,%s,'ENZ',%s)",
                (opened_at, self.tenant, site, sensor, 0.05 + 0.01 * i),
            )
            self.conn.execute(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
                (incident, event_uuid, self.tenant, site, opened_at),
            )
            out.append(
                {
                    "site": site,
                    "sensor": sensor,
                    "incident": incident,
                    "dist_km": dist_km,
                    "opened_at": opened_at,
                }
            )
        self.conn.commit()
        return out


def _arrival(dist_km: float, jitter_s: float = 0.0) -> datetime:
    """Arribo teórico de la onda P al sitio: BASE + dist/v_P + jitter."""
    return BASE + timedelta(seconds=dist_km / V_P + jitter_s)


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")  # paridad con la nube (BYPASSRLS)
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Engine Test')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield _Scenario(conn, tenant)
    finally:
        _cleanup(conn, tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    """Purga SÓLO el grafo de este tenant (los eventos de red se borran por los
    que MIS incidentes referencian). El origen de siembra (``SRC``) está deliberada-
    mente AISLADO de toda flota fixture (>400 km): así el fail-open no abre
    incidentes sintéticos —imborrables: ``incident_actions`` es append-only— en
    sitios de otros tenants, y este DELETE no choca con la FK ni deja residuo."""
    conn.rollback()
    conn.execute("RESET ROLE")  # takab_ingest no tiene DELETE; el superusuario sí
    try:
        event_ids = [
            r["event_id"]
            for r in conn.execute(
                "SELECT DISTINCT event_id FROM incidents "
                "WHERE tenant_id = %s AND event_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        ]
        if event_ids:
            conn.execute("DELETE FROM quorum_votes WHERE event_id = ANY(%s)", (event_ids,))
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
        if event_ids:
            conn.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (event_ids,))
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _engine(**kw: float) -> IncidentEngine:
    # conn_factory sin uso en run_correlation (sólo el bucle run() lo usa).
    return IncidentEngine(lambda: None, Settings(), lookback_s=300.0, **kw)  # type: ignore[arg-type]


def _votes(conn: psycopg.Connection, event_id: str) -> list[dict]:
    return conn.execute(
        "SELECT sensor_id, pga_g, delta_s, counted FROM quorum_votes "
        "WHERE event_id = %s ORDER BY delta_s",
        (event_id,),
    ).fetchall()


# --------------------------------------------------------------------------- G2/G4


def test_correlates_distance_aware_cluster(scenario: _Scenario) -> None:
    """0/40/90/110 km → 1 seismic_event 'local_quorum' + 4 votes + 4 incidentes linkeados.

    El sitio a 110 km arriba a ~17 s del ancla y AÚN ASÍ asocia (distance-aware);
    una ventana fija de 2–5 s lo habría descartado.
    """
    seeded = scenario.seed(
        [
            (0.0, _arrival(0.0, 0.10)),
            (40.0, _arrival(40.0, -0.20)),
            (90.0, _arrival(90.0, 0.15)),
            (110.0, _arrival(110.0, -0.05)),
        ]
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1
    event_id = created[0]

    ev = scenario.conn.execute(
        "SELECT source, magnitude, detected_at, meta, "
        "ST_Y(epicenter::geometry) AS lat, ST_X(epicenter::geometry) AS lon "
        "FROM seismic_events WHERE event_id = %s",
        (event_id,),
    ).fetchone()
    assert ev["source"] == "local_quorum"
    assert ev["magnitude"] is None  # no hay magnitud en vivo (WR-1 booleano)
    assert ev["detected_at"] == seeded[0]["opened_at"]  # ancla = arribo más temprano
    assert ev["meta"]["node_count"] == 4
    assert SRC_LAT < ev["lat"] < _arrival_lat_max()  # epicentro entre los sitios

    votes = _votes(scenario.conn, event_id)
    assert len(votes) == 4
    # delta_s monótono creciente y el del ancla es 0.
    deltas = [float(v["delta_s"]) for v in votes]
    assert deltas[0] == pytest.approx(0.0, abs=1e-6)
    assert deltas == sorted(deltas)
    assert deltas[-1] == pytest.approx(110.0 / V_P - 0.05 - 0.10, abs=0.01)
    assert all(v["counted"] for v in votes)
    # PGA tomada del pico de waveform_features_1s (no el default 0).
    assert all(float(v["pga_g"]) > 0 for v in votes)

    linked = scenario.conn.execute(
        "SELECT COUNT(*) AS n FROM incidents WHERE tenant_id = %s AND event_id = %s",
        (scenario.tenant, event_id),
    ).fetchone()
    assert linked["n"] == 4


def _arrival_lat_max() -> float:
    # Latitud del sitio más lejano (110 km al norte del origen); cota del centroide.
    return SRC_LAT + 2.0  # 110 km ≈ ~1° de latitud; cota holgada


# ----------------------------------------------------------------- negativos G4


def test_out_of_window_no_event(scenario: _Scenario) -> None:
    """Un tercer sitio con Δt = 40 s (fuera de max_window) no asocia → < min_nodes → sin evento."""
    scenario.seed(
        [
            (0.0, _arrival(0.0)),
            (40.0, _arrival(40.0)),
            # Sitio cercano (5 km) pero desfasado 40 s: > max_window (30) y > 5/6.5+3.
            (5.0, BASE + timedelta(seconds=40.0)),
        ]
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert created == []
    assert _my_events(scenario) == 0


def test_below_min_nodes_no_event(scenario: _Scenario) -> None:
    """Sólo 2 estaciones (< min_nodes=3) → sin evento."""
    scenario.seed([(0.0, _arrival(0.0)), (40.0, _arrival(40.0))])
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert created == []
    assert _my_events(scenario) == 0


# ------------------------------------------------------------ idempotencia G2


def test_rerun_is_idempotent(scenario: _Scenario) -> None:
    """Re-correlacionar no duplica: mismo evento, mismos votos, mismos enlaces."""
    scenario.seed([(0.0, _arrival(0.0)), (40.0, _arrival(40.0)), (90.0, _arrival(90.0))])
    now = BASE + timedelta(seconds=120)
    first = _engine().run_correlation(scenario.conn, now=now)
    assert len(first) == 1

    second = _engine().run_correlation(scenario.conn, now=now)
    assert second == []  # ya corroborados (event_id IS NOT NULL) → nada que hacer

    assert _my_events(scenario) == 1
    assert len(_votes(scenario.conn, first[0])) == 3
    linked = scenario.conn.execute(
        "SELECT COUNT(*) AS n FROM incidents WHERE tenant_id = %s AND event_id = %s",
        (scenario.tenant, first[0]),
    ).fetchone()
    assert linked["n"] == 3


# ------------------------------------------------------ orden de inserción G4


def test_out_of_order_insertion_same_result(scenario: _Scenario) -> None:
    """Insertar el ancla al final no cambia el resultado (correlate ordena por tiempo)."""
    seeded = scenario.seed(
        [(0.0, _arrival(0.0)), (40.0, _arrival(40.0)), (90.0, _arrival(90.0))],
        reverse_insert=True,  # el ancla (0 km) se inserta de última
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1
    ev = scenario.conn.execute(
        "SELECT detected_at FROM seismic_events WHERE event_id = %s", (created[0],)
    ).fetchone()
    earliest = min(s["opened_at"] for s in seeded)
    assert ev["detected_at"] == earliest
    # El voto del ancla tiene delta_s = 0.
    assert float(_votes(scenario.conn, created[0])[0]["delta_s"]) == pytest.approx(0.0, abs=1e-6)


# -------------------------------------------------- multi-evento en una pasada


def test_two_disjoint_events_one_pass(scenario: _Scenario) -> None:
    """Dos cúmulos separados > max_window en el tiempo → 2 eventos en una sola pasada."""
    # Cúmulo A alrededor de BASE; cúmulo B a +120 s (más allá de max_window=30).
    scenario.seed(
        [
            (0.0, _arrival(0.0)),
            (40.0, _arrival(40.0)),
            (90.0, _arrival(90.0)),
            (0.0, BASE + timedelta(seconds=120.0)),
            (40.0, BASE + timedelta(seconds=120.0 + 40.0 / V_P)),
            (90.0, BASE + timedelta(seconds=120.0 + 90.0 / V_P)),
        ]
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=200))
    assert len(created) == 2
    assert _my_events(scenario) == 2
    for ev in created:
        assert len(_votes(scenario.conn, ev)) == 3


# ------------------------------------------------------------- no-bloqueo G3


def test_engine_absent_does_not_block_writes(scenario: _Scenario) -> None:
    """Con el motor APAGADO, la ingesta de un incidente y su ack (state) commitean bien.

    Documenta la regla de oro: el motor de red es cloud-only y post-hoc; su
    ausencia jamás bloquea la actuación/ingesta local del edge.
    """
    site, sensor = str(uuid.uuid4()), str(uuid.uuid4())
    incident, event_uuid = str(uuid.uuid4()), str(uuid.uuid4())
    scenario.conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,'NB','S', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
        (site, scenario.tenant, SRC_LON, SRC_LAT),
    )
    scenario.conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
        "VALUES (%s,%s,%s,'structural','RS4D')",
        (sensor, scenario.tenant, site),
    )
    # Ingesta del edge (incidente) — nunca depende del motor.
    scenario.conn.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
        "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,'critical','sasmex')",
        (incident, event_uuid, scenario.tenant, site, _arrival(0.0)),
    )
    scenario.conn.commit()
    # Ack (open→acked) sin motor corriendo.
    scenario.conn.execute("UPDATE incidents SET state='acked' WHERE incident_id = %s", (incident,))
    scenario.conn.commit()

    row = scenario.conn.execute(
        "SELECT state FROM incidents WHERE incident_id = %s", (incident,)
    ).fetchone()
    assert row["state"] == "acked"
    assert _my_events(scenario) == 0  # el motor no corrió


def _node_count(scenario: _Scenario, event_id: str) -> int:
    return scenario.conn.execute(
        "SELECT (meta->>'node_count')::int AS n FROM seismic_events WHERE event_id = %s",
        (event_id,),
    ).fetchone()["n"]


def _event_of(scenario: _Scenario, incident_id: str) -> str | None:
    return scenario.conn.execute(
        "SELECT event_id FROM incidents WHERE incident_id = %s", (incident_id,)
    ).fetchone()["event_id"]


# --------------------------------------------------- ancla espuria no suprime (#1/#2)


def test_spurious_early_out_of_window_detection_does_not_suppress_quorum(
    scenario: _Scenario,
) -> None:
    """Un disparo espurio anterior y FUERA de ventana (el más temprano) no debe
    abortar la correlación: el quórum sísmico REAL posterior sí se confirma (#1).

    Antes, ``run_correlation`` hacía ``break`` cuando el ancla más temprana no
    formaba cúmulo → el espurio enmascaraba al sismo real.
    """
    seeded = scenario.seed(
        [
            (5.0, BASE + timedelta(seconds=0.0)),  # X: espurio aislado, el más temprano
            (0.0, BASE + timedelta(seconds=40.0)),  # ancla del sismo real
            (40.0, BASE + timedelta(seconds=40.0 + 40.0 / V_P)),
            (90.0, BASE + timedelta(seconds=40.0 + 90.0 / V_P)),
        ]
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1  # el sismo real SÍ se corrobora
    assert _node_count(scenario, created[0]) == 3  # burst {0,40,90}; X excluido
    assert _event_of(scenario, seeded[0]["incident"]) is None  # X sigue sin linkear


def test_isolated_single_site_anchor_does_not_poison_window(scenario: _Scenario) -> None:
    """Un incidente mono-sitio no corroborado ~200 s antes del sismo (el más
    temprano del lookback) no suprime el quórum real posterior (#2)."""
    scenario.seed(
        [
            (5.0, BASE + timedelta(seconds=0.0)),  # local_threshold aislado
            (0.0, BASE + timedelta(seconds=200.0)),
            (40.0, BASE + timedelta(seconds=200.0 + 40.0 / V_P)),
            (90.0, BASE + timedelta(seconds=200.0 + 90.0 / V_P)),
        ]
    )
    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=300))
    assert len(created) == 1
    assert len(_votes(scenario.conn, created[0])) == 3
    assert _my_events(scenario) == 1


# ----------------------------------------- ruido viejo del mismo sitio no enmascara (#3)


def test_stale_same_site_detection_does_not_mask_real_one(scenario: _Scenario) -> None:
    """Un sitio con un incidente de ruido viejo (más temprano) y su detección REAL
    del sismo: la selección debe tomar la real, no el ruido, para no sub-contar el
    quórum ni linkear el incidente equivocado (#3)."""
    scenario.seed([(40.0, _arrival(40.0)), (90.0, _arrival(90.0))])  # B, C del cúmulo
    conn = scenario.conn
    site_a, sensor_a = str(uuid.uuid4()), str(uuid.uuid4())
    noise_inc, real_inc = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,'A0','S', ST_Project("
        "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 0.0, 0.0)::geography)",
        (site_a, scenario.tenant, SRC_LON, SRC_LAT),
    )
    conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
        "VALUES (%s,%s,%s,'structural','RS4D')",
        (sensor_a, scenario.tenant, site_a),
    )
    conn.execute(
        "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g) "
        "VALUES (%s,%s,%s,%s,'ENZ',0.08)",
        (_arrival(0.0), scenario.tenant, site_a, sensor_a),
    )
    for inc_id, opened in ((noise_inc, BASE - timedelta(seconds=120)), (real_inc, _arrival(0.0))):
        conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
            (inc_id, str(uuid.uuid4()), scenario.tenant, site_a, opened),
        )
    conn.commit()

    created = _engine().run_correlation(conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1
    assert _node_count(scenario, created[0]) == 3  # A cuenta con su detección real
    assert _event_of(scenario, real_inc) == created[0]  # se linkeó la REAL
    assert _event_of(scenario, noise_inc) is None  # el ruido viejo NO
    assert len(_votes(scenario.conn, created[0])) == 3


# --------------------------------------- umbral estricto del ancla no suprime (#5)


def test_strict_anchor_ruleset_does_not_suppress_network_event(scenario: _Scenario) -> None:
    """El rule_set del sitio ancla exige min_nodes=5 pero sólo 4 sitios asocian:
    el evento de red NO debe suprimirse — se reintenta con otra ancla cuya config
    (default min_nodes=3) sí confirma el quórum (#5)."""
    seeded = scenario.seed(
        [
            (0.0, _arrival(0.0, 0.10)),
            (40.0, _arrival(40.0, -0.20)),
            (90.0, _arrival(90.0, 0.15)),
            (110.0, _arrival(110.0, -0.05)),
        ]
    )
    anchor_site = seeded[0]["site"]  # 0 km = arribo más temprano = ancla
    scenario.conn.execute(
        "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active, config) "
        "VALUES (%s,'site',%s,1,true,%s::jsonb)",
        (scenario.tenant, anchor_site, json.dumps({"quorum": {"min_nodes": 5}})),
    )
    scenario.conn.commit()

    created = _engine().run_correlation(scenario.conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1  # NO suprimido pese al umbral estricto del ancla
    assert _node_count(scenario, created[0]) == 3  # {40,90,110}; el ancla estricta cae
    assert _event_of(scenario, seeded[0]["incident"]) is None  # el sitio estricto sin linkear


# ------------------------------------- lock serializa instancias concurrentes (#4)


def test_concurrent_correlation_serializes_no_duplicate(scenario: _Scenario) -> None:
    """Dos instancias del engine no crean dos eventos del mismo sismo: la segunda
    BLOQUEA en el advisory lock de correlación hasta que la primera commitea (#4)."""
    scenario.seed([(0.0, _arrival(0.0)), (40.0, _arrival(40.0)), (90.0, _arrival(90.0))])
    now = BASE + timedelta(seconds=120)

    # El fixture (scenario.conn) simula la instancia I1 reteniendo el lock en una txn.
    scenario.conn.execute("SELECT pg_advisory_xact_lock(%s)", (_CORRELATION_LOCK_KEY,))

    conn2 = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    out: dict[str, object] = {}

    def worker() -> None:
        try:
            conn2.execute("SET ROLE takab_ingest")
            out["created"] = _engine().run_correlation(conn2, now=now)
        except BaseException as exc:  # noqa: BLE001 — se re-lanza vía assert en el hilo main
            out["err"] = exc

    t = threading.Thread(target=worker)
    t.start()
    try:
        t.join(timeout=1.0)
        was_blocked = t.is_alive()  # I2 bloqueada en el advisory lock mientras I1 lo tiene
    finally:
        scenario.conn.rollback()  # SIEMPRE suelta el lock (I1) aunque falle un assert
        t.join(timeout=30.0)  # SIEMPRE espera al worker antes de cerrar su conexión
        conn2.close()

    assert was_blocked, "run_correlation no serializó por el advisory lock"
    assert "err" not in out, out.get("err")
    assert isinstance(out["created"], list) and len(out["created"]) == 1
    assert _my_events(scenario) == 1
    assert len(_votes(scenario.conn, out["created"][0])) == 3  # type: ignore[index]


# ---------------------------------- el worker sobrevive un corte de DB prolongado (#6)


# Vueltas que el bucle tiene que dar DESPUÉS de reanudar para que la supervivencia
# esté medida. Con 1 el test sería el de antes: el hilo puede morir en esa misma
# vuelta, después de los asserts. Con 3 hay al menos dos vueltas completas —la
# muerte del hilo ocurre AL FINAL de una vuelta, así que sobrevivir a dos exige
# que el bucle haya vuelto a entrar por arriba.
_VUELTAS_SOSTENIDAS = 3


class _PasadaEscapada(BaseException):
    """Una pasada tocó la conexión falsa, o sea que la neutralización la perdió.

    Deriva de `BaseException` **a propósito**, y es la única forma de que el
    escape se vea: el bucle de `run` envuelve cada vuelta en `except Exception`
    —y el rollback de la recuperación en otro—, así que un `AttributeError` de
    la conexión falsa lo absorben los dos y la corrida sigue en verde. Lo que
    `except Exception` no atrapa sale del hilo, mata al bucle y hace fallar el
    `assert sostenido.wait(...)` de abajo con su mensaje.
    """


# Las dos llamadas del bucle que el test gobierna por su cuenta (una da la
# conexión falsa, la otra cuenta las vueltas): todo lo DEMÁS que el bucle llame
# con la conexión de trabajo se silencia solo.
_YA_GOBERNADAS = ("_ensure_work", "run_correlation")


def _neutraliza_las_pasadas(monkeypatch: pytest.MonkeyPatch, eng: IncidentEngine) -> list[str]:
    """Silencia las pasadas del bucle DERIVÁNDOLAS del cuerpo de ``run``.

    Enumerarlas a mano es lo que dejó ciega a la guarda de abajo: se escribieron
    tres ``monkeypatch`` con su comentario de ficha, llegaron ``_shakemap_pass``
    (T-7.24) y ``_consulta_catalogo_pass`` (T-7.25), nadie añadió las suyas, y la
    primera sin parchear reventaba contra la conexión falsa y mataba al hilo — con
    el test en verde. Se lee el propio bucle en vez de fiarlo a un sufijo: una
    pasada nueva queda cubierta el día que se escribe, se llame como se llame.
    """
    fuente = inspect.getsource(IncidentEngine.run)
    llamadas = list(dict.fromkeys(re.findall(r"self\.(\w+)\(work_conn\)", fuente)))
    faltan = [n for n in _YA_GOBERNADAS if n not in llamadas]
    assert not faltan, (
        f"el bucle ya no llama a {faltan} con `work_conn`: este helper quedó "
        "desalineado de `run` y silenciaría lo que el test necesita vivo"
    )
    pasadas = [n for n in llamadas if n not in _YA_GOBERNADAS]
    assert pasadas, "no se detectó ninguna pasada en el cuerpo de `run`"
    for nombre in pasadas:
        monkeypatch.setattr(eng, nombre, lambda wc: None)
    return pasadas


def test_run_survives_prolonged_db_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un corte de DB más largo que el presupuesto de ``with_retry`` no mata al
    worker: la (re)conexión ocurre DENTRO del bucle y reintenta indefinidamente (#6).

    Lo que mide es SUPERVIVENCIA SOSTENIDA: que el bucle siga dando vueltas
    después de reanudar. La versión anterior comprobaba ``t.is_alive()`` en la
    MISMA vuelta que reanudaba —los tres asserts caían antes de que la vuelta
    terminara—, así que acreditaba supervivencia por carrera, no por invariante:
    durante T-7.24 estuvo en verde mientras el hilo del bucle moría en cada
    corrida. Una guarda de supervivencia que no ve morir al proceso acredita lo
    contrario de lo que promete.
    """
    monkeypatch.setattr(engine_mod, "_RECONNECT_BACKOFF_S", 0.01)
    monkeypatch.setattr(engine_mod, "_ERROR_BACKOFF_S", 0.01)
    eng = IncidentEngine(lambda: None, Settings(), poll_s=0.01, lookback_s=300.0)  # type: ignore[arg-type]

    connects = {"n": 0}
    vueltas = {"n": 0}
    reanudo = threading.Event()
    sostenido = threading.Event()

    class _Dummy:
        # Deliberadamente MÍNIMO: con las pasadas neutralizadas nadie le pide nada
        # más que `closed`/`close()`. Cualquier otro atributo es una pasada que se
        # escapó de la neutralización, y entonces tiene que REVENTAR A LA VISTA.
        #
        # ⚠️ Y por eso el escape sale por `__getattr__` con un `BaseException`, y
        # no por la ausencia del atributo. Medido el 2026-09-21 con el `_Dummy`
        # anterior —sin `execute` ni `rollback`— y la neutralización sustituida por
        # la enumeración a mano de cuatro pasadas: `1 passed in 1.88s`, cero
        # warnings. La ironía era que el propio arreglo de `run` tapaba el síntoma:
        # el `except Exception` del ciclo se traga el `AttributeError` de la pasada,
        # el `except Exception` del rollback se traga el segundo, y el bucle sigue
        # dando vueltas, así que el test acreditaba supervivencia mientras el
        # trabajo de dos pasadas no se hacía. Con `-o log_cli=true` se veía lo que
        # ocultaba —«engine: error inesperado en el ciclo» + «rollback fallido»,
        # tres vueltas idénticas— y aun así `1 passed`.
        closed = False

        def close(self) -> None:
            pass

        def __getattr__(self, nombre: str) -> object:
            raise _PasadaEscapada(
                f"una pasada del bucle le pidió `{nombre}` a la conexión falsa: se "
                "escapó de `_neutraliza_las_pasadas` y estaría corriendo de verdad "
                "contra una conexión que no existe"
            )

    def flaky_connect() -> _Dummy:
        connects["n"] += 1
        if connects["n"] <= 3:  # 3 cortes seguidos (agotan with_retry)
            raise psycopg.OperationalError("db down")
        return _Dummy()

    def _correlacion(conn: object) -> list[str]:
        vueltas["n"] += 1
        reanudo.set()
        if vueltas["n"] >= _VUELTAS_SOSTENIDAS:
            sostenido.set()
        return []

    monkeypatch.setattr(eng, "_connect_listen", flaky_connect)
    monkeypatch.setattr(eng, "_drain_notifies", lambda lc: None)
    monkeypatch.setattr(eng, "_ensure_work", lambda wc: _Dummy())
    monkeypatch.setattr(eng, "run_correlation", _correlacion)
    _neutraliza_las_pasadas(monkeypatch, eng)  # derivadas, no enumeradas

    t = threading.Thread(target=eng.run)
    t.start()
    try:
        assert reanudo.wait(5.0)  # reanudó la correlación tras los cortes
        assert connects["n"] >= 4  # reconectó (no salió por el except)
        assert sostenido.wait(5.0), (
            f"el bucle dejó de dar vueltas tras reanudar: {vueltas['n']} de "
            f"{_VUELTAS_SOSTENIDAS}; hilo vivo={t.is_alive()}"
        )
        assert t.is_alive()
    finally:
        eng.stop()
        t.join(timeout=5.0)
    assert not t.is_alive()


def test_run_no_muere_si_la_recuperacion_de_una_pasada_tambien_falla(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una pasada revienta Y la recuperación revienta con ella ⇒ el bucle SIGUE.

    Es la otra mitad del #6, y la que no estaba medida. El manejador de errores
    inesperados del bucle hace ``work_conn.rollback()``; si eso levanta algo que
    no es ``psycopg.Error`` —y puede, porque lo que entra ahí es un fallo
    INESPERADO de cualquier pasada, no un fallo de la DB—, la excepción escapa
    del manejador, sale por el ``finally`` y el worker muere en silencio: ya
    nadie correla, dictamina ni cierra incidentes, y ninguna alarma lo dice.

    Aquí las pasadas NO se silencian a propósito: la primera que toque la
    conexión falsa revienta, que es justo el escenario. Y el ``close`` también
    levanta, porque ``_safe_close`` se llama desde esa misma recuperación.
    """
    monkeypatch.setattr(engine_mod, "_RECONNECT_BACKOFF_S", 0.01)
    monkeypatch.setattr(engine_mod, "_ERROR_BACKOFF_S", 0.01)
    eng = IncidentEngine(lambda: None, Settings(), poll_s=0.01, lookback_s=300.0)  # type: ignore[arg-type]

    vueltas = {"n": 0}
    # Sin esto el test pasaría trivialmente el día que ninguna pasada tocara la
    # conexión: se exige que la recuperación se haya EJECUTADO de verdad.
    recuperacion = {"rollback": 0, "close": 0}
    sostenido = threading.Event()

    class _ConexionHostil:
        """Conexión que falla en todo, incluso al recogerse los platos rotos."""

        closed = False

        def execute(self, *a: object, **k: object) -> None:
            raise RuntimeError("la pasada revienta")

        def rollback(self) -> None:
            recuperacion["rollback"] += 1
            raise RuntimeError("y el rollback de la recuperación también")

        def close(self) -> None:
            recuperacion["close"] += 1
            raise RuntimeError("y el cierre también")

    def _correlacion(conn: object) -> list[str]:
        vueltas["n"] += 1
        if vueltas["n"] >= _VUELTAS_SOSTENIDAS:
            sostenido.set()
        return []

    monkeypatch.setattr(eng, "_connect_listen", lambda: _ConexionHostil())
    monkeypatch.setattr(eng, "_drain_notifies", lambda lc: None)
    monkeypatch.setattr(eng, "_ensure_work", lambda wc: _ConexionHostil())
    monkeypatch.setattr(eng, "run_correlation", _correlacion)

    t = threading.Thread(target=eng.run)
    t.start()
    try:
        assert sostenido.wait(5.0), (
            f"el bucle murió con la pasada: {vueltas['n']} de {_VUELTAS_SOSTENIDAS} "
            f"vueltas; hilo vivo={t.is_alive()}"
        )
        assert t.is_alive()
        assert recuperacion["rollback"] > 0, (
            "ninguna pasada reventó: el escenario no se ejerció y la guarda no mide nada"
        )
        assert recuperacion["close"] > 0, (
            "el rollback falló pero nadie tiró la conexión: se queda una conexión "
            "en estado desconocido dando vueltas"
        )
    finally:
        eng.stop()
        t.join(timeout=5.0)
    assert not t.is_alive()


def _my_events(scenario: _Scenario) -> int:
    """Eventos de red a los que se linkearon incidentes de ESTE tenant (scoped)."""
    return scenario.conn.execute(
        "SELECT COUNT(DISTINCT event_id) AS n FROM incidents "
        "WHERE tenant_id = %s AND event_id IS NOT NULL",
        (scenario.tenant,),
    ).fetchone()["n"]
