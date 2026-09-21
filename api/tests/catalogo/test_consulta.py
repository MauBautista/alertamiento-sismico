"""T-7.25 · La pasada que le pregunta a USGS por un incidente en revisión.

Lo que fija esta suite, por orden de lo que costaría equivocarse:

1. **Apagada no abre un socket ni escribe una fila.** Es la configuración que se
   despliega, y se comprueba saboteando el cliente HTTP entero: si el camino
   apagado lo tocara, reventaría. Mismo control negativo que
   `tests/narrative/test_openrouter.py`.
2. **El intento se escribe ANTES de la red.** Es todo el mecanismo que hace
   alcanzable `consultando`: un worker que muere con la pregunta en vuelo tiene
   que dejar «pregunté», no «nadie preguntó nunca». Se mide matando el proceso a
   mitad (una excepción que el worker NO captura).
3. **El criterio de identidad es el de `T-5.11`, sin segunda ley.** La respuesta
   grabada del 2026-09-14 trae once eventos globales —Vanuatu, isla de Pascua,
   Filipinas, China…— y sólo el de Huehuetlán el Chico es el nuestro. Los
   intrusos se rechazan **aunque la fuente los devuelva**, que es más fuerte que
   confiar en que el servidor respete el radio que le pedimos.
4. **Idempotencia** (regla de oro 3): reconsultar no duplica filas ni reescribe
   `asked_at`, y un sismo que ya está en el catálogo con otro `catalog_key`
   —los seis del seed— se REFRESCA, no se duplica.
5. **Sin respuesta se declara**, con su razón y con `answered_at` en NULL.

Sin red en ningún momento: el transporte se inyecta con `httpx.MockTransport`.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api import procedencia as P
from takab_api.catalogo import consulta as C
from takab_api.dictamen.model import (
    CONSULTA_EXTERNA_EN_VUELO,
    CORRELACION_EN_DISPUTA,
    SIN_CONSULTA_A_FUENTE_EXTERNA,
    SSN_NO_SE_CONSULTA,
    TS_FMT,
    fuentes_line,
)
from takab_api.settings import Settings
from tests.catalogo.fixtures import CRUDA_AUTOMATICA, cruda, dsn, geojson, geojson_de

#: El M5.7 de Huehuetlán el Chico (`us7000lh50`), 2023-12-07T20:03:38.568Z, a
#: 135 km del centro de la Ciudad de México. Es el único de los once eventos de
#: la consulta archivada que puede ser el nuestro.
ORIGEN_HUEHUETLAN = datetime(2023, 12, 7, 20, 3, 38, 568000, tzinfo=UTC)
#: Detección 40 s después del origen: dentro de la cota `dist/v_S + margen`
#: (135.4/3.6 + 30 ≈ 68 s) que fija el criterio de `T-5.11`.
DETECTADO = ORIGEN_HUEHUETLAN + timedelta(seconds=40)
NOW = DETECTADO + timedelta(minutes=30)

CDMX_LAT, CDMX_LON = 19.43, -99.13

#: El gemelo USGS del Puebla-Morelos 2017 tal como lo siembra
#: `db/seeds/reference_earthquakes.sql`: clave NUESTRA, identidad del proveedor.
SEED_CLAVE = "USGS-2017-09-19-PUE"
SEED_PID = "us2000ar20"
ORIGEN_PUEBLA = datetime(2017, 9, 19, 18, 14, 38, 90000, tzinfo=UTC)


def _settings(**over) -> Settings:
    return Settings(**{"catalog_usgs_enabled": True, **over})


def _sirve(payload: dict, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


def _huehuetlan_solo() -> dict:
    """Los once eventos grabados. Uno es el nuestro; diez no."""
    return geojson_de("NUEVO-2023-12-07-HUEH")


@dataclass
class Escenario:
    conn: psycopg.Connection
    tenant: str
    site: str

    # ------------------------------------------------------------- siembra
    def incidente(self, *, en_revision: bool = True, cuando: datetime = DETECTADO) -> str:
        inc = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
            " severity, state, trigger) VALUES (%s, gen_random_uuid(), %s, %s, %s,"
            " 'critical', %s, 'sasmex')",
            (inc, self.tenant, self.site, cuando, "in_review" if en_revision else "open"),
        )
        if en_revision:
            # La huella que deja `transition_incident`, que es lo que la pasada mira.
            self.conn.execute(
                "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor)"
                " VALUES (%s,%s,%s,'in_review','system:incident')",
                (inc, self.tenant, cuando + timedelta(minutes=5)),
            )
        self.conn.commit()
        return inc

    def siembra_puebla(self) -> None:
        """La fila USGS del seed: clave nuestra, identidad del proveedor."""
        self.conn.execute(
            "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
            " epicenter, depth_km, source, source_ref, provider_event_id)"
            " VALUES (%s,%s,7.1,'Puebla-Morelos 19S (solucion USGS, gemelo)',"
            " ST_SetSRID(ST_MakePoint(-98.4887, 18.5499), 4326)::geography, 48,"
            " 'USGS','USGS us2000ar20 — sembrado a mano',%s)",
            (SEED_CLAVE, ORIGEN_PUEBLA, SEED_PID),
        )
        self.conn.commit()

    # -------------------------------------------------------------- lectura
    def consulta(self, inc: str) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM catalog_consultations WHERE incident_id = %s", (inc,)
        ).fetchone()

    def catalogo(self) -> list[dict]:
        return self.conn.execute(
            "SELECT catalog_key, provider_event_id, magnitude::float8 AS magnitude,"
            " review_status, consulted_at, source_ref, place"
            " FROM reference_earthquakes ORDER BY catalog_key"
        ).fetchall()

    # --------------------------------------------------------------- pasada
    def sitio_en(self, lat: float, lon: float) -> None:
        """Mueve el sitio. Hay sismos que sólo existen lejos de México: ver
        `fixtures.CRUDA_AUTOMATICA`."""
        self.conn.execute(
            "UPDATE sites SET geom = ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography"
            " WHERE site_id = %s",
            (lon, lat, self.site),
        )
        self.conn.commit()

    def epicentro_escrito(self) -> dict:
        """Lo que quedó GUARDADO, releído de la base y no de lo que se mandó."""
        return self.conn.execute(
            "SELECT catalog_key,"
            " ST_Y(epicenter::geometry)::float8 AS lat,"
            " ST_X(epicenter::geometry)::float8 AS lon"
            " FROM reference_earthquakes ORDER BY catalog_key"
        ).fetchone()

    def pasada(
        self,
        transporte: httpx.MockTransport | None,
        *,
        now: datetime = NOW,
        maximo: int = C._MAX_POR_PASADA,  # noqa: SLF001
        reloj: Callable[[], float] = time.monotonic,
        **over,
    ) -> C.PasadaDeConsulta:
        """Corre la pasada CON EL ROL DEL WORKER, no como superusuario.

        Es lo que verifica que los `GRANT` de la 0068 existen: sin ellos la
        pasada muere con `permission denied`, que es verde en local sólo si se
        corre como superusuario — el defecto que este repositorio ya pagó dos
        veces."""
        self.conn.execute('SET ROLE "takab_ingest"')
        try:
            return C.run_consulta_catalogo_pass(
                self.conn,
                _settings(**over),
                now=now,
                transport=transporte,
                max_por_pasada=maximo,
                reloj=reloj,
            )
        finally:
            self.conn.execute("RESET ROLE")
            self.conn.commit()


async def _forense(inc: str):
    """El ensamblado forense por el camino de producción, contra esta base.

    Lo alimentan la consola, el dictamen y la app: un estado que no llega aquí
    no llega a ninguna superficie.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from takab_api.forensics import build_forensics

    engine = create_async_engine(dsn().replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        async with engine.connect() as c:
            return await build_forensics(c, inc)
    finally:
        await engine.dispose()


@pytest.fixture
def esc() -> Iterator[Escenario]:
    conn = psycopg.connect(dsn(), autocommit=False, row_factory=dict_row)
    tenant, site = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility)"
            " VALUES (%s,%s,'Consulta T-7.25','private')",
            (tenant, tenant[:8]),
        )
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES"
            " (%s,%s,%s,'Sitio',ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
            (site, tenant, f"{tenant[:8]}-A", CDMX_LON, CDMX_LAT),
        )
        conn.commit()
        yield Escenario(conn, tenant, site)
    finally:
        _limpiar(conn, tenant)
        conn.close()


def _limpiar(conn: psycopg.Connection, tenant: str) -> None:
    """`incident_actions` es append-only por trigger: el superusuario los apaga
    para el teardown (sólo en tests; en producción esas filas son inmutables)."""
    conn.rollback()
    conn.execute("RESET ROLE")
    conn.execute("SET session_replication_role = replica")
    conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM catalog_consultations WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
    # El catálogo es GLOBAL (sin tenant_id): se borra lo que esta suite escribió.
    # Los tres prefijos que esta suite puede escribir: `us…` (USGS nacional),
    # `aka…` (la red de Alaska, que es de donde sale el único evento que la
    # fuente NO ha revisado) y la clave del seed que se siembra aquí.
    conn.execute(
        "DELETE FROM reference_earthquakes WHERE source = 'USGS'"
        " AND (catalog_key LIKE 'USGS-us%%' OR catalog_key LIKE 'USGS-aka%%'"
        "      OR catalog_key = %s)",
        (SEED_CLAVE,),
    )
    conn.execute("SET session_replication_role = origin")
    conn.commit()


# ---- apagada: lo que se despliega -------------------------------------------


def test_apagada_no_abre_un_socket_ni_escribe_una_fila(esc: Escenario, monkeypatch) -> None:
    """Se sabotea `httpx.Client` entero: si el camino apagado lo tocara, reventaría."""

    def explota(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("el camino apagado no debe construir un cliente HTTP")

    monkeypatch.setattr(httpx, "Client", explota)
    inc = esc.incidente()
    esc.conn.execute('SET ROLE "takab_ingest"')
    try:
        out = C.run_consulta_catalogo_pass(esc.conn, Settings(), now=NOW)
    finally:
        esc.conn.execute("RESET ROLE")
        esc.conn.commit()
    assert out.consultados == ()
    assert esc.consulta(inc) is None
    assert esc.catalogo() == []


# ---- el intento se escribe ANTES de la red ----------------------------------


def test_el_intento_se_escribe_y_se_commitea_antes_de_preguntar(esc: Escenario) -> None:
    """Un worker que muere con la pregunta en vuelo deja `consultando` escrito.

    ⚠️ **Mirar la base DESPUÉS de la pasada no demuestra nada, y la primera
    versión de esta prueba nació ciega por eso**: la pasada commitea igual al
    salir (suelta el advisory lock), así que con el `commit` del intento
    borrado la fila aparecía lo mismo y el test seguía verde. Medido.

    Lo que sí lo demuestra es mirar **desde otra conexión, DURANTE la llamada
    HTTP**: el manejador del transporte es literalmente ese instante, y en
    `READ COMMITTED` una segunda conexión sólo ve la fila si el worker ya la
    commiteó. Después se mata el proceso con `SystemExit` —que no es
    `Exception`, así que el worker no la captura— para que el escenario sea el
    real y no una simulación.
    """
    inc = esc.incidente()
    visto: list[dict | None] = []

    def espia_y_se_muere(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        otra = psycopg.connect(dsn(), autocommit=True, row_factory=dict_row)
        try:
            visto.append(
                otra.execute(
                    "SELECT asked_at, answered_at, outcome, attempts"
                    " FROM catalog_consultations WHERE incident_id = %s",
                    (inc,),
                ).fetchone()
            )
        finally:
            otra.close()
        raise SystemExit("el worker se murió con la pregunta en vuelo")

    with pytest.raises(SystemExit):
        esc.pasada(httpx.MockTransport(espia_y_se_muere))

    assert visto, "el transporte no llegó a ejecutarse"
    fila = visto[0]
    assert fila is not None, (
        "durante la llamada HTTP el intento NO estaba commiteado: un worker que "
        "muera ahí dejaría el incidente como si nadie hubiera preguntado nunca"
    )
    assert fila["answered_at"] is None
    assert fila["outcome"] is None, "un intento en vuelo no tiene desenlace"
    assert fila["asked_at"] == NOW
    assert fila["attempts"] == 1


# ---- el caso bueno ----------------------------------------------------------


def test_el_evento_real_correlaciona_y_el_catalogo_queda_citable(esc: Escenario) -> None:
    inc = esc.incidente()
    out = esc.pasada(_sirve(_huehuetlan_solo()))
    assert out.correlacionados == (inc,)

    fila = esc.consulta(inc)
    assert fila["outcome"] == "correlacionado"
    assert fila["answered_at"] == NOW
    assert fila["catalog_key"] == "USGS-us7000lh50"
    assert "us7000lh50" in fila["detail"]

    catalogo = esc.catalogo()
    assert [c["catalog_key"] for c in catalogo] == ["USGS-us7000lh50"], (
        "los otros diez eventos publicados NO son éste y no pueden entrar al catálogo"
    )
    (sismo,) = catalogo
    assert sismo["provider_event_id"] == "us7000lh50"
    assert sismo["magnitude"] == pytest.approx(5.7)
    assert sismo["review_status"] == "confirmado"  # USGS lo declara `reviewed`
    assert sismo["consulted_at"] == NOW
    # La cita tiene que permitir REPETIR la pregunta.
    assert "earthquake.usgs.gov" in sismo["source_ref"]
    assert "maxradiuskm" in sismo["source_ref"]


def test_los_intrusos_del_otro_hemisferio_se_rechazan_aunque_la_fuente_los_devuelva(
    esc: Escenario,
) -> None:
    """La consulta pide `maxradiuskm`, pero el veredicto no se apoya en que el
    servidor lo respete: los once eventos entran al criterio de `T-5.11` y sólo
    uno sale. Vanuatu está a 10 910 km del sitio."""
    esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))
    claves = {c["catalog_key"] for c in esc.catalogo()}
    assert "USGS-us7000lgwp" not in claves, "entró el M7.1 de Vanuatu"
    assert "USGS-us7000lgsj" not in claves, "entró el M5.4 de Filipinas"
    assert claves == {"USGS-us7000lh50"}


# ---- sin red y sin coincidencia ---------------------------------------------


def test_sin_red_queda_consultando_con_su_razon(esc: Escenario) -> None:
    inc = esc.incidente()

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Name or service not known", request=request)

    out = esc.pasada(httpx.MockTransport(sin_red))
    assert out.sin_respuesta == (inc,)

    fila = esc.consulta(inc)
    assert fila["answered_at"] is None, "sin `answered_at` no se puede decir que contestó"
    assert fila["outcome"] == "sin_respuesta"
    assert fila["catalog_key"] is None
    assert "ConnectError" in fila["detail"]
    assert esc.catalogo() == [], "nada que no venga de la fuente entra al catálogo"


def test_la_fuente_contesta_y_no_tiene_nada_es_sin_correlacion(esc: Escenario) -> None:
    """`sin_correlacion` es un HECHO sobre el evento —probablemente local y
    pequeño—, no una ausencia de datos. Y por eso SÍ lleva `answered_at`."""
    inc = esc.incidente()
    out = esc.pasada(_sirve(geojson([])))
    assert out.sin_correlacion == (inc,)

    fila = esc.consulta(inc)
    assert fila["outcome"] == "sin_correlacion"
    assert fila["answered_at"] == NOW
    assert "no publicó ningún evento" in fila["detail"]


def test_hay_eventos_en_la_ventana_y_ninguno_es_este_lo_dice_con_su_motivo(
    esc: Escenario,
) -> None:
    """La diferencia entre «el catálogo no tiene nada» y «lo que tiene no es
    esto». Sin el motivo, el operador lee un hueco como «no pasó nada»."""
    inc = esc.incidente()
    esc.pasada(_sirve(geojson_de("SSN-2022-09-19-MICH")))  # el M7.6 de 2022
    fila = esc.consulta(inc)
    assert fila["outcome"] == "sin_correlacion"
    assert "us7000i9bw" in fila["detail"]
    assert "ninguno es éste" in fila["detail"]


# ---- idempotencia -----------------------------------------------------------


def test_reconsultar_no_duplica_filas_ni_reescribe_la_fecha_original(esc: Escenario) -> None:
    """Regla de oro 3. `asked_at` es la fecha que se cita; `last_attempt_at` es
    el reloj del reintento, y son cosas distintas."""
    inc = esc.incidente()

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    esc.pasada(httpx.MockTransport(sin_red))
    primera = esc.consulta(inc)

    despues = NOW + timedelta(seconds=1000)  # pasado el reintento de 900 s
    esc.pasada(_sirve(_huehuetlan_solo()), now=despues)
    segunda = esc.consulta(inc)

    assert segunda["asked_at"] == primera["asked_at"] == NOW
    assert segunda["last_attempt_at"] == despues
    assert segunda["attempts"] == 2
    assert segunda["outcome"] == "correlacionado"

    n = esc.conn.execute(
        "SELECT count(*) AS n FROM catalog_consultations WHERE incident_id = %s", (inc,)
    ).fetchone()["n"]
    assert n == 1


def test_un_sismo_ya_sembrado_se_REFRESCA_y_no_entra_dos_veces(esc: Escenario) -> None:
    """⚠️ La trampa que esta ficha existe para no pisar: `catalog_key` es una
    clave NUESTRA y `provider_event_id` es la del proveedor. Si la identidad
    fuera la primera, reconsultar `us2000ar20` metería el Puebla-Morelos 2017
    dos veces — una como `USGS-2017-09-19-PUE` y otra como `USGS-us2000ar20`."""
    esc.siembra_puebla()
    inc = esc.incidente(cuando=ORIGEN_PUEBLA + timedelta(seconds=40))
    esc.pasada(_sirve(geojson_de("USGS-2017-09-19-PUE")), now=ORIGEN_PUEBLA + timedelta(hours=1))

    catalogo = esc.catalogo()
    assert [c["catalog_key"] for c in catalogo] == [SEED_CLAVE], (
        "el sismo entró dos veces: la identidad es (source, provider_event_id)"
    )
    (sismo,) = catalogo
    assert sismo["provider_event_id"] == SEED_PID
    # La consulta SÍ actualiza la procedencia y la cita: dejar la cifra vieja
    # junto a un `consulted_at` recién puesto sería lo peor de las dos cosas.
    assert sismo["review_status"] == "confirmado"
    assert sismo["consulted_at"] is not None
    assert "earthquake.usgs.gov" in sismo["source_ref"]
    assert esc.consulta(inc)["catalog_key"] == SEED_CLAVE


def test_una_consulta_ya_resuelta_no_se_vuelve_a_preguntar(esc: Escenario) -> None:
    inc = esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))

    def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("se volvió a preguntar por un incidente ya resuelto")

    out = esc.pasada(httpx.MockTransport(no_deberia), now=NOW + timedelta(hours=2))
    assert out.consultados == ()
    assert esc.consulta(inc)["attempts"] == 1


def test_un_sin_respuesta_reciente_espera_su_turno(esc: Escenario) -> None:
    """El reintento tiene reloj. Sin él, cada pasada (cada 5 s) volvería a
    aporrear a un tercero que acaba de decir que no puede."""
    esc.incidente()

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    esc.pasada(httpx.MockTransport(sin_red))

    def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("se reintentó antes de tiempo")

    out = esc.pasada(httpx.MockTransport(no_deberia), now=NOW + timedelta(seconds=60))
    assert out.consultados == ()


# ---- a quién se pregunta ----------------------------------------------------


def test_un_incidente_que_no_entro_en_revision_no_se_consulta(esc: Escenario) -> None:
    """La ficha lo dice: la consulta es un paso «al entrar en revisión». Un
    incidente todavía en alerta no se consulta — el evento puede no haber
    terminado, y la fuente no habrá publicado nada."""
    esc.incidente(en_revision=False)

    def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("se consultó un incidente que no entró en revisión")

    assert esc.pasada(httpx.MockTransport(no_deberia)).consultados == ()


def test_un_incidente_mas_viejo_que_el_ttl_de_revision_ya_no_se_consulta(
    esc: Escenario,
) -> None:
    """La ventana se DERIVA de `incident_review_ttl_s`: pasado ese plazo el
    incidente ya no está en revisión y la respuesta no le sirve a nadie."""
    esc.incidente()

    def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("se consultó un incidente vencido")

    tarde = DETECTADO + timedelta(seconds=Settings().incident_review_ttl_s + 60)
    assert esc.pasada(httpx.MockTransport(no_deberia), now=tarde).consultados == ()


# ---- el worker es el ÚNICO escritor -----------------------------------------


def test_la_api_no_puede_escribir_la_consulta_ni_el_catalogo(esc: Escenario) -> None:
    """Criterio 1 de la ficha, medido como PRIVILEGIO y no como costumbre.

    `has_table_privilege` sobre el rol de la API: `takab_app` lee las dos tablas
    y no escribe ninguna. Sin esto, «el worker es el único escritor» sería una
    afirmación sobre el código de hoy.

    ⚠️ Este docstring decía exactamente eso —«las dos tablas»— mientras la
    prueba sólo miraba una: `catalog_consultations` estaba blindada y
    `reference_earthquakes`, la tabla que esta ficha acaba de volver escribible,
    se quedaba con INSERT, UPDATE y DELETE para `takab_app`. Medido el
    2026-09-20 sobre esta misma base, construida por migraciones."""
    esc.conn.execute("RESET ROLE")
    for tabla in ("catalog_consultations", "reference_earthquakes"):
        puede = esc.conn.execute(
            "SELECT has_table_privilege('takab_app', %s, 'SELECT') AS lee,"
            "       has_table_privilege('takab_app', %s, 'INSERT') AS i,"
            "       has_table_privilege('takab_app', %s, 'UPDATE') AS u,"
            "       has_table_privilege('takab_app', %s, 'DELETE') AS d",
            (tabla, tabla, tabla, tabla),
        ).fetchone()
        assert puede["lee"], f"la API no puede leer {tabla}"
        assert not (puede["i"] or puede["u"] or puede["d"]), (
            f"la API puede escribir {tabla}: el worker deja de ser el único escritor"
        )
    ing = esc.conn.execute(
        "SELECT has_table_privilege('takab_ingest','reference_earthquakes','INSERT') AS i,"
        "       has_table_privilege('takab_ingest','reference_earthquakes','UPDATE') AS u"
    ).fetchone()
    assert ing["i"] and ing["u"], (
        "el worker no puede escribir el catálogo: la 0068 no concedió el permiso"
    )


# ---- la consulta se DERIVA del criterio de identidad -------------------------


def test_la_ventana_y_el_radio_que_se_preguntan_salen_del_criterio_de_T_5_11(
    esc: Escenario,
) -> None:
    """No hay un segundo criterio, y esto es lo que lo impide.

    Si la pasada acotara la consulta con números propios, ese segundo criterio no
    estaría escrito en ninguna parte y podría contradecir al que después decide la
    identidad: se preguntaría por una ventana en la que el veredicto ya no acepta
    nada, o al revés, se dejaría fuera un sismo que sí habría casado.
    """
    from urllib.parse import parse_qs, urlsplit

    from takab_api.settings import Settings as S

    visto: dict[str, list[str]] = {}

    def espia(request: httpx.Request) -> httpx.Response:
        visto.update(parse_qs(urlsplit(str(request.url)).query))
        return httpx.Response(200, json=geojson([]))

    esc.incidente()
    esc.pasada(httpx.MockTransport(espia))

    criterio = C.criterio_de(S(catalog_usgs_enabled=True))
    assert visto["maxradiuskm"] == [f"{criterio.radio_km:g}"]
    assert visto["latitude"] == [f"{CDMX_LAT:g}"]
    assert visto["longitude"] == [f"{CDMX_LON:g}"]
    # La cota es la MISMA que usa `queries/forensics.py` contra la base: el
    # retraso máximo admisible, a los dos lados.
    tope = timedelta(seconds=criterio.retraso_maximo_s)
    esperado_desde = (DETECTADO - tope).strftime("%Y-%m-%dT%H:%M:%SZ")
    esperado_hasta = (DETECTADO + tope).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert visto["starttime"] == [esperado_desde]
    assert visto["endtime"] == [esperado_hasta]


def test_un_evento_sin_magnitud_no_entra_al_catalogo_y_se_DICE(esc: Escenario) -> None:
    """`reference_earthquakes.magnitude` es NOT NULL y un cero inventado sería la
    cifra sin fuente que todo esto existe para impedir. Así que un evento sin
    magnitud publicada no se puede escribir — y en vez de desaparecer, se cuenta
    en el desenlace."""
    inc = esc.incidente()
    payload = _huehuetlan_solo()
    for f in payload["features"]:
        f["properties"]["mag"] = None
    publicados = len(payload["features"])
    esc.pasada(_sirve(payload))

    fila = esc.consulta(inc)
    assert fila["outcome"] == "sin_correlacion"
    assert esc.catalogo() == []
    # ⚠️ La frase ENTERA, no una subcadena. Esta guarda buscaba sólo «sin
    # magnitud publicada» y dejaba pasar la mitad falsa de la misma línea: el
    # detalle decía «0 evento(s) publicados y ninguno evaluable (11 sin magnitud
    # publicada, no citables)» — cero y once, sobre la misma respuesta, en doce
    # palabras. `_por_que_no` recibía el número de CITABLES bajo el rótulo
    # «publicados», que es justo la cifra que ese parámetro existe para dar.
    assert fila["detail"] == (
        f"{publicados} evento(s) publicados y ninguno evaluable "
        f"({publicados} sin magnitud publicada, no citables)"
    )


# ---- el estado LLEGA a la superficie ----------------------------------------


async def test_consultando_llega_hasta_el_ensamblado_forense(esc: Escenario) -> None:
    """La prueba de que el estado no muere en la tabla.

    `consultando` sólo sirve si alguien lo lee: `build_forensics` es lo que
    alimentan la consola, el dictamen y la app. Antes de esta ficha ese camino
    decía `sin_correlacion` pasara lo que pasara —«se consultó el catálogo y nada
    suyo es éste»—, que con una pregunta sin contestar es dar por concluido lo
    que no ha concluido.
    """
    inc = esc.incidente()

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("se acabó el tiempo", request=request)

    esc.pasada(httpx.MockTransport(sin_red))

    f = await _forense(inc)

    assert f is not None
    assert f.catalog_correlation.estado == "consultando"
    assert f.catalog is None, "no se pinta cifra: no hay ninguna"
    # [T-7.25] Y llega CON SU HORA. Sin esto el estado va desnudo a la
    # superficie: un `consultando` de hace seis horas se pinta igual que uno de
    # hace dos segundos, que es dato viejo presentado como fresco (regla de oro
    # 7). `de_consulta` ya calculaba las dos cosas y el llamador las tiraba.
    assert f.catalog_correlation.fuente == "USGS"
    assert f.catalog_correlation.consultado_en == NOW


# ---- lo que la pasada le cuesta al bucle del worker -------------------------


def _lento(segundos: float, payload: dict | None = None) -> httpx.MockTransport:
    """Un tercero que tarda. Es el escenario normal, no el patológico."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        time.sleep(segundos)
        return httpx.Response(200, json=payload if payload is not None else geojson([]))

    return httpx.MockTransport(handler)


def test_la_pasada_NO_bloquea_el_bucle_mas_alla_de_su_presupuesto(esc: Escenario) -> None:
    """El invariante, MEDIDO con reloj de pared y no prometido en un comentario.

    Esta pasada corre DENTRO del bucle del worker de incidentes, que es serial:
    en la misma vuelta viven `run_correlation`, la reproducción, **la actuación
    comandada por el quórum**, el dictamen y las fases. Lo que tarde aquí es lo
    que se retrasa todo aquello. Con veinte llamadas seriales y 6 s de timeout
    el peor caso eran dos minutos.

    Ahora el tope es `catalog_usgs_presupuesto_s` y se comprueba antes de cada
    pregunta con el timeout incluido, así que el peor caso de la pasada ES ese
    número. Aquí se mide con ocho candidatos contra un tercero que tarda 0.25 s
    cada uno: sin presupuesto serían 2 s; con él, medio segundo.
    """
    for i in range(8):
        esc.incidente(cuando=DETECTADO - timedelta(minutes=i))

    arranque = time.monotonic()
    out = esc.pasada(
        _lento(0.25),
        catalog_usgs_presupuesto_s=0.6,
        catalog_usgs_timeout_s=0.25,
    )
    gastado = time.monotonic() - arranque

    # La medición primero: es el invariante. Lo demás describe POR QUÉ se cumple.
    assert gastado < 1.0, (
        f"la pasada bloqueó el bucle {gastado:.2f} s con un presupuesto de 0.6 s: "
        "la siguiente vuelta —y con ella la actuación del quórum— llega tarde"
    )
    assert out.corte == C.CORTE_POR_PRESUPUESTO
    assert 0 < len(out.consultados) < 8, "o no preguntó nada, o no cortó"


def test_con_el_timeout_ENTERO_la_pasada_pregunta_una_vez_y_se_va(esc: Escenario) -> None:
    """La aritmética exacta, con los números que se despliegan y sin dormir.

    El reloj lo mueve el propio transporte: cada llamada gasta el timeout
    completo (6 s), que es el peor caso de una pregunta. Con el presupuesto en
    10 s la cuenta es `6 + 6 > 10`, así que la segunda no sale: se queda para la
    vuelta siguiente, que llega en segundos. Lo que NO puede pasar es que salgan
    las veinte, que es lo que hacía.
    """
    for i in range(4):
        esc.incidente(cuando=DETECTADO - timedelta(minutes=i))

    marca = [0.0]
    s = Settings()

    def quema_el_timeout(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        marca[0] += s.catalog_usgs_timeout_s
        return httpx.Response(200, json=geojson([]))

    out = esc.pasada(httpx.MockTransport(quema_el_timeout), reloj=lambda: marca[0])
    assert len(out.consultados) == 1
    assert out.corte == C.CORTE_POR_PRESUPUESTO
    assert marca[0] <= s.catalog_usgs_presupuesto_s


def test_un_presupuesto_ridiculo_NO_deja_la_pasada_en_un_no_op_silencioso(
    esc: Escenario,
) -> None:
    """La primera pregunta SIEMPRE sale, aunque el presupuesto no la cubra.

    Si la comprobación fuera ciega al orden, un presupuesto por debajo del
    timeout convertiría la pasada en un no-op: nadie preguntaría nunca y nada lo
    diría — el modo de fallo más caro de este repositorio (una superficie que
    calla en vez de declarar). El peor caso de una sola llamada ya lo acota el
    propio timeout.
    """
    inc = esc.incidente()
    out = esc.pasada(_sirve(geojson([])), catalog_usgs_presupuesto_s=0.0001)
    assert out.consultados == (inc,)


def test_el_tope_por_pasada_recorta_y_el_resultado_lo_DICE(esc: Escenario) -> None:
    """`corte` no es decoración: es lo que distingue «ya está» de «faltan»."""
    for i in range(3):
        esc.incidente(cuando=DETECTADO - timedelta(minutes=i))
    out = esc.pasada(_sirve(geojson([])), maximo=2)
    assert len(out.consultados) == 2
    assert out.corte == C.CORTE_POR_TOPE
    assert out.truncada


def test_se_pregunta_primero_por_el_incidente_MAS_VIEJO(esc: Escenario) -> None:
    """⚠️ Con `ORDER BY opened_at DESC` los viejos no se preguntaban NUNCA.

    Cuando la pasada recorta, el orden decide a quién se deja fuera. Con los
    nuevos primero, un goteo de incidentes recientes empuja a los viejos hasta
    que vence el TTL de revisión —y entonces ya no son candidatos—, sin que
    quede rastro de que se les saltó. El más viejo es justo el que menos ventana
    le queda, y preguntarle primero no puede acaparar la pasada: en cuanto se
    pregunta queda escrito `last_attempt_at` y se calla durante su reintento.
    """
    viejo = esc.incidente(cuando=DETECTADO - timedelta(hours=1))
    esc.incidente(cuando=DETECTADO)
    out = esc.pasada(_sirve(geojson([])), maximo=1)
    assert out.consultados == (viejo,), "se preguntó por el nuevo y el viejo esperó"


# ---- el epicentro que se ESCRIBE --------------------------------------------


def test_el_epicentro_ESCRITO_es_el_que_publico_la_fuente(esc: Escenario) -> None:
    """Releído de la base, no de lo que se mandó.

    Las cifras son las del evento `us7000lh50` en la respuesta archivada:
    18.2702 N, 98.7384 W. Hasta esta revisión **nadie miraba el epicentro en el
    lado de la escritura**: invertir `ST_MakePoint(lon, lat)` dejaba 493 pruebas
    en verde.
    """
    esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))
    fila = esc.epicentro_escrito()
    assert fila["lat"] == pytest.approx(18.2702, abs=1e-6)
    assert fila["lon"] == pytest.approx(-98.7384, abs=1e-6)


def test_un_epicentro_INVERTIDO_al_escribir_no_llega_a_la_base(esc: Escenario, monkeypatch) -> None:
    """La mutación del escéptico, hecha por la prueba, y su consecuencia.

    PostGIS no protege: una latitud de -98.7384 no es un error para él, la
    coacciona al rango con un simple `NOTICE` y guarda `POINT(18.2702
    -81.2616)` — el epicentro del sismo de Puebla en mitad del Caribe, con su
    magnitud y su cita al lado, camino de un croquis firmado.

    Con la relectura, el `INSERT` se revierte y el incidente se queda en
    `consultando`: no escribir un epicentro es mucho menos grave que escribir
    uno falso.
    """
    monkeypatch.setattr(
        C,
        "_CATALOGO_SQL",
        C._CATALOGO_SQL.replace(  # noqa: SLF001
            "ST_MakePoint(%(lon)s, %(lat)s)", "ST_MakePoint(%(lat)s, %(lon)s)"
        ),
    )
    inc = esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))

    assert esc.catalogo() == [], "se escribió un epicentro que no es el que publicó la fuente"
    fila = esc.consulta(inc)
    assert fila["answered_at"] is None and fila["outcome"] is None, (
        "la consulta se dio por resuelta con el catálogo sin escribir"
    )


# ---- `preliminar`: la afirmación que caduca ---------------------------------

#: El M3.5 de Valdez (`aka2026scqemw`), 2026-09-12T19:18:05.903Z. Es el único
#: evento de todo el árbol que la fuente **no ha revisado**, y por eso el sitio
#: de estas pruebas está en Alaska: USGS revisa los sismos mexicanos de magnitud
#: publicable en horas, así que un `automatic` mexicano no se puede archivar.
#: Ver `tests/catalogo/fixtures.py`.
ORIGEN_VALDEZ = datetime(2026, 9, 12, 19, 18, 5, 903000, tzinfo=UTC)
VALDEZ_SITIO_LAT, VALDEZ_SITIO_LON = 61.49, -146.12


def _valdez(esc: Escenario) -> str:
    """Un incidente a 22 km del epicentro archivado, detectado 20 s después."""
    esc.sitio_en(VALDEZ_SITIO_LAT, VALDEZ_SITIO_LON)
    return esc.incidente(cuando=ORIGEN_VALDEZ + timedelta(seconds=20))


def test_una_respuesta_grabada_SIN_REVISAR_produce_preliminar_por_el_camino_real(
    esc: Escenario,
) -> None:
    """`preliminar` dejó de ser un estado que sólo se alcanzaba a mano.

    El archivo destilado de la suite sólo traía eventos `reviewed`, así que
    `preliminar` —«la fuente aún no ha revisado esta solución: PUEDE CAMBIAR»—
    no lo producía el camino real en ningún punto: se construía a mano en los
    tests de `procedencia` y nadie había visto nunca al worker escribirlo.
    """
    inc = _valdez(esc)
    ahora = ORIGEN_VALDEZ + timedelta(minutes=10)
    out = esc.pasada(_sirve(cruda(CRUDA_AUTOMATICA)), now=ahora)

    assert out.correlacionados == (inc,)
    (sismo,) = esc.catalogo()
    assert sismo["provider_event_id"] == "aka2026scqemw"
    assert sismo["review_status"] == "preliminar", (
        "la fuente dijo `automatic` y aquí se citó como revisada"
    )
    assert "estado en la fuente 'automatic'" in esc.consulta(inc)["detail"]


def test_un_preliminar_se_vuelve_a_preguntar_cuando_vence_SU_reloj(esc: Escenario) -> None:
    """⚠️ Un `preliminar` no se re-preguntaba NUNCA, y eso congela el papel.

    El predicado de candidatos excluía toda consulta con `answered_at` puesto,
    así que en cuanto la fuente contestaba una vez, su estado quedaba fijado
    para siempre. Pero `preliminar` significa literalmente «puede cambiar», y la
    ventana en la que la fuente revisa su solución se solapa con la ventana en
    la que se firma el dictamen: el papel salía diciendo PUEDE CAMBIAR de algo
    que ya estaba revisado, o peor, con la magnitud que la fuente corrigió.

    El reloj es propio (`catalog_usgs_refresco_preliminar_s`) y no el del
    reintento: reintentar es «no me contestaron» y esto es «me contestaron algo
    que todavía puede cambiar». Un `confirmado` no vuelve a preguntarse — eso lo
    fija `test_una_consulta_ya_resuelta_no_se_vuelve_a_preguntar`, cuyo evento
    es `reviewed`.
    """
    inc = _valdez(esc)
    ahora = ORIGEN_VALDEZ + timedelta(minutes=10)
    esc.pasada(_sirve(cruda(CRUDA_AUTOMATICA)), now=ahora)

    def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("se re-preguntó por un preliminar antes de su hora")

    media_hora = ahora + timedelta(minutes=30)
    assert esc.pasada(httpx.MockTransport(no_deberia), now=media_hora).consultados == ()
    assert esc.consulta(inc)["attempts"] == 1

    pasada_la_hora = ahora + timedelta(seconds=Settings().catalog_usgs_refresco_preliminar_s + 60)
    out = esc.pasada(_sirve(cruda(CRUDA_AUTOMATICA)), now=pasada_la_hora)
    assert out.correlacionados == (inc,), "el preliminar se congeló: nadie volvió a preguntar"
    fila = esc.consulta(inc)
    assert fila["attempts"] == 2
    assert fila["asked_at"] == ahora, "`asked_at` es la fecha que se cita y no se reescribe"
    assert fila["last_attempt_at"] == pasada_la_hora


# ---- multi-tenant (regla de oro 5) ------------------------------------------


def test_la_consulta_de_OTRO_cliente_no_se_ve(esc: Escenario) -> None:
    """`catalog_consultations` lleva `tenant_id`, y eso hay que defenderlo.

    La RLS aísla —medido—, pero nadie lo comprobaba: la tabla nació en esta
    ficha con su política y su `FORCE`, y un `USING` mal escrito en una
    migración futura no habría puesto nada en rojo. Un incidente es de un
    cliente, y de él se deduce cuándo tembló en su edificio.
    """
    inc = esc.incidente()
    esc.pasada(_sirve(geojson([])))

    def cuantas_ve(tenant: str) -> int:
        esc.conn.execute("RESET ROLE")
        esc.conn.execute('SET ROLE "takab_app"')
        esc.conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        esc.conn.execute("SELECT set_config('app.role', 'client_admin', true)")
        n = esc.conn.execute(
            "SELECT count(*) AS n FROM catalog_consultations WHERE incident_id = %s", (inc,)
        ).fetchone()["n"]
        esc.conn.execute("RESET ROLE")
        return n

    assert cuantas_ve(esc.tenant) == 1, "el dueño del incidente no ve su propia consulta"
    assert cuantas_ve(str(uuid.uuid4())) == 0, (
        "otro cliente ve la consulta de éste: la RLS de catalog_consultations no aísla"
    )


# ---- el PAPEL FIRMADO -------------------------------------------------------


async def _modelo(inc: str, **over):
    """El modelo del dictamen por el camino de producción, contra esta base."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from takab_api.dictamen.builder import build_model

    engine = create_async_engine(dsn().replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        async with engine.connect() as c:
            return await build_model(c, inc, generated_at=NOW, settings=_settings(**over))
    finally:
        await engine.dispose()


async def test_el_papel_NO_afirma_que_no_hay_correlacion_con_la_pregunta_en_vuelo(
    esc: Escenario,
) -> None:
    """⚠️ EL defecto que esta ficha existe para eliminar, en su peor superficie.

    Con la consulta sin respuesta, el dictamen imprimía «SIN CORRELACIÓN EN EL
    CATÁLOGO DE REFERENCIA: ningún sismo publicado satisface el criterio de
    identidad con este incidente». Eso es una afirmación **sobre el sismo**, y
    lo cierto era que nadie había contestado todavía. `_catalog_line` no miraba
    `catalog_correlation.estado`, y el PDF imprime `catalog_line or
    SIN_CORRELACION_EN_CATALOGO`, así que el hueco se rellenaba con la mentira.

    Va sobre el modelo completo y no sobre la función pura a propósito: lo que
    hay que demostrar es que el estado llega desde la base hasta la línea que se
    firma, atravesando `build_forensics`.
    """
    inc = esc.incidente()

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("se acabó el tiempo", request=request)

    esc.pasada(httpx.MockTransport(sin_red))

    m = await _modelo(inc)
    assert m is not None
    assert m.catalog_line is not None, (
        "sin línea, el PDF imprime SIN_CORRELACION_EN_CATALOGO: el papel firma "
        "que ningún sismo publicado es éste cuando nadie ha contestado"
    )
    assert m.catalog_line.startswith(CONSULTA_EXTERNA_EN_VUELO)
    assert "SIN CORRELACIÓN" not in m.catalog_line
    # Con su hora, que es lo que separa «se preguntó hace un minuto» de «lleva
    # seis horas sin respuesta».
    assert "USGS" in m.catalog_line
    assert f"{NOW:{TS_FMT}}" in m.catalog_line


async def test_el_dictamen_declara_a_quien_se_PUEDE_preguntar_y_lo_deriva(
    esc: Escenario,
) -> None:
    """La línea «CONSULTA A FUENTES EXTERNAS» estaba sin cablear a nada.

    Borrarla del builder dejaba 359 pruebas en verde, y hacerla MENTIR —decir
    «USGS (FDSN)» con la consulta apagada— también. El docstring de
    `fuentes_line` dice palabra por palabra que existe para impedir lo segundo:
    «con la consulta apagada decir "consultadas: USGS" sería afirmar una llamada
    que nadie hizo».

    Las dos caras, porque son las dos que se despliegan: hoy apagada.
    """
    inc = esc.incidente()

    apagada = await _modelo(inc, catalog_usgs_enabled=False)
    assert apagada.fuentes_externas == fuentes_line(False)
    assert "apagada" in apagada.fuentes_externas

    encendida = await _modelo(inc, catalog_usgs_enabled=True)
    assert encendida.fuentes_externas == fuentes_line(True)
    assert "USGS (FDSN)" in encendida.fuentes_externas
    # Y el SSN, siempre: sin la razón escrita, un lector supone que falló.
    assert SSN_NO_SE_CONSULTA in apagada.fuentes_externas


async def test_una_consulta_que_CORRELACIONO_no_se_rotula_SIN_DATO_EXTERNO(
    esc: Escenario,
) -> None:
    """La cuarta rama de `de_consulta` recibía siempre `fila=None`.

    Con `outcome='correlacionado'` escrito en la base, esa rama devolvía
    `de_fila(None)` = `sin_dato_externo`: la superficie rotulaba «SIN DATO
    EXTERNO» —«nadie preguntó»— sobre un incidente que sí se preguntó y sí
    correlacionó. Ahora la fila del catálogo viaja en el mismo `SELECT`.

    La discrepancia se fabrica moviendo la hora de origen de la fila del
    catálogo, que la saca de la ventana con la que el ensamblado forense busca
    candidatos. Lo que se mide es la DERIVACIÓN, no la causa: la causa puede ser
    cualquiera (una poda, un refresco que corrigió la hora en la fuente, dos
    lecturas con criterios distintos), y el rótulo tiene que ser el mismo.
    """
    inc = esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))
    assert esc.consulta(inc)["outcome"] == "correlacionado"
    esc.conn.execute(
        "UPDATE reference_earthquakes SET origin_time = origin_time - interval '1 hour'"
        " WHERE provider_event_id = 'us7000lh50'"
    )
    esc.conn.commit()

    f = await _forense(inc)

    assert f.catalog is None, "el arreglo del escenario no dejó al acierto fuera"
    assert f.catalog_correlation.estado == "confirmado", (
        "se preguntó, se correlacionó, y la superficie dice que nadie preguntó"
    )
    assert f.catalog_correlation.fuente == "USGS"
    assert f.catalog_correlation.consultado_en == NOW


async def test_el_papel_DECLARA_la_discrepancia_en_vez_de_exonerar_al_catalogo(
    esc: Escenario,
) -> None:
    """⚠️ El CUARTO hecho, y la misma mentira de la ficha en su cuarto disfraz.

    El escenario es el de la prueba de arriba —la consulta correlacionó y el
    ensamblado forense no reconoce el acierto—, pero lo que se mide es la línea
    que se FIRMA. `_linea_sin_acierto` no tenía rama para `preliminar` ni para
    `confirmado`: caían al final, y el final era el caso «contestaron y ninguno
    casa». Medido contra esta misma base antes del arreglo: `catalog_line` en
    `None`, que el PDF rellena con «SIN CORRELACIÓN EN EL CATÁLOGO DE
    REFERENCIA: ningún sismo publicado satisface el criterio de identidad con
    este incidente» — de un incidente cuya consulta escribió
    `outcome='correlacionado'` en la fila de al lado.

    Los dos procedimientos preguntan cosas distintas y pueden discrepar sin que
    ninguno esté roto. El documento no elige: lo dice.
    """
    inc = esc.incidente()
    esc.pasada(_sirve(_huehuetlan_solo()))
    assert esc.consulta(inc)["outcome"] == "correlacionado"
    esc.conn.execute(
        "UPDATE reference_earthquakes SET origin_time = origin_time - interval '1 hour'"
        " WHERE provider_event_id = 'us7000lh50'"
    )
    esc.conn.commit()

    m = await _modelo(inc)
    assert m.catalog_line is not None, (
        "sin línea, el PDF imprime SIN_CORRELACION_EN_CATALOGO: el papel firma que "
        "ningún sismo publicado es éste sobre un incidente que SÍ correlacionó"
    )
    assert m.catalog_line.startswith(CORRELACION_EN_DISPUTA)
    assert "SIN CORRELACIÓN" not in m.catalog_line
    # Con quién contestó, cuándo y con qué confianza: una discrepancia que no se
    # puede ir a comprobar no sirve de nada.
    assert "USGS" in m.catalog_line
    assert f"{NOW:{TS_FMT}}" in m.catalog_line
    assert P.rotulo(P.CONFIRMADO, "consola") in m.catalog_line


async def test_SIN_fila_de_consulta_nadie_pregunto_y_ni_la_consola_ni_el_papel_lo_niegan(
    esc: Escenario,
) -> None:
    """⚠️ La OTRA mitad del defecto central, y la del caso normal.

    Los tres hechos son distintos: **(a)** no se preguntó, **(b)** se preguntó y
    no contestaron, **(c)** contestaron y ninguno casa. Sólo (c) es una
    afirmación sobre el catálogo de referencia — lo exonera.

    Con la consulta ENCENDIDA y sin fila de intento —un incidente que acaba de
    entrar en revisión y al que la pasada todavía no ha llegado—, el ensamblado
    forense devolvía `sin_correlacion` y el dictamen firmaba «ningún sismo
    publicado satisface el criterio de identidad con este incidente». (a)
    impreso como (c): se exoneraba al catálogo sin haberlo interrogado. Y es el
    caso de TODOS los incidentes mientras la consulta se despliegue apagada,
    que es como se despliega.

    El estado por defecto venía del constructor de `CatalogCorrelation`, y la
    derivación desde el intento sólo corría `if consulta is not None`.
    """
    inc = esc.incidente()  # en revisión y SIN pasada: nadie le preguntó a nadie
    assert esc.consulta(inc) is None

    f = await _forense(inc)
    assert f.catalog_correlation.estado == P.SIN_DATO_EXTERNO, (
        "la superficie afirma que el catálogo no tiene este sismo, y nadie lo consultó"
    )
    assert f.catalog_correlation.fuente is None, "no hay fuente: no se preguntó a ninguna"
    assert f.catalog_correlation.consultado_en is None

    m = await _modelo(inc)
    assert m.catalog_line is not None, (
        "sin línea, el PDF imprime SIN_CORRELACION_EN_CATALOGO: el papel firma "
        "que ningún sismo publicado es éste sin haber preguntado a nadie"
    )
    assert m.catalog_line.startswith(SIN_CONSULTA_A_FUENTE_EXTERNA)
    assert "SIN CORRELACIÓN" not in m.catalog_line


# ---- el cerrojo de SESIÓN: la fuga que mataba la pasada para siempre --------


def _cerrojo_libre() -> bool:
    """¿Está el advisory lock de la pasada sin tomar? Desde OTRA conexión.

    Se toma y se suelta: `pg_try_advisory_lock` es la única forma de saberlo que
    no depende de interpretar el desdoblamiento `classid`/`objid` de `pg_locks`.
    """
    otra = psycopg.connect(dsn(), autocommit=True, row_factory=dict_row)
    try:
        libre = otra.execute(
            "SELECT pg_try_advisory_lock(%s) AS t",
            (C._CONSULTA_LOCK_KEY,),  # noqa: SLF001
        ).fetchone()["t"]
        if libre:
            otra.execute("SELECT pg_advisory_unlock(%s)", (C._CONSULTA_LOCK_KEY,))  # noqa: SLF001
        return bool(libre)
    finally:
        otra.close()


def test_un_fallo_de_la_pasada_SUELTA_el_cerrojo_y_no_tapa_la_excepcion(
    esc: Escenario, monkeypatch
) -> None:
    """⚠️ El cerrojo es de SESIÓN, y el `finally` lo soltaba sobre la transacción.

    Si la consulta de candidatos falla, la transacción queda ABORTADA. El
    `finally` ejecutaba entonces `SELECT pg_advisory_unlock(...)` sobre ella y
    pasaban las dos cosas a la vez:

    1. el `execute` reventaba con `InFailedSqlTransaction` y **sustituía** a la
       excepción original —una excepción lanzada en un `finally` se lleva por
       delante la que iba en vuelo—, así que en el log no salía el fallo de
       verdad;
    2. el cerrojo se quedaba tomado en `work_conn`, que el motor del worker
       **no cierra**: a partir de ahí todas las pasadas caían en la rama «otra
       instancia lo tiene» y el subsistema quedaba muerto.

    Se mide con el fallo más barato de provocar y el más probable: la consulta
    de candidatos rota.
    """
    assert _cerrojo_libre(), "el cerrojo venía tomado de otra prueba"
    monkeypatch.setattr(C, "_CANDIDATOS_SQL", "SELECT esta_columna_no_existe")

    with pytest.raises(psycopg.errors.UndefinedColumn):
        esc.pasada(_sirve(geojson([])))

    assert _cerrojo_libre(), (
        "la pasada murió con el cerrojo tomado: como es de SESIÓN y el motor no "
        "cierra la conexión, ninguna pasada volvería a entrar jamás"
    )


def test_si_otra_instancia_tiene_el_cerrojo_la_pasada_lo_DICE(esc: Escenario, caplog) -> None:
    """No preguntar es correcto; no decirlo es el no-op silencioso.

    Esta rama es el destino de cualquier fuga del cerrojo (ver la prueba de
    arriba), y no escribía una sola línea: la pasada devolvía un resultado vacío
    idéntico al de «no había nada que preguntar». Un subsistema muerto y uno
    ocioso tienen que leerse distinto en el log — es el modo de fallo que este
    repositorio ya se cobró varias veces.
    """
    inc = esc.incidente()
    otra = psycopg.connect(dsn(), autocommit=True, row_factory=dict_row)
    try:
        otra.execute("SELECT pg_advisory_lock(%s)", (C._CONSULTA_LOCK_KEY,))  # noqa: SLF001

        def no_deberia(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
            raise AssertionError("se preguntó con el cerrojo en manos de otra instancia")

        with caplog.at_level(logging.INFO, logger="takab_api.catalogo"):
            out = esc.pasada(httpx.MockTransport(no_deberia))
    finally:
        otra.close()

    assert out.consultados == ()
    assert esc.consulta(inc) is None
    dicho = "\n".join(r.getMessage() for r in caplog.records)
    assert "cerrojo" in dicho, (
        f"la pasada no preguntó nada y no lo dijo: el log de la vuelta es {dicho!r}"
    )


# ---- un reintento sin respuesta NO puede borrar la respuesta anterior -------


def test_un_reintento_SIN_RESPUESTA_no_borra_la_correlacion_que_ya_habia(
    esc: Escenario,
) -> None:
    """⚠️ Un fallo de red DEGRADABA un dato bueno. Eso es perder información.

    Desde que un `preliminar` se re-pregunta por su propio reloj, la rama «no
    contestó» le cae a filas que YA habían correlacionado. Escribía por el mismo
    UPDATE que el desenlace bueno, con `answered=None` y `key=None`: diez
    segundos sin red borraban `answered_at`, la clave del sismo y el detalle, y
    la superficie pasaba de `preliminar` —con su magnitud citable— a
    `consultando`. La fuente había contestado; el sistema decía que no.

    Lo que SÍ cambia es lo que de verdad pasó: `attempts`, `last_attempt_at` y
    una nota al final del detalle.
    """
    inc = _valdez(esc)
    ahora = ORIGEN_VALDEZ + timedelta(minutes=10)
    esc.pasada(_sirve(cruda(CRUDA_AUTOMATICA)), now=ahora)
    buena = esc.consulta(inc)
    assert buena["outcome"] == "correlacionado" and buena["answered_at"] == ahora

    def sin_red(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    refresco = Settings().catalog_usgs_refresco_preliminar_s
    despues = ahora + timedelta(seconds=refresco + 60)
    assert esc.pasada(httpx.MockTransport(sin_red), now=despues).sin_respuesta == (inc,)

    fila = esc.consulta(inc)
    assert fila["answered_at"] == buena["answered_at"], "el fallo de red borró que contestó"
    assert fila["catalog_key"] == buena["catalog_key"], "el fallo de red borró el sismo que casó"
    assert fila["outcome"] == "correlacionado"
    assert "estado en la fuente 'automatic'" in fila["detail"], "y borró el detalle de la buena"
    # El intento fallido no se calla: queda en las dos cifras y en una nota.
    assert fila["attempts"] == 2
    assert fila["last_attempt_at"] == despues
    assert "REINTENTO SIN RESPUESTA" in fila["detail"] and "ConnectError" in fila["detail"]

    # Y la DERIVACIÓN, que es lo que ve la superficie: sigue siendo `preliminar`
    # —con su cifra citable— y no `consultando`.
    ref = esc.conn.execute(
        "SELECT source, consulted_at, review_status, provider_event_id"
        " FROM reference_earthquakes WHERE catalog_key = %s",
        (fila["catalog_key"],),
    ).fetchone()
    assert P.de_consulta(dict(fila), dict(ref)).estado == P.PRELIMINAR

    # La nota se REEMPLAZA, no se acumula: en la ventana de revisión caben seis
    # refrescos y el detalle no puede convertirse en un log.
    def tampoco(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("se acabó el tiempo", request=request)

    mas_tarde = despues + timedelta(seconds=refresco + 60)
    esc.pasada(httpx.MockTransport(tampoco), now=mas_tarde)
    ultima = esc.consulta(inc)
    assert ultima["detail"].count("REINTENTO SIN RESPUESTA") == 1
    assert "ReadTimeout" in ultima["detail"] and "ConnectError" not in ultima["detail"]
    assert "estado en la fuente 'automatic'" in ultima["detail"]
