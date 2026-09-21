"""T-7.24 · La pasada del worker que calcula el mini-ShakeMap, CONTRA LA BASE.

Ésta es la suite que importa. `test_calculo.py` ejerce la física con datos
inyectados a mano y pasaría en verde con la pasada entera desconectada; aquí se
siembra una red real en `takab_test_a`, se corre la pasada **con el rol del
worker** y se lee lo que quedó escrito.

Lo que fija, por lo que costaría equivocarse:

1. **Las features se leen con el contexto de tenant puesto.** La tabla por
   estación lee `waveform_features_1s_secure`, una vista `security_barrier`
   cuyo JOIN a `sites` se evalúa con la RLS del DUEÑO de la vista. El worker es
   `takab_ingest` (BYPASSRLS) y eso **no le vale**: sin `app.tenant_id` la
   vista devuelve cero filas y todos los mapas saldrían `sin_datos` —un no-op
   perfectamente silencioso—. Lo cazan `test_el_snapshot_recoge_lo_medido` y
   `test_no_se_cuelan_las_features_de_otro_cliente`.
2. **Con el rol del worker, no como superusuario.** Sin los `GRANT` de la 0069
   la pasada muere con `permission denied` — el defecto que este repositorio ya
   pagó dos veces, porque verde en local no es verde en la nube.
3. **Idempotencia** (regla de oro 3): recalcular no duplica ni corrompe, y la
   fecha del cálculo sí se refresca porque aquí esa fecha ES el dato.
4. **Converge.** Un `completo` no se vuelve a calcular jamás; un
   `solo_observado` sí, con su propio reloj, porque puede llegarle el epicentro.
5. **No bloquea el bucle** más allá de su presupuesto de reloj de pared, que es
   la trampa que T-7.25 midió: lo que esta pasada tarda es lo que se retrasa la
   correlación, el dictamen y las fases de la vuelta siguiente.

Las cifras sísmicas salen del Puebla-Morelos 2017 con la solución USGS que el
repositorio ya cita (18.5499 N, −98.4887 W, 48 km, M7.1).
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.geo import haversine_km, hypo_km, pga_law_g
from takab_api.schemas.shakemap import PuntoProps
from takab_api.settings import Settings
from takab_api.shakemap import calculo as C
from takab_api.shakemap import servicio as S
from tests.catalogo.fixtures import dsn

# --- el sismo, con su procedencia ---------------------------------------------
EPI_LAT, EPI_LON, PROF_KM, MAG = 18.5499, -98.4887, 48.0, 7.1
ORIGEN = datetime(2017, 9, 19, 18, 14, 38, 90000, tzinfo=UTC)
ABIERTO = ORIGEN + timedelta(seconds=40)
NOW = ABIERTO + timedelta(minutes=30)

# Dos inmuebles reales de la red de demostración (`db/seeds/demo_red.sql`).
CDMX = (19.4326, -99.1332)
PUEBLA = (19.3139, -98.2404)

#: Lo que se siembra como pico medido en cada uno. El de la Ciudad de México va
#: a propósito por ENCIMA de lo que la ley predice a su distancia: el residuo
#: positivo es el producto de la ficha y tiene que llegar hasta la tabla.
PGA_CDMX = 0.086
PGA_PUEBLA = 0.012
#: Y su PGV, que viaja por el MISMO camino desde `T-7.24`: el contrato la promete
#: y el PDF del dictamen le imprime una columna.
PGV_CDMX = 6.4

#: Una banda del inmueble a propósito DISTINTA de la de fábrica (0.040 / 0.060),
#: para que un `Thresholds()` clavado en el código —o cualquier número tecleado—
#: se ponga rojo. Los dos niveles siguen cortando la superficie con el M7.1 de
#: referencia (55.0 y 163.5 km), así que la guarda mide los VALORES y no la
#: supresión.
BANDA_DEL_INMUEBLE = {"pga_watch_g": 0.033, "pga_trip_g": 0.077}


def _settings(**over) -> Settings:
    """Los ajustes del worker, apuntando a la base de ESTA suite.

    ⚠️ `database_url` se fija a mano y no es cosmético: el puente async de la
    pasada abre su conexión con `settings.database_url`, que en producción es la
    DSN de `takab_ingest`. Aquí `Settings()` caería a su DSN de desarrollo —otra
    base— mientras el resto de la suite usa `DATABASE_URL`. Son DOS variables
    distintas (`TAKAB_API_DATABASE_URL` y `DATABASE_URL`) y el puente las cruzaba
    en silencio: los candidatos se leían de esta base y la tabla por estación de
    la otra, así que TODO salía sin calcular y sin un solo error.
    """
    return Settings(
        **{"database_url": dsn().replace("postgresql://", "postgresql+psycopg://", 1), **over}
    )


@dataclass
class Escenario:
    conn: psycopg.Connection
    tenant: str
    sitios: dict[str, str]  # code -> site_id

    # ------------------------------------------------------------- siembra
    def incidente(
        self,
        *,
        code: str = "CDMX",
        en_revision: bool = True,
        cuando: datetime = ABIERTO,
        magnitud: float | None = MAG,
        con_epicentro: bool = True,
    ) -> str:
        inc = str(uuid.uuid4())
        event_id = None
        if con_epicentro:
            event_id = f"EVT-{inc[:8]}"
            self.conn.execute(
                "INSERT INTO seismic_events (event_id, source, epicenter, magnitude,"
                " depth_km, detected_at, meta) VALUES (%s,'external',"
                " ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s,%s,'{}'::jsonb)",
                (event_id, EPI_LON, EPI_LAT, magnitud, PROF_KM, ORIGEN),
            )
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
            " severity, state, trigger, event_id) VALUES (%s, gen_random_uuid(), %s, %s, %s,"
            " 'critical', %s, 'sasmex', %s)",
            (
                inc,
                self.tenant,
                self.sitios[code],
                cuando,
                "in_review" if en_revision else "open",
                event_id,
            ),
        )
        if en_revision:
            # La huella que deja `transition_incident`, que es lo que mira la pasada.
            self.conn.execute(
                "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor)"
                " VALUES (%s,%s,%s,'in_review','system:incident')",
                (inc, self.tenant, cuando + timedelta(minutes=5)),
            )
        self.conn.commit()
        return inc

    def mide(
        self,
        code: str,
        pga_g: float,
        *,
        pgv_cms: float | None = None,
        cuando: datetime | None = None,
    ) -> None:
        """Un segundo de features en la ventana del incidente."""
        self.conn.execute(
            "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel,"
            " pga_g, pgv_cms) VALUES (%s,%s,%s,%s,'ENZ',%s,%s) ON CONFLICT DO NOTHING",
            (
                cuando or ABIERTO + timedelta(seconds=30),
                self.tenant,
                self.sitios[code],
                self.sensor(code),
                pga_g,
                pgv_cms,
            ),
        )
        self.conn.commit()

    def sensor(self, code: str) -> str:
        return self.conn.execute(
            "SELECT sensor_id FROM sensors WHERE site_id = %s", (self.sitios[code],)
        ).fetchone()["sensor_id"]

    def banda(self, code: str, **umbrales: float) -> None:
        """Los umbrales DEL INMUEBLE, por donde el sistema los lee de verdad.

        `rule_sets` con `config.edge.thresholds` y `scope_type='site'`, que es lo
        que resuelve `umbral_de_comparacion` — el mismo resolvedor que usan la
        tabla por estación y el dictamen. Sembrarlo por otra vía probaría otra
        cosa.
        """
        self.conn.execute(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active,"
            " config, created_at) VALUES (%s,'site',%s,1,true,%s::jsonb,%s)",
            (
                self.tenant,
                self.sitios[code],
                json.dumps({"edge": {"thresholds": umbrales}}),
                ABIERTO - timedelta(days=1),
            ),
        )
        self.conn.commit()

    def vota(self, inc: str, code: str, *, counted: bool = True) -> None:
        """El voto de cuórum de ese inmueble para el evento del incidente."""
        event_id = self.conn.execute(
            "SELECT event_id FROM incidents WHERE incident_id = %s", (inc,)
        ).fetchone()["event_id"]
        self.conn.execute(
            "INSERT INTO quorum_votes (event_id, sensor_id, detected_at, pga_g, counted)"
            " VALUES (%s,%s,%s,%s,%s)",
            (event_id, self.sensor(code), ABIERTO, PGA_CDMX, counted),
        )
        self.conn.commit()

    def consulta(
        self,
        inc: str,
        *,
        respondida: bool = False,
        outcome: str | None = None,
        catalog_key: str | None = None,
    ) -> None:
        """La huella de `T-7.25`: se le preguntó a la fuente por este incidente."""
        self.conn.execute(
            "INSERT INTO catalog_consultations (incident_id, provider, tenant_id, asked_at,"
            " last_attempt_at, answered_at, outcome, catalog_key)"
            " VALUES (%s,'USGS',%s,%s,%s,%s,%s,%s)",
            (
                inc,
                self.tenant,
                NOW,
                NOW,
                NOW + timedelta(seconds=3) if respondida else None,
                outcome,
                catalog_key,
            ),
        )
        self.conn.commit()

    def siembra_catalogo(self, clave: str, *, review_status: str = "preliminar") -> None:
        self.conn.execute(
            "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
            " epicenter, depth_km, source, source_ref, consulted_at, review_status,"
            " provider_event_id) VALUES (%s,%s,7.1,'Puebla-Morelos',"
            " ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,'USGS','prueba T-7.24',"
            " %s,%s,%s)",
            (clave, ORIGEN, EPI_LON, EPI_LAT, PROF_KM, NOW, review_status, clave),
        )
        self.conn.commit()

    def pone_magnitud(self, inc: str, magnitud: float) -> None:
        self.conn.execute(
            "UPDATE seismic_events SET magnitude = %s WHERE event_id ="
            " (SELECT event_id FROM incidents WHERE incident_id = %s)",
            (magnitud, inc),
        )
        self.conn.commit()

    # ------------------------------------------------------------- lectura
    def snapshot(self, inc: str) -> dict | None:
        self.conn.rollback()
        return self.conn.execute(
            "SELECT incident_id::text, tenant_id::text, calculado_en, estado, ley,"
            " epicentro, cobertura_km::float8 AS cobertura_km, puntos, anillos"
            " FROM incident_shakemap WHERE incident_id = %s",
            (inc,),
        ).fetchone()

    def punto(self, inc: str, code: str) -> dict:
        snap = self.snapshot(inc)
        assert snap is not None
        return next(p for p in snap["puntos"] if p["site_code"].endswith(code))

    # -------------------------------------------------------------- pasada
    def pasada(
        self,
        *,
        now: datetime = NOW,
        maximo: int = S.MAX_POR_PASADA,
        reloj: Callable[[], float] = time.monotonic,
        **over,
    ) -> S.PasadaDeShakemap:
        """Corre la pasada CON EL ROL DEL WORKER, no como superusuario.

        Es lo que verifica que los `GRANT` de la 0069 existen: sin ellos la
        pasada muere con `permission denied`, que en local es verde sólo porque
        el DSN de los tests es el superusuario.
        """
        self.conn.execute('SET ROLE "takab_ingest"')
        try:
            return S.run_shakemap_pass(
                self.conn,
                _settings(**over),
                now=now,
                max_por_pasada=maximo,
                reloj=reloj,
            )
        finally:
            self.conn.execute("RESET ROLE")
            self.conn.commit()


@pytest.fixture
def esc() -> Iterator[Escenario]:
    conn = psycopg.connect(dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    sitios: dict[str, str] = {}
    try:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility)"
            " VALUES (%s,%s,'ShakeMap T-7.24','private')",
            (tenant, tenant[:8]),
        )
        for code, (lat, lon) in (("CDMX", CDMX), ("PUEBLA", PUEBLA)):
            site = str(uuid.uuid4())
            sitios[code] = site
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES"
                " (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
                (site, tenant, f"{tenant[:8]}-{code}", f"Inmueble {code}", lon, lat),
            )
            gw = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status)"
                " VALUES (%s,%s,%s,%s,'online')",
                (gw, tenant, site, f"GW-{site[:8]}"),
            )
            conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model,"
                " serial) VALUES (gen_random_uuid(),%s,%s,%s,'structural','RS4D',%s)",
                (tenant, site, gw, f"SIM-{site[:8]}"),
            )
        conn.commit()
        yield Escenario(conn, tenant, sitios)
    finally:
        _limpiar(conn, tenant)
        conn.close()


def _limpiar(conn: psycopg.Connection, tenant: str) -> None:
    """`incident_actions` es append-only por trigger: el superusuario lo apaga
    para el teardown (sólo en tests; en producción esas filas son inmutables)."""
    conn.rollback()
    conn.execute("RESET ROLE")
    conn.execute("SET session_replication_role = replica")
    conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM incident_shakemap WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM catalog_consultations WHERE tenant_id = %s", (tenant,))
    # El catálogo es GLOBAL (sin `tenant_id`): se borra sólo lo que esta suite
    # escribió, reconocible por su prefijo. Sin esto, la clave única
    # `(source, provider_event_id)` haría chocar la segunda corrida con la primera.
    conn.execute("DELETE FROM reference_earthquakes WHERE catalog_key LIKE 'USGS-T724-%%'")
    conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
    conn.execute(
        "DELETE FROM quorum_votes WHERE sensor_id IN"
        " (SELECT sensor_id FROM sensors WHERE tenant_id = %s)",
        (tenant,),
    )
    conn.execute(
        "DELETE FROM seismic_events WHERE event_id IN"
        " (SELECT event_id FROM incidents WHERE tenant_id = %s AND event_id IS NOT NULL)",
        (tenant,),
    )
    conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM gateways WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
    conn.execute("SET session_replication_role = origin")
    conn.commit()


# --------------------------------------------------------- el camino completo


def test_el_snapshot_recoge_lo_medido_lo_modelado_y_el_residuo(esc: Escenario) -> None:
    """El camino entero: features sembradas ⇒ tres capas escritas en la tabla.

    ⚠️ Si la pasada se olvidara de fijar `app.tenant_id`, la vista segura de
    features devolvería cero filas y esto saldría `sin_datos` sin un solo error.
    """
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.mide("PUEBLA", PGA_PUEBLA)

    assert esc.pasada().calculados == (inc,)

    snap = esc.snapshot(inc)
    assert snap is not None
    assert snap["estado"] == C.ESTADO_COMPLETO
    assert snap["ley"] == C.LEY
    assert snap["tenant_id"] == esc.tenant
    assert snap["cobertura_km"] == 5.0

    cdmx = esc.punto(inc, "CDMX")
    assert cdmx["procedencia"] == C.PROC_MEDIDO
    assert cdmx["pga_g"] == pytest.approx(PGA_CDMX, rel=1e-5)
    # La distancia y el modelo, derivados de la MISMA ley que usa el sistema.
    dist = haversine_km(EPI_LAT, EPI_LON, *CDMX)
    esperada = pga_law_g(MAG, hypo_km(dist, PROF_KM))
    assert cdmx["dist_km"] == pytest.approx(dist, rel=1e-6)
    assert cdmx["pga_g_modelada"] == pytest.approx(esperada, rel=1e-6)
    assert cdmx["residuo_log10"] == pytest.approx(math.log10(PGA_CDMX / esperada), abs=1e-4)
    assert cdmx["residuo_log10"] > 0, "la Ciudad de México sacudió MÁS de lo predicho"

    # Y la capa 2, en kilómetros y con los umbrales con que el sistema decide.
    assert {a["umbral"] for a in snap["anillos"]} == set(C.UMBRALES)
    assert all(a["radio_km"] > 0 for a in snap["anillos"])
    # El radio que se ESCRIBE es el que despeja la ley de este sismo, no un
    # número cualquiera mayor que cero: sin esto, un anillo de 5 623 km —el que
    # producía el piso de coherencia de T-5.11 antes del 2026-09-21— pasaba la
    # guarda tan campante.
    for anillo in snap["anillos"]:
        # ⚠️ Se comprueba con la ley HACIA ADELANTE (`pga_law_g`), no volviendo a
        # despejar con la misma función que escribió el radio: eso sería
        # preguntarle al acusado. Si el anillo afirma 0.040 g, la ley evaluada a
        # su radio tiene que devolver 0.040 g.
        assert pga_law_g(MAG, hypo_km(anillo["radio_km"], PROF_KM)) == pytest.approx(
            anillo["pga_g"], rel=1e-6
        )
        assert anillo["radio_km"] <= Settings().correlation_max_km


def test_los_niveles_de_los_anillos_son_los_umbrales_DEL_INMUEBLE(esc: Escenario) -> None:
    """⚠️ La guarda del hallazgo ALTO, y media ficha: «son los umbrales con que
    ESTE sistema ya decide, no una escala inventada».

    Se siembra en `rule_sets` una banda distinta de la de fábrica y se exige que
    los anillos escritos lleven **esos** números. Un valor tecleado en el código
    —el defecto que cerró `T-7.35`: un umbral de fábrica presentado como del
    edificio— se pone rojo aquí, y también se pondría rojo si alguien volviera a
    colar un nivel que no sale de la banda.
    """
    esc.banda("CDMX", **BANDA_DEL_INMUEBLE)
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()

    anillos = esc.snapshot(inc)["anillos"]
    assert {a["umbral"]: a["pga_g"] for a in anillos} == BANDA_DEL_INMUEBLE, (
        "los niveles del mapa tienen que ser los umbrales del inmueble, leídos "
        "del rule_set que regía en la apertura del incidente"
    )
    assert set(BANDA_DEL_INMUEBLE) == set(C.UMBRALES)


def test_el_radio_de_representatividad_QUE_SE_AJUSTA_es_el_que_se_escribe(
    esc: Escenario,
) -> None:
    """`shakemap_cobertura_km` es configurable a propósito —una red urbana densa
    y una red estatal no tienen el mismo alcance— y el número se guarda EN CADA
    SNAPSHOT para que un mapa impreso no cambie de significado si mañana alguien
    lo sube. Con el valor de fábrica en los dos lados, eso no lo medía nadie."""
    ajustado = Settings().shakemap_cobertura_km * 1.5
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada(shakemap_cobertura_km=ajustado)
    assert esc.snapshot(inc)["cobertura_km"] == pytest.approx(ajustado)


def test_un_nivel_MAS_LEJOS_DEL_TOPE_no_se_dibuja_y_se_declara(esc: Escenario) -> None:
    """⚠️ El otro hallazgo ALTO, medido contra la base.

    ATTEN-LAW v1 es ILUSTRATIVA y su radio no tiene sentido físico a cualquier
    distancia. Con la banda de fábrica, el nivel de cautela (0.040 g) se va a
    1 252.0 km en un M9.0 —más allá del radio con el que este sistema acepta
    atribuirle a un epicentro la sacudida de un edificio (1 200 km,
    `correlation_max_km`)— y el de disparo se queda en 833.9 km. Medido el
    2026-09-21. Así que uno se dibuja y el otro **se declara**: un anillo que
    desaparece en silencio se lee como «ese umbral no existía».
    """
    inc = esc.incidente(magnitud=9.0)
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()

    censo = {a["umbral"]: a for a in esc.snapshot(inc)["anillos"]}
    assert set(censo) == set(C.UMBRALES), "ningún nivel se pierde por el camino"
    assert censo[C.UMBRAL_TRIP]["radio_km"] is not None
    assert censo[C.UMBRAL_TRIP]["motivo"] is None

    lejano = censo[C.UMBRAL_WATCH]
    assert lejano["radio_km"] is None, "no se dibuja lo que el modelo no puede afirmar"
    assert lejano["motivo"] == C.FUERA_DEL_ALCANCE
    assert lejano["radio_max_km"] == pytest.approx(Settings().correlation_max_km), (
        "«fuera del alcance» sin decir de qué alcance no es una afirmación"
    )


def test_el_epicentro_guardado_dice_de_donde_salio(esc: Escenario) -> None:
    """`fuente` (quién lo localizó) y `procedencia` (el estado del glosario) son
    cosas distintas y las dos tienen que estar."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()

    epi = esc.snapshot(inc)["epicentro"]
    assert epi["lat"] == pytest.approx(EPI_LAT, abs=1e-6)
    assert epi["lon"] == pytest.approx(EPI_LON, abs=1e-6)
    assert epi["depth_km"] == pytest.approx(PROF_KM)
    assert epi["magnitud"] == pytest.approx(MAG)
    assert epi["fuente"] == "external"
    # Nadie le preguntó a USGS por este incidente: el estado del glosario lo dice.
    assert epi["procedencia"] == "sin_dato_externo"


def test_el_contrato_del_punto_no_promete_ningun_campo_que_no_pueda_llenar(
    esc: Escenario,
) -> None:
    """Censo DERIVADO del contrato: cada propiedad que `PuntoProps` publica tiene
    que llegar con un valor en un mapa `completo`.

    Es la guarda de `pgv_cms`, que viajó en `null` desde que nació mientras el
    contrato lo prometía y el PDF del dictamen le imprimía una columna; y la del
    voto de cuórum, que la ficha pide por su nombre («puntos observados de
    features **y votos**») y que llega en la misma tabla por estación. Prometer
    un campo que no se puede llenar es peor que no prometerlo, y añadir mañana
    otro sin poder llenarlo pone esto rojo sin que nadie tenga que acordarse.
    """
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX, pgv_cms=PGV_CDMX)
    esc.vota(inc, "CDMX", counted=True)
    esc.pasada()

    cdmx = esc.punto(inc, "CDMX")
    # `lat`/`lon` no son propiedades: son la GEOMETRÍA del feature. El resto sí.
    assert set(cdmx) == set(PuntoProps.model_fields) | {"lat", "lon"}
    vacios = sorted(k for k, v in cdmx.items() if v is None)
    assert vacios == [], f"el contrato promete campos que el cálculo no llena: {vacios}"
    assert cdmx["pgv_cms"] == pytest.approx(PGV_CDMX, rel=1e-5)
    assert cdmx["voto_contado"] is True


def test_un_voto_que_NO_conto_no_es_lo_mismo_que_no_haber_votado(esc: Escenario) -> None:
    """Tres estados y ninguno se confunde: contó, no contó, y no hay cuórum que
    contar. El último es `null` y **no** es «no votó» (regla de oro 7)."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.mide("PUEBLA", PGA_PUEBLA)
    esc.vota(inc, "CDMX", counted=True)
    esc.vota(inc, "PUEBLA", counted=False)
    esc.pasada()
    assert esc.punto(inc, "CDMX")["voto_contado"] is True
    assert esc.punto(inc, "PUEBLA")["voto_contado"] is False

    otro = esc.incidente(con_epicentro=False)  # sin evento no hay votos que contar
    esc.pasada(now=NOW + timedelta(seconds=120))
    assert esc.punto(otro, "CDMX")["voto_contado"] is None


def test_un_inmueble_que_no_publico_nada_no_es_cero_g(esc: Escenario) -> None:
    """Regla de oro 7. El punto existe —el edificio está instrumentado— pero su
    medida es `null`, y su residuo también: no hay contra qué compararlo."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)  # Puebla se queda muda

    esc.pasada()
    puebla = esc.punto(inc, "PUEBLA")
    assert puebla["pga_g"] is None
    assert puebla["residuo_log10"] is None
    # ...pero el modelo SÍ se puede afirmar ahí: depende sólo de la distancia.
    assert puebla["pga_g_modelada"] is not None


def test_no_se_cuelan_las_features_de_otro_cliente(esc: Escenario) -> None:
    """Multi-tenant por diseño (regla de oro 5). Un pico enorme de otro cliente
    en el mismo segundo no puede aparecer en este mapa ni mover su residuo."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)

    otro = str(uuid.uuid4())
    otro_site = str(uuid.uuid4())
    esc.conn.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility)"
        " VALUES (%s,%s,'Vecino T-7.24','private')",
        (otro, otro[:8]),
    )
    esc.conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES"
        " (%s,%s,%s,'Vecino',ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
        (otro_site, otro, f"{otro[:8]}-V", CDMX[1], CDMX[0]),
    )
    esc.conn.execute(
        "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g)"
        " VALUES (%s,%s,%s,gen_random_uuid(),'ENZ',9.9)",
        (ABIERTO + timedelta(seconds=30), otro, otro_site),
    )
    esc.conn.commit()
    try:
        esc.pasada()
        snap = esc.snapshot(inc)
        assert {p["site_code"].split("-")[-1] for p in snap["puntos"]} == {"CDMX", "PUEBLA"}
        assert esc.punto(inc, "CDMX")["pga_g"] == pytest.approx(PGA_CDMX, rel=1e-5)
    finally:
        esc.conn.rollback()
        esc.conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (otro,))
        esc.conn.execute("DELETE FROM sites WHERE tenant_id = %s", (otro,))
        esc.conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (otro,))
        esc.conn.commit()


# ------------------------------------------------------------- idempotencia


def test_recalcular_no_duplica_ni_corrompe(esc: Escenario) -> None:
    """Regla de oro 3. La clave natural es el incidente y es la PRIMARY KEY."""
    inc = esc.incidente(magnitud=None)  # se queda `solo_observado` ⇒ recalculable
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    primera = esc.snapshot(inc)

    despues = NOW + timedelta(seconds=120)
    assert esc.pasada(now=despues).calculados == (inc,)

    filas = esc.conn.execute(
        "SELECT count(*) AS n FROM incident_shakemap WHERE incident_id = %s", (inc,)
    ).fetchone()["n"]
    assert filas == 1
    segunda = esc.snapshot(inc)
    assert segunda["estado"] == primera["estado"]
    assert segunda["puntos"] == primera["puntos"]
    # La fecha del cálculo SÍ se refresca: aquí esa fecha ES el dato (dice con
    # qué información se hizo el mapa), a diferencia de `fw_releases.released_at`.
    assert segunda["calculado_en"] > primera["calculado_en"]


def test_un_mapa_completo_no_se_vuelve_a_calcular(esc: Escenario) -> None:
    """Converge. Con epicentro, magnitud y medidas el mapa ya no puede mejorar, y
    recalcularlo sería gastar el bucle en confirmar lo mismo cada cinco segundos."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    assert esc.pasada().calculados == (inc,)
    assert esc.pasada(now=NOW + timedelta(hours=1)).calculados == ()


def test_el_degradado_se_rehace_cuando_llega_la_magnitud(esc: Escenario) -> None:
    """§A.4: «aparece cuando hay con qué calcularlo, y mientras tanto lo dice»."""
    inc = esc.incidente(magnitud=None)
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()

    degradado = esc.snapshot(inc)
    assert degradado["estado"] == C.ESTADO_SOLO_OBSERVADO
    assert degradado["ley"] is None, "sin capa 2 no se cita la ley que no se aplicó"
    assert degradado["anillos"] == []
    assert degradado["epicentro"]["magnitud"] is None

    esc.pone_magnitud(inc, MAG)
    assert esc.pasada(now=NOW + timedelta(seconds=120)).calculados == (inc,)
    assert esc.snapshot(inc)["estado"] == C.ESTADO_COMPLETO


def test_el_refresco_tiene_su_propio_reloj(esc: Escenario) -> None:
    """«Puede cambiar» es una afirmación con caducidad, no una invitación a
    recalcular en cada vuelta del bucle (mismo patrón que el preliminar de USGS)."""
    inc = esc.incidente(magnitud=None)
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    # Dentro del refresco: no se toca.
    assert esc.pasada(now=NOW + timedelta(seconds=10)).calculados == ()
    # Pasado el refresco: sí.
    assert esc.pasada(now=NOW + timedelta(seconds=120)).calculados == (inc,)


# ------------------------------------------------------------ la candidatura


def test_un_incidente_que_no_entro_en_revision_no_tiene_mapa(esc: Escenario) -> None:
    """Se calcula cuando hay algo que mirar, no en el segundo del disparo. Un
    mapa pintado a medias durante la sacudida se lee como verdad y no lo es."""
    inc = esc.incidente(en_revision=False)
    esc.mide("CDMX", PGA_CDMX)
    assert esc.pasada().calculados == ()
    assert esc.snapshot(inc) is None


def test_sin_medidas_el_mapa_existe_y_declara_que_no_hay_datos(esc: Escenario) -> None:
    """No calcular nada dejaría al lector en `pendiente` para siempre, que es
    «todavía no» — y aquí la respuesta es «ya miré y no hay».

    ⚠️ Y con cero medidas **no se publica la capa modelada** (`§A.3`: «la capa 2
    sola no aporta nada que no se calcule con una regla de tres»). Hasta el
    2026-09-21 este mismo caso escribía en la base `ley`, epicentro y tres
    anillos —el mayor, de 5 623.2 km— sobre ninguna medición: un mapa de puro
    modelo presentado como el mapa de la sacudida.
    """
    inc = esc.incidente()
    assert esc.pasada().calculados == (inc,)

    snap = esc.snapshot(inc)
    assert snap["estado"] == C.ESTADO_SIN_DATOS
    assert snap["ley"] is None, "no se cita la ley que no se aplicó"
    assert snap["anillos"] == []
    assert all(p["pga_g_modelada"] is None for p in snap["puntos"])
    # El epicentro SÍ se queda: no es la capa 2, es el hecho externo que la
    # anclaría, y con su procedencia. Retirarlo dejaría al operador sin saber
    # siquiera de qué sismo no se midió nada.
    assert snap["epicentro"] is not None


def test_sin_evento_enlazado_el_mapa_es_solo_observado(esc: Escenario) -> None:
    inc = esc.incidente(con_epicentro=False)
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    snap = esc.snapshot(inc)
    assert snap["estado"] == C.ESTADO_SOLO_OBSERVADO
    assert snap["epicentro"] is None
    assert snap["anillos"] == []


# ---------------------------------------------- lo que le cuesta al bucle


def test_la_pasada_no_bloquea_el_bucle_mas_alla_de_su_presupuesto(esc: Escenario) -> None:
    """La trampa que T-7.25 midió: el bucle del worker es serial y lo que esta
    pasada tarda es lo que se retrasa la correlación, el dictamen y las fases.

    El reloj es falso y monótono: arranca en 0 y, cuando la pasada va a empezar el
    SEGUNDO incidente, le dice que ya han pasado 6 s. Con un presupuesto de 5 s
    sólo cabe el primero —el primero siempre se calcula, porque si no un
    presupuesto mal puesto convertiría la pasada en un no-op silencioso— y el
    corte se DICE en vez de dejar candidatos sin explicación.
    """
    for _ in range(3):
        inc = esc.incidente(magnitud=None)
        esc.mide("CDMX", PGA_CDMX)
    marcas = iter([0.0, 6.0, 12.0, 18.0, 24.0])

    pasada = esc.pasada(reloj=lambda: next(marcas), shakemap_presupuesto_s=5.0)
    assert len(pasada.calculados) == 1
    assert pasada.corte == S.CORTE_POR_PRESUPUESTO
    assert pasada.truncada
    assert inc  # el resto entra en la vuelta siguiente, que llega en segundos


def test_el_tope_por_pasada_se_declara(esc: Escenario) -> None:
    """`tope` («había más de los que se traen») y `presupuesto` («se acabó el
    reloj») son cosas distintas y ninguna es un error; lo que no puede pasar es
    que no se digan."""
    for _ in range(3):
        esc.incidente(magnitud=None)
    pasada = esc.pasada(maximo=2)
    assert len(pasada.calculados) == 2
    assert pasada.corte == S.CORTE_POR_TOPE


def test_si_otra_instancia_tiene_el_cerrojo_la_pasada_lo_DICE(esc: Escenario) -> None:
    """Un no-op silencioso es el modo de fallo más caro de este repositorio."""
    inc = esc.incidente()
    otra = psycopg.connect(dsn(), autocommit=False, row_factory=dict_row)
    try:
        otra.execute("SELECT pg_advisory_xact_lock(%s)", (S.LOCK_KEY,))
        pasada = esc.pasada()
        assert pasada.calculados == ()
        assert pasada.corte == S.CORTE_POR_CERROJO
        assert esc.snapshot(inc) is None
    finally:
        otra.rollback()
        otra.close()


def test_el_puente_lee_con_el_rol_DEL_WORKER_y_el_tenant_del_incidente(
    esc: Escenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos líneas del puente que no se ven en ningún resultado, medidas.

    * **El rol.** En producción el DSN ya es de `takab_ingest`; en local es el
      superusuario, así que sin el `SET LOCAL ROLE` esta suite ejercería
      privilegios que la nube no tiene y los `GRANT` de la 0069 no estarían
      probados. Esa clase de verde ya costó un despliegue en este repositorio.
    * **El contexto de tenant.** `waveform_features_1s_secure` es una vista
      `security_barrier` cuyo JOIN a `sites` se evalúa con la RLS del DUEÑO de
      la vista, que no tiene BYPASSRLS: sin `app.tenant_id` devuelve cero filas.

    Se espía la conexión que el puente le pasa a la tabla por estación, que es
    el único sitio donde los dos hechos son observables a la vez.
    """
    from sqlalchemy import text as _text

    real = S.build_estaciones
    visto: list[tuple[str, str | None]] = []

    async def espia(conn, incident_id, settings=None):  # noqa: ANN001, ANN202
        fila = (
            await conn.execute(
                # ⚠️ Los alias NO son `u`/`t`: `Row.t` está deprecado en SQLAlchemy
                # 2 (colisiona con `Row._t`) y devuelve el objeto interno, así que
                # la comparación pasaba a ser contra una tupla y no contra el GUC.
                _text(
                    "SELECT current_user AS rol,"
                    " current_setting('app.tenant_id', true) AS inquilino"
                )
            )
        ).first()
        visto.append((fila.rol, fila.inquilino))
        return await real(conn, incident_id, settings)

    monkeypatch.setattr(S, "build_estaciones", espia)
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    assert esc.pasada().calculados == (inc,)
    assert visto == [("takab_ingest", esc.tenant)]


# ------------------------------------- la procedencia del epicentro, sin inventar


def test_una_consulta_EN_VUELO_deja_el_epicentro_en_consultando(esc: Escenario) -> None:
    """⚠️ La rama que se escapa si el mapa sólo mira si hubo RESPUESTA.

    `catalog_consultations` con `answered_at` NULL significa «se preguntó y
    todavía no contestó». Si el snapshot lo leyera como `sin_dato_externo`
    —«nadie preguntó nunca»— estaría diciendo lo contrario de lo que pasó, que es
    exactamente la confusión que `T-7.25` existe para impedir. Y no se ve en
    ninguna otra prueba porque en ese caso no hay ni `outcome` ni `catalog_key`.
    """
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.consulta(inc)  # preguntada, sin respuesta todavía

    esc.pasada()
    assert esc.snapshot(inc)["epicentro"]["procedencia"] == "consultando"


def test_una_consulta_sin_correlacion_se_declara(esc: Escenario) -> None:
    """«Hay eventos en el catálogo y ninguno es el nuestro» es un HECHO sobre el
    evento, no una ausencia de datos."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.consulta(inc, respondida=True, outcome="sin_correlacion")

    esc.pasada()
    assert esc.snapshot(inc)["epicentro"]["procedencia"] == "sin_correlacion"


def test_una_consulta_que_CASO_trae_la_clave_y_el_estado_de_la_fuente(esc: Escenario) -> None:
    """El estado lo manda la FILA del catálogo: casar no concede procedencia."""
    clave = f"USGS-T724-{uuid.uuid4().hex[:8]}"
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.siembra_catalogo(clave, review_status="preliminar")
    esc.consulta(inc, respondida=True, outcome="correlacionado", catalog_key=clave)

    esc.pasada()
    epi = esc.snapshot(inc)["epicentro"]
    assert epi["procedencia"] == "preliminar"
    assert epi["catalog_key"] == clave
