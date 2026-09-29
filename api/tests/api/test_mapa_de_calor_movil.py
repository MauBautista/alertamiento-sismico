"""[T-9.65 · D-44 · D-39] `GET /sites/{id}/mapa-de-calor`: cómo se sintió el último
sismo en el inmueble, para la app.

* Sólo POSTERIOR al evento (incidente en revisión o cerrado): D-44 limita la MMI
  estimada al después, y una superficie a medio calcular cambia cada minuto.
* Una prueba, un falso positivo o una reproducción no son «cómo se sintió».
* El ocupante sólo ve lo que le ORDENÓ algo (D-39): un movimiento local sin
  corroborar no existe para él, ni en vivo ni después.
* El PNG viaja DENTRO del JSON: el SDK nativo del mapa no manda cabeceras por
  fuente, y la ruta de la consola exige superficie web.

Y el mismo criterio en `GET /sites/{id}/historial-sismico`, que hasta aquí le
enseñaba al ocupante TODOS los incidentes del sitio.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.incident.classification import TERMINALES
from takab_api.main import create_app
from takab_api.shakemap import raster
from takab_api.shakemap import superficie as SUP

pytestmark = pytest.mark.usefixtures("base_data")

AHORA = datetime.now(tz=UTC)
OCUPANTE = str(uuid.uuid4())
#: Un SEGUNDO inmueble del mismo cliente. Los sitios no entran en el TRUNCATE de
#: teardown: lo crea y lo borra `otro_sitio`, para no cambiar el censo de otras suites.
OTRO_SITIO = "7a000000-0000-0000-0000-0000000000a9"
RUTA = f"/sites/{au.DB_SITE_PRIV}/mapa-de-calor"
PNG_FIRMA = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
def _pool_de_ocupantes(monkeypatch: pytest.MonkeyPatch) -> None:
    au.occupants_env(monkeypatch)


@pytest.fixture
async def app_client():
    async with au.client_for(create_app()) as client:
        yield client


def _ocupante() -> dict[str, str]:
    return au.bearer(au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCUPANTE))


def _tactico(
    role: str = "brigadista", *, tenant: str = au.DB_TENANT_PRIV, alcance: str = au.DB_SITE_PRIV
) -> dict[str, str]:
    return au.bearer(
        au.make_token(
            role,
            tenant=tenant,
            user_id=str(uuid.uuid4()),
            surface="mobile",
            site_scope=alcance,
        )
    )


@pytest.fixture
async def otro_sitio():
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (:s, :t,"
                " 'B2SA-OTRO', 'Otro inmueble', ST_SetSRID(ST_MakePoint(-98.2, 19.04), 4326)"
                "::geography) ON CONFLICT DO NOTHING"
            ),
            {"s": OTRO_SITIO, "t": au.DB_TENANT_PRIV},
        )
    yield OTRO_SITIO
    async with get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM incidents WHERE site_id = :s"), {"s": OTRO_SITIO})
        await conn.execute(text("DELETE FROM sites WHERE site_id = :s"), {"s": OTRO_SITIO})


async def _enrolar_ocupante() -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, role) "
                "VALUES (:u, :t, :s, 'occupant') ON CONFLICT DO NOTHING"
            ),
            {"u": OCUPANTE, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV},
        )


def _superficie() -> SUP.Superficie:
    sup, motivo = SUP.estima(
        [
            SUP.Estacion(lat=19.43, lon=-99.13, pga_g=0.061, calibrado=True),
            SUP.Estacion(lat=19.30, lon=-99.20, pga_g=0.022, calibrado=True),
            SUP.Estacion(lat=19.50, lon=-99.00, pga_g=0.035, calibrado=False),
        ],
        SUP.EpicentroLey(lat=18.4, lon=-98.7, depth_km=57.0, magnitud=6.1),
    )
    assert sup is not None, motivo
    return sup


async def _incidente(
    *,
    hace: timedelta,
    trigger: str = "sasmex",
    estado: str = "in_review",
    clasificacion: str | None = None,
    corregida_a: str | None = None,
    con_superficie: bool = True,
    nodos: int | None = None,
    sitio: str = au.DB_SITE_PRIV,
) -> str:
    inc = str(uuid.uuid4())
    evento = None
    async with get_engine().begin() as conn:
        if nodos is not None:
            evento = f"EVT-{inc[:8]}"
            await conn.execute(
                text(
                    "INSERT INTO seismic_events (event_id, source, detected_at, meta) "
                    "VALUES (:e, 'local_quorum', :t, CAST(:m AS jsonb))"
                ),
                {"e": evento, "t": AHORA - hace, "m": f'{{"node_count": {nodos}}}'},
            )
        await conn.execute(
            text(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
                " severity, state, trigger, max_pga_g, event_id, closed_at) VALUES (:i,"
                " gen_random_uuid(), :t, :s, :o, 'critical', :estado, :trigger, 0.061, :e,"
                " CASE WHEN :estado = 'closed'"
                "      THEN CAST(:o AS timestamptz) + interval '1 hour' END)"
            ),
            {
                "i": inc,
                "t": au.DB_TENANT_PRIV,
                "s": sitio,
                "o": AHORA - hace,
                "estado": estado,
                "trigger": trigger,
                "e": evento,
            },
        )
        if clasificacion:
            primera = (
                await conn.execute(
                    text(
                        "INSERT INTO incident_classifications (tenant_id, incident_id,"
                        " classification, classified_by, classified_at) VALUES (:t, :i, :c,"
                        " gen_random_uuid(), now() - interval '1 hour') RETURNING classification_id"
                    ),
                    {"t": au.DB_TENANT_PRIV, "i": inc, "c": clasificacion},
                )
            ).scalar_one()
            if corregida_a:
                await conn.execute(
                    text(
                        "INSERT INTO incident_classifications (tenant_id, incident_id,"
                        " classification, classified_by, supersedes_id) VALUES (:t, :i, :c,"
                        " gen_random_uuid(), :sup)"
                    ),
                    {"t": au.DB_TENANT_PRIV, "i": inc, "c": corregida_a, "sup": primera},
                )
        await conn.execute(
            text(
                "INSERT INTO incident_shakemap (incident_id, tenant_id, estado, cobertura_km,"
                " superficie, superficie_motivo) VALUES (:i, :t, 'completo', 150,"
                " CAST(:sup AS jsonb), :motivo)"
            ),
            {
                "i": inc,
                "t": au.DB_TENANT_PRIV,
                "sup": json.dumps(_superficie().to_json()) if con_superficie else None,
                "motivo": None if con_superficie else "sin_calibrados",
            },
        )
    return inc


# --- el mapa de calor ------------------------------------------------------------


async def test_sin_evento_lo_dice(app_client) -> None:
    r = await app_client.get(RUTA, headers=_tactico())
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["incidente"]) == ("sin_evento", None)
    # El inmueble va SIEMPRE: el mapa de la app lo centra aunque no haya evento.
    assert cuerpo["sitio"] == pytest.approx({"lat": 19.43, "lon": -99.13})


async def test_la_ultima_superficie_viaja_con_su_png_y_lo_que_hace_falta_para_rotularla(
    app_client,
) -> None:
    await _incidente(hace=timedelta(days=9))
    inc = await _incidente(hace=timedelta(days=2), estado="closed")

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "disponible"
    ev = cuerpo["incidente"]
    assert ev["incident_id"] == inc
    assert datetime.fromisoformat(ev["opened_at"]) == pytest.approx(
        AHORA - timedelta(days=2), abs=timedelta(seconds=1)
    )
    sup = ev["superficie"]
    esperada = _superficie()
    caja = [esperada.oeste, esperada.sur, esperada.este, esperada.norte]
    assert sup["bbox"] == pytest.approx(caja)
    assert (sup["n_sensores"], sup["n_calibrados"]) == (esperada.n_sensores, esperada.n_calibrados)
    assert sup["cita_mmi"]
    assert sup["mmi_max_estimada"] is not None
    # Los cortes del SITIO, los mismos con que se pintó el PNG.
    assert sup["verde_max_g"] < sup["rojo_min_g"]
    assert base64.b64decode(sup["png_base64"]).startswith(PNG_FIRMA)


async def test_en_curso_no_se_ensena_la_de_antes_si(app_client) -> None:
    anterior = await _incidente(hace=timedelta(days=5))
    await _incidente(hace=timedelta(minutes=3), estado="open")
    await _incidente(hace=timedelta(minutes=4), estado="acked")

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == anterior


@pytest.mark.parametrize("clasificacion", sorted(TERMINALES))
async def test_una_prueba_un_falso_positivo_o_una_reproduccion_no_son_como_se_sintio(
    app_client, clasificacion: str
) -> None:
    anterior = await _incidente(hace=timedelta(days=5), clasificacion="real")
    await _incidente(hace=timedelta(days=1), estado="closed", clasificacion=clasificacion)

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == anterior


@pytest.mark.parametrize(
    ("primera", "vigente", "sale"),
    [("prueba", "real", True), ("real", "falso_positivo", False)],
)
async def test_manda_la_clasificacion_VIGENTE_no_la_primera(
    app_client, primera: str, vigente: str, sale: bool
) -> None:
    anterior = await _incidente(hace=timedelta(days=5))
    corregido = await _incidente(hace=timedelta(days=1), clasificacion=primera, corregida_a=vigente)

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == (corregido if sale else anterior)


async def test_la_superficie_de_OTRO_inmueble_del_mismo_cliente_no_es_la_suya(
    app_client, otro_sitio: str
) -> None:
    propio = await _incidente(hace=timedelta(days=5))
    await _incidente(hace=timedelta(days=1), sitio=otro_sitio)

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == propio


async def test_el_png_se_pinta_con_los_cortes_DEL_SITIO_y_la_leyenda_dice_los_mismos(
    app_client,
) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active,"
                " config) VALUES (:t, 'site', :s, 1, true, CAST(:c AS jsonb))"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "s": au.DB_SITE_PRIV,
                "c": json.dumps({"dictamen_v2": {"verde_max_g": 0.02, "rojo_min_g": 0.05}}),
            },
        )
    await _incidente(hace=timedelta(days=1))

    sup = (await app_client.get(RUTA, headers=_tactico())).json()["incidente"]["superficie"]
    assert (sup["verde_max_g"], sup["rojo_min_g"]) == (0.02, 0.05)
    esperado = raster.png(_superficie(), verde_max_g=0.02, rojo_min_g=0.05)
    assert base64.b64decode(sup["png_base64"]) == esperado


async def test_el_ultimo_sin_superficie_no_tapa_al_que_la_tiene(app_client) -> None:
    anterior = await _incidente(hace=timedelta(days=5))
    await _incidente(hace=timedelta(days=1), con_superficie=False)

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == anterior


@pytest.mark.parametrize("tactico", ["brigadista", "inspector", "tenant_admin"])
async def test_el_ocupante_no_ve_un_movimiento_local_sin_corroborar(
    app_client, tactico: str
) -> None:
    await _enrolar_ocupante()
    sasmex = await _incidente(hace=timedelta(days=5))
    local = await _incidente(hace=timedelta(days=1), trigger="local_threshold")

    del_ocupante = await app_client.get(RUTA, headers=_ocupante())
    assert del_ocupante.status_code == 200, del_ocupante.text
    assert del_ocupante.json()["incidente"]["incident_id"] == sasmex
    # La brigada, el inspector y el administrador sí: D-39 les manda el movimiento.
    del_tactico = await app_client.get(RUTA, headers=_tactico(tactico))
    assert del_tactico.status_code == 200, del_tactico.text
    assert del_tactico.json()["incidente"]["incident_id"] == local


async def test_un_local_que_la_red_corroboro_si_es_del_ocupante(app_client) -> None:
    await _enrolar_ocupante()
    corroborado = await _incidente(hace=timedelta(days=1), trigger="local_threshold", nodos=3)

    r = await app_client.get(RUTA, headers=_ocupante())
    assert r.json()["incidente"]["incident_id"] == corroborado


async def test_un_ocupante_no_enrolado_no_sabe_que_el_sitio_existe(app_client) -> None:
    r = await app_client.get(RUTA, headers=_ocupante())
    assert r.status_code == 404


async def test_otro_cliente_no_sabe_que_el_sitio_existe(app_client) -> None:
    await _incidente(hace=timedelta(days=1))
    r = await app_client.get(RUTA, headers=_tactico(tenant=au.DB_TENANT_PRIV2, alcance="*"))
    assert r.status_code == 404


async def test_un_tactico_con_otro_sitio_en_su_alcance_es_403(app_client) -> None:
    r = await app_client.get(RUTA, headers=_tactico(alcance=au.DB_SITE_PRIV2))
    assert r.status_code == 403


async def test_un_rol_sin_app_es_403(app_client) -> None:
    web = au.make_token("gov_operator", tenant=au.DB_TENANT_PRIV, surface="web")
    r = await app_client.get(RUTA, headers=au.bearer(web))
    assert r.status_code == 403


# --- el historial, con el mismo criterio ------------------------------------------


async def test_el_historial_del_ocupante_no_trae_movimientos_locales(app_client) -> None:
    await _enrolar_ocupante()
    sasmex = await _incidente(hace=timedelta(days=5), con_superficie=False)
    local = await _incidente(hace=timedelta(days=1), trigger="local_threshold")
    corroborado = await _incidente(hace=timedelta(days=2), trigger="local_threshold", nodos=3)
    ruta = f"/sites/{au.DB_SITE_PRIV}/historial-sismico"

    def ids(r) -> list[str]:  # noqa: ANN001 - respuesta de httpx
        assert r.status_code == 200, r.text
        return [e["incident_id"] for e in r.json()["eventos"] if e["tipo"] == "incidente"]

    assert ids(await app_client.get(ruta, headers=_ocupante())) == [corroborado, sasmex]
    assert ids(await app_client.get(ruta, headers=_tactico())) == [local, corroborado, sasmex]


async def test_el_sismo_que_correlaciono_un_local_oculto_SIGUE_en_el_historial_del_ocupante(
    app_client,
) -> None:
    """Un sismo real que sólo disparó a esta estación: el incidente local se le oculta
    al ocupante (D-39), pero el sismo PUBLICADO por USGS sigue siendo suyo. Antes se
    omitía por «ya va como incidente» aunque ese incidente no se le enseñara."""
    await _enrolar_ocupante()
    local = await _incidente(hace=timedelta(days=1), trigger="local_threshold")
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
                " epicenter, depth_km, source, source_ref, provider_event_id, origen, usgs_url)"
                " VALUES ('usCERCA', :t, 5.6, 'cerca', ST_SetSRID(ST_MakePoint(-99.0, 19.2),"
                " 4326)::geography, 20, 'USGS', 'cita', 'usCERCA', 'catalog_sync', NULL)"
            ),
            {"t": AHORA - timedelta(days=1)},
        )
        await conn.execute(
            text(
                "INSERT INTO catalog_consultations (incident_id, provider, tenant_id, asked_at,"
                " last_attempt_at, answered_at, outcome, catalog_key) VALUES (:i, 'USGS', :t,"
                " :o, :o, :o, 'correlacionado', 'usCERCA')"
            ),
            {"i": local, "t": au.DB_TENANT_PRIV, "o": AHORA - timedelta(days=1)},
        )
    ruta = f"/sites/{au.DB_SITE_PRIV}/historial-sismico"

    del_ocupante = (await app_client.get(ruta, headers=_ocupante())).json()["eventos"]
    assert [(e["tipo"], e.get("place")) for e in del_ocupante] == [("sismo", "cerca")]
    del_tactico = (await app_client.get(ruta, headers=_tactico())).json()["eventos"]
    assert [(e["tipo"], e.get("incident_id")) for e in del_tactico] == [("incidente", local)]
