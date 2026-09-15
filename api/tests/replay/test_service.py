"""[T-7.14] Vestir el incidente de reproducción: lo que hace y lo que NO puede hacer.

La mitad de esta suite es lo que **no** ocurre, y es la mitad que importa:

1. **Jamás crea incidentes ni votos de cuórum.** Un `EVT-REP` que abriera
   incidentes convertiría una demostración en una alerta para edificios que no
   sintieron nada; un voto falsificaría la corroboración de la red, que es el
   hecho sobre el que la nube manda comandos FIRMADOS a gabinetes reales.
2. **Sin ventana armada no viste nada.** Ni con el sismo en el catálogo, ni con
   el incidente recién abierto: hace falta que alguien lo haya DECLARADO.
3. **Vencida la ventana, tampoco.** El vencimiento es lo que convierte «armar» en
   una declaración acotada y no en un interruptor que alguien se deja puesto.
4. **No toca un incidente que ya tiene evento.** Pisar el evento de un incidente
   real con una reproducción es el peor fallo imaginable de esta ficha.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.replay.service import (
    PATRON_SITIO_DEMO,
    event_id_de,
    run_replay_pass,
    ventana_viva_sync,
)
from takab_api.settings import Settings

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
#: Las cifras del 19-S-2017 (solución USGS). La FILA se crea en el escenario en
#: vez de depender del seed `db/seeds/reference_earthquakes.sql`: una prueba que
#: necesita que alguien haya sembrado pasa o falla por algo que no está probando.
ORIGEN_REAL = datetime(2017, 9, 19, 18, 14, 38, tzinfo=UTC)
MAGNITUD, PROF_KM, EPI_LAT, EPI_LON = 7.1, 48.0, 18.5499, -98.4887


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


# ───────────────────────────────────────────────── el espejo del patrón


def test_el_patron_de_sitio_DEMO_es_el_mismo_que_el_de_la_consola() -> None:
    """Dos listas escritas a mano en dos lenguajes divergen; ésta no puede.

    Rotular de demostración un edificio real —o dejar de rotular uno simulado— es
    el error caro de los dos lados: aquí decide si se puede armar una
    reproducción; allí, si el operador ve la cinta amarilla.
    """
    fuente = (
        Path(__file__).resolve().parents[3] / "web/src/features/fleet/datosDeDemostracion.ts"
    ).read_text(encoding="utf-8")
    patrones = re.findall(r"/\^([^/]+)\$/", fuente)
    assert patrones, "el bloque de patrones de la consola se movió: esto no mide nada"
    # El de sitios, traducido de la sintaxis de JS (`\d`) a la de Postgres (`[0-9]`).
    sitios = [p for p in patrones if p.startswith("site-")]
    assert len(sitios) == 1, sitios
    equivalente = "^" + sitios[0].replace(r"\d", "[0-9]") + "$"
    assert equivalente == PATRON_SITIO_DEMO, (
        f"la consola usa {equivalente!r} y el servidor {PATRON_SITIO_DEMO!r}"
    )


def test_el_id_del_evento_es_DETERMINISTA_y_por_minuto() -> None:
    """Dos gabinetes del mismo pulso comparten evento: un sismo, un evento."""
    t = uuid.uuid4().hex
    a = event_id_de(t, "K", datetime(2026, 9, 15, 12, 0, 1, tzinfo=UTC))
    b = event_id_de(t, "K", datetime(2026, 9, 15, 12, 0, 59, tzinfo=UTC))
    c = event_id_de(t, "K", datetime(2026, 9, 15, 12, 1, 0, tzinfo=UTC))
    assert a == b and a != c
    assert a.startswith("EVT-REP-")


# ──────────────────────────────────────────────────── contra la base


@dataclass
class Escenario:
    conn: psycopg.Connection
    tenant: str
    site_real: str
    site_demo: str
    catalogo: str

    def armar(
        self, *, hasta: datetime, desde: datetime | None = None, catalog_key: str | None = None
    ) -> None:
        """⚠️ `desde` y `hasta` tienen que salir del MISMO reloj.

        El CHECK de la tabla exige `armed_until <= armed_at + 8h`. Mezclar el
        `NOW` fijo de estas pruebas con el reloj real hace que la fila pase o
        reviente **según la hora del día**: con `armed_at` a las 11:55 del NOW
        fijo, cualquier `armed_until` posterior a las 19:55 reales viola el
        CHECK. Lo descubrió CI corriendo de noche, no la corrida local.
        """
        self.conn.execute(
            "INSERT INTO demo_replay (tenant_id, catalog_key, armed_by, armed_at, armed_until)"
            " VALUES (%s,%s,gen_random_uuid(),%s,%s)"
            " ON CONFLICT (tenant_id) DO UPDATE SET armed_at = EXCLUDED.armed_at,"
            " armed_until = EXCLUDED.armed_until, catalog_key = EXCLUDED.catalog_key",
            (
                self.tenant,
                catalog_key or self.catalogo,
                desde if desde is not None else NOW - timedelta(minutes=5),
                hasta,
            ),
        )
        self.conn.commit()

    def incidente(
        self, *, trigger: str = "sasmex", abierto_hace_s: float = 30.0, event_id: str | None = None
    ) -> str:
        inc = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,"
            " opened_at, severity, state, trigger) VALUES (%s, gen_random_uuid(), %s, %s, %s,"
            " %s, 'critical', 'open', %s)",
            (
                inc,
                self.tenant,
                self.site_real,
                event_id,
                NOW - timedelta(seconds=abierto_hace_s),
                trigger,
            ),
        )
        self.conn.commit()
        return inc

    def evento_de(self, inc: str) -> dict | None:
        return self.conn.execute(
            "SELECT e.event_id, e.source, e.magnitude, e.depth_km, e.detected_at, e.meta,"
            " ST_Y(e.epicenter::geometry) AS lat, ST_X(e.epicenter::geometry) AS lon"
            " FROM incidents i JOIN seismic_events e ON e.event_id = i.event_id"
            " WHERE i.incident_id = %s",
            (inc,),
        ).fetchone()

    def cuantos_incidentes(self) -> int:
        return self.conn.execute(
            "SELECT count(*) AS n FROM incidents WHERE tenant_id = %s", (self.tenant,)
        ).fetchone()["n"]

    def cuantos_votos(self) -> int:
        return self.conn.execute(
            "SELECT count(*) AS n FROM quorum_votes v"
            " JOIN seismic_events e ON e.event_id = v.event_id"
            " WHERE e.event_id LIKE 'EVT-REP-%%'"
        ).fetchone()["n"]

    def pasada(self, *, now: datetime = NOW):
        self.conn.execute('SET ROLE "takab_ingest"')
        try:
            return run_replay_pass(self.conn, Settings(), now=now, lookback_s=300.0)
        finally:
            self.conn.execute("RESET ROLE")
            self.conn.commit()


@pytest.fixture
def esc() -> Iterator[Escenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant, real, demo, gw_r, gw_d = (str(uuid.uuid4()) for _ in range(5))
    catalogo = f"T714-{uuid.uuid4().hex[:8]}"
    try:
        conn.execute(
            "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
            " epicenter, depth_km, source, source_ref) VALUES (%s,%s,%s,'19-S 2017 (fixture)',"
            " ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,'USGS','fixture T-7.14')",
            (catalogo, ORIGEN_REAL, MAGNITUD, EPI_LON, EPI_LAT, PROF_KM),
        )
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility)"
            " VALUES (%s,%s,'Reproducción T-7.14','private')",
            (tenant, tenant[:8]),
        )
        # Un sitio REAL (el gabinete que da el pulso) y uno de DEMOSTRACIÓN, que
        # es lo que habilita armar. Coordenadas de Puebla y Tlaxcala.
        for sid, code, lat, lon in (
            (real, f"{tenant[:8]}-real", 19.05, -98.22),
            (demo, "site-sim-101", 19.3139, -98.2404),
        ):
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'Sitio',ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
                (sid, tenant, code, lon, lat),
            )
        for gid, sid in ((gw_r, real), (gw_d, demo)):
            conn.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status)"
                " VALUES (%s,%s,%s,%s,'online')",
                (gid, tenant, sid, f"SER-{gid[:8]}"),
            )
        conn.commit()
        yield Escenario(conn, tenant, real, demo, catalogo)
    finally:
        _limpiar(conn, tenant, catalogo)
        conn.close()


def _limpiar(conn: psycopg.Connection, tenant: str, catalogo: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        eventos = [
            r["event_id"]
            for r in conn.execute(
                "SELECT DISTINCT event_id FROM incidents"
                " WHERE tenant_id = %s AND event_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        ]
        for tabla in ("incident_actions", "incidents", "demo_replay", "audit_log"):
            conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (tenant,))
        if eventos:
            conn.execute("DELETE FROM quorum_votes WHERE event_id = ANY(%s)", (eventos,))
            conn.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (eventos,))
        for tabla in ("gateways", "sites", "tenants"):
            conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM reference_earthquakes WHERE catalog_key = %s", (catalogo,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def test_con_la_ventana_ARMADA_el_incidente_queda_vestido(esc: Escenario) -> None:
    esc.armar(hasta=NOW + timedelta(hours=1))
    inc = esc.incidente()

    resultado = esc.pasada()

    assert inc in resultado.vestidos
    ev = esc.evento_de(inc)
    assert ev is not None, "el incidente se quedó sin evento enlazado"
    assert ev["event_id"].startswith("EVT-REP-")
    assert ev["source"] == "external"
    assert float(ev["magnitude"]) == pytest.approx(MAGNITUD)
    assert float(ev["depth_km"]) == pytest.approx(PROF_KM)
    assert float(ev["lat"]) == pytest.approx(EPI_LAT, abs=1e-4)


def test_el_evento_lleva_el_ROTULO_y_las_dos_horas(esc: Escenario) -> None:
    """`meta.reproduccion` no se borra: después siempre se puede saber qué
    incidentes se vistieron de demostración."""
    esc.armar(hasta=NOW + timedelta(hours=1))
    inc = esc.incidente()

    esc.pasada()

    meta = esc.evento_de(inc)["meta"]
    rep = meta["reproduccion"]
    assert rep["catalog_key"] == esc.catalogo
    assert rep["t0_real"].startswith("2017-09-19")
    assert rep["t0_demo"].startswith("2026-09-15")
    # El conteo va PEGADO al rótulo: nadie puede leer la corroboración sin ver
    # que es una reproducción.
    assert meta["node_count"] == 2, "las dos estaciones del cliente"


def test_JAMAS_crea_incidentes_ni_votos_de_cuorum(esc: Escenario) -> None:
    """La guarda de la ficha. Un `EVT-REP` que abriera incidentes convertiría una
    demostración en una alerta para edificios que no sintieron nada."""
    esc.armar(hasta=NOW + timedelta(hours=1))
    inc = esc.incidente()
    antes = esc.cuantos_incidentes()

    esc.pasada()

    assert esc.cuantos_incidentes() == antes, "la reproducción abrió un incidente"
    assert esc.cuantos_votos() == 0, "la reproducción falsificó corroboración de red"
    assert esc.evento_de(inc) is not None  # control: la pasada SÍ hizo su trabajo


def test_SIN_ventana_armada_no_viste_nada(esc: Escenario) -> None:
    inc = esc.incidente()

    resultado = esc.pasada()

    assert resultado.vestidos == []
    assert esc.evento_de(inc) is None


def test_con_la_ventana_VENCIDA_tampoco(esc: Escenario) -> None:
    """El vencimiento es lo que hace de «armar» una declaración acotada."""
    esc.armar(hasta=NOW - timedelta(seconds=1))
    inc = esc.incidente()

    esc.pasada()

    assert esc.evento_de(inc) is None


def test_no_toca_un_incidente_que_YA_tiene_evento(esc: Escenario) -> None:
    """Pisar el evento de un incidente real con una reproducción es el peor fallo
    imaginable de esta ficha."""
    esc.conn.execute(
        "INSERT INTO seismic_events (event_id, source, detected_at) "
        "VALUES ('EVT-REAL-T714','local_quorum',%s) ON CONFLICT DO NOTHING",
        (NOW,),
    )
    esc.conn.commit()
    esc.armar(hasta=NOW + timedelta(hours=1))
    inc = esc.incidente(event_id="EVT-REAL-T714")

    esc.pasada()

    assert esc.evento_de(inc)["event_id"] == "EVT-REAL-T714"


def test_solo_viste_incidentes_del_WR1(esc: Escenario) -> None:
    """Un incidente instrumental no es el pulso de la demostración."""
    esc.armar(hasta=NOW + timedelta(hours=1))
    instrumental = esc.incidente(trigger="local_threshold")

    esc.pasada()

    assert esc.evento_de(instrumental) is None


def test_la_pasada_es_IDEMPOTENTE(esc: Escenario) -> None:
    esc.armar(hasta=NOW + timedelta(hours=1))
    inc = esc.incidente()

    primera = esc.pasada()
    segunda = esc.pasada()

    assert inc in primera.vestidos
    assert segunda.vestidos == []
    assert esc.evento_de(inc) is not None


def test_la_ventana_viva_se_LEE_con_el_rol_del_worker(esc: Escenario) -> None:
    """Si faltara el GRANT, el worker moriría en cada pasada — y en local no.

    La ventana se arma contra el reloj REAL y no contra `NOW`: esta consulta la
    resuelve la base con su `now()`, que es lo correcto —el vencimiento no puede
    depender del reloj del proceso— y lo que obliga a que la prueba lo respete.
    """
    ahora = datetime.now(tz=UTC)
    esc.armar(desde=ahora - timedelta(minutes=5), hasta=ahora + timedelta(hours=1))
    esc.conn.execute('SET ROLE "takab_ingest"')
    try:
        ventana = ventana_viva_sync(esc.conn, esc.tenant)
    finally:
        esc.conn.execute("RESET ROLE")
    assert ventana is not None and ventana.catalog_key == esc.catalogo
