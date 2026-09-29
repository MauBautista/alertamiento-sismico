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
from takab_api.shakemap import superficie as SUP

pytestmark = pytest.mark.usefixtures("base_data")

AHORA = datetime.now(tz=UTC)
OCUPANTE = str(uuid.uuid4())
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


def _tactico(role: str = "brigadista") -> dict[str, str]:
    return au.bearer(
        au.make_token(
            role,
            tenant=au.DB_TENANT_PRIV,
            user_id=str(uuid.uuid4()),
            surface="mobile",
            site_scope=au.DB_SITE_PRIV,
        )
    )


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
    con_superficie: bool = True,
    nodos: int | None = None,
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
                "s": au.DB_SITE_PRIV,
                "o": AHORA - hace,
                "estado": estado,
                "trigger": trigger,
                "e": evento,
            },
        )
        if clasificacion:
            await conn.execute(
                text(
                    "INSERT INTO incident_classifications (tenant_id, incident_id,"
                    " classification, classified_by) VALUES (:t, :i, :c, gen_random_uuid())"
                ),
                {"t": au.DB_TENANT_PRIV, "i": inc, "c": clasificacion},
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


async def test_el_ultimo_sin_superficie_no_tapa_al_que_la_tiene(app_client) -> None:
    anterior = await _incidente(hace=timedelta(days=5))
    await _incidente(hace=timedelta(days=1), con_superficie=False)

    r = await app_client.get(RUTA, headers=_tactico())
    assert r.json()["incidente"]["incident_id"] == anterior


async def test_el_ocupante_no_ve_un_movimiento_local_sin_corroborar(app_client) -> None:
    await _enrolar_ocupante()
    sasmex = await _incidente(hace=timedelta(days=5))
    local = await _incidente(hace=timedelta(days=1), trigger="local_threshold")

    del_ocupante = await app_client.get(RUTA, headers=_ocupante())
    assert del_ocupante.status_code == 200, del_ocupante.text
    assert del_ocupante.json()["incidente"]["incident_id"] == sasmex
    # La brigada sí: D-39 le manda el movimiento a ella.
    del_brigadista = await app_client.get(RUTA, headers=_tactico())
    assert del_brigadista.json()["incidente"]["incident_id"] == local


async def test_un_local_que_la_red_corroboro_si_es_del_ocupante(app_client) -> None:
    await _enrolar_ocupante()
    corroborado = await _incidente(hace=timedelta(days=1), trigger="local_threshold", nodos=3)

    r = await app_client.get(RUTA, headers=_ocupante())
    assert r.json()["incidente"]["incident_id"] == corroborado


async def test_un_ocupante_no_enrolado_no_sabe_que_el_sitio_existe(app_client) -> None:
    r = await app_client.get(RUTA, headers=_ocupante())
    assert r.status_code == 404


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
