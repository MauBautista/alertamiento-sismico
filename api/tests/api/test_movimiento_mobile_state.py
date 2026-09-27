"""[T-9.11 · D-39] `mobile-state` POR ROL: la brigada ve el movimiento, el ocupante nunca.

Un umbral local de UNA estación en DISPARO no ordena evacuar a nadie (T-2.105), y hasta
esta ficha `mobile-state` lo ocultaba a TODOS — también a la brigada, que era la única
que podía revisar el inmueble. Ahora quien tiene `movement_alert` ve la fase
`building_movement` con el incidente para atenderlo; el ocupante sigue en calma.
"""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.auth import deps
from takab_api.main import create_app
from tests.api.test_building_alarm_desde_el_acuse import (  # noqa: F401
    SITE_BA,
    _ack,
    _acuse_de_activacion,
    sitio_con_gabinete,
)

BRIG = "70000000-0000-0000-0000-00000000b911"
URL = f"/sites/{au.DB_SITE_PRIV}/mobile-state"


@pytest.fixture(autouse=True)
def _pools(monkeypatch: pytest.MonkeyPatch):
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _brigadista() -> dict[str, str]:
    return au.bearer(
        au.make_token(
            "brigadista",
            tenant=au.DB_TENANT_PRIV,
            user_id=BRIG,
            surface="mobile",
            site_scope=au.DB_SITE_PRIV,
        )
    )


def _ocupante() -> dict[str, str]:
    from tests.api.test_reingreso_persistente import _occ

    return _occ()


async def _estado(client, headers: dict[str, str]) -> dict:
    resp = await client.get(URL, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _enrolar_ocupante(client) -> None:
    from tests.api.test_reingreso_persistente import _enrolar

    await _enrolar(client)


@pytest.mark.anyio
@pytest.mark.parametrize("severity", ["warning", "critical"])
async def test_la_brigada_ve_el_movimiento_en_DISPARO(base_data, make_incident, severity) -> None:
    iid = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold", severity=severity
    )
    async with au.client_for(create_app()) as client:
        estado = await _estado(client, _brigadista())

    assert estado["phase"] == "building_movement"
    assert estado["incident"]["incident_id"] == iid, "sin el incidente no hay qué atender"
    assert estado["reentry"]["blocked"] is False, "un movimiento no ordenó salir a nadie"


@pytest.mark.anyio
async def test_el_ocupante_NUNCA_ve_el_movimiento(base_data, make_incident) -> None:
    await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold", severity="critical"
    )
    async with au.client_for(create_app()) as client:
        await _enrolar_ocupante(client)
        estado = await _estado(client, _ocupante())

    assert estado["phase"] == "idle", "el ocupante vio el movimiento: es el pánico de D-39"
    assert estado["incident"] is None


@pytest.mark.anyio
async def test_en_CAUTELA_ni_la_brigada(base_data, make_incident) -> None:
    await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold", severity="watch"
    )
    async with au.client_for(create_app()) as client:
        estado = await _estado(client, _brigadista())

    assert estado["phase"] == "idle"


@pytest.mark.anyio
async def test_un_SASMEX_abierto_manda_sobre_el_movimiento(base_data, make_incident) -> None:
    await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold", severity="critical"
    )
    sasmex = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    async with au.client_for(create_app()) as client:
        estado = await _estado(client, _brigadista())

    assert estado["phase"] == "alert_active"
    assert estado["incident"]["incident_id"] == sasmex


@pytest.mark.anyio
async def test_un_movimiento_CERRADO_ya_no_se_muestra(base_data, make_incident) -> None:
    await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="local_threshold",
        severity="critical",
        state="closed",
    )
    async with au.client_for(create_app()) as client:
        estado = await _estado(client, _brigadista())

    assert estado["phase"] == "idle"


# --- lo que la revisión de F1 encontró ------------------------------------------------


@pytest.mark.anyio
async def test_un_movimiento_EN_REVISION_ya_no_es_movimiento_vivo(base_data, make_incident) -> None:
    """El incidente pasa a `in_review` cuando el tier del sitio vuelve a `normal` y se
    cumple el retén: la sacudida terminó. Mostrarlo hasta el cierre (TTL de 6 h) tapaba
    todo lo que viniera después para la brigada."""
    await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="local_threshold",
        severity="critical",
        state="in_review",
    )
    async with au.client_for(create_app()) as client:
        estado = await _estado(client, _brigadista())

    assert estado["phase"] == "idle"


@pytest.mark.anyio
async def test_con_movimiento_Y_alarma_la_brigada_ve_LAS_DOS(
    make_incident,
    sitio_con_gabinete,  # noqa: F811
) -> None:
    """Una activación de pánico mientras el edificio se mueve: la fase es el movimiento,
    pero la alarma viva VIAJA en su campo para que la pantalla la explique y la brigada
    pueda acusarla. Antes `building_alarm` solo viajaba con su propia fase, y la brigada
    —justo quien tiene que atenderla— no sabía que sonaba."""
    await make_incident(au.DB_TENANT_PRIV, SITE_BA, trigger="local_threshold", severity="critical")
    await _acuse_de_activacion(_ack(None))
    token = au.make_token(
        "brigadista", tenant=au.DB_TENANT_PRIV, user_id=BRIG, surface="mobile", site_scope=SITE_BA
    )
    async with au.client_for(create_app()) as client:
        resp = await client.get(f"/sites/{SITE_BA}/mobile-state", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    estado = resp.json()

    assert estado["phase"] == "building_movement"
    assert estado["building_alarm"] is not None, "la alarma que suena quedó oculta a la brigada"
