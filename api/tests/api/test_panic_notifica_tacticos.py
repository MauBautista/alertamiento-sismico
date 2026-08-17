"""[T-2.147.a · D-05 · D-11] El quórum de pánico abre incidente y despierta a los tácticos.

Hasta hoy `panic_vote` alcanzaba quórum, emitía el comando firmado de sirena,
consumía los votos y **ahí acababa**: la ruta del voto no tocaba `notify/`. Los
tácticos se enteraban en el siguiente sondeo de la app —30 s en reposo— y nadie
más se enteraba de nada.

`D-05` decidió QUÉ pasa: push **solo a los tácticos**. No a todo el edificio,
porque dos personas no deben poder despertar a 400 — un pánico falso a las
3 a.m. quema la credibilidad que hace que la gente obedezca la SIGUIENTE alerta,
que puede ser la de verdad.

`D-11` decidió POR DÓNDE: toda la maquinaria de notificación cuelga de un
incidente (`notification_jobs.incident_id` es NOT NULL) y el pánico no abría
ninguno. Ahora abre uno con `trigger='manual'`, valor que el CHECK del esquema
contemplaba y que nadie producía.

QUÉ PRUEBA ESTE ARCHIVO Y QUÉ NO
--------------------------------
Aquí solo el HECHO que deja el router: el incidente. El encolado del push y el
filtro por rol viven en `tests/notify/test_panic_push_tacticos.py`, porque los
encola el WORKER — `notification_jobs` tiene RLS que solo admite escrituras de
los roles internos, y una petición de occupant no lo es.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.anyio

KEY = "clave-panic-notify"
THING = "gw-panic-notify"
GW = "7c500000-0000-0000-0000-0000000000d2"
SITE = "7c500000-0000-0000-0000-00000000015e"
ZONE = "7c500000-0000-0000-0000-0000000000e2"
OCC_A = "70000000-0000-0000-0000-0000000cc101"
OCC_B = "70000000-0000-0000-0000-0000000cc102"
SITE_LON, SITE_LAT = -98.3014, 19.0633


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def publisher() -> _FakePublisher:
    return _FakePublisher()


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def sitio(base_data) -> None:
    """Sitio con dos occupants votantes y un táctico, los tres con token de push."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-PANIC-N', 'Sitio pánico notify', "
                "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE, "t": au.DB_TENANT_PRIV, "lon": SITE_LON, "lat": SITE_LAT},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-PANIC-N', :thing) ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW, "t": au.DB_TENANT_PRIV, "s": SITE, "thing": THING},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'PB') ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONE, "t": au.DB_TENANT_PRIV, "s": SITE},
        )
        for user in (OCC_A, OCC_B):
            await conn.execute(
                text(
                    "INSERT INTO user_zone_assignments "
                    "(user_id, tenant_id, site_id, zone_id, role) "
                    "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "t": au.DB_TENANT_PRIV, "s": SITE, "z": ZONE},
            )
        await conn.execute(
            text("DELETE FROM manual_activation_votes WHERE site_id = :s"), {"s": SITE}
        )
        await conn.execute(
            text(
                "DELETE FROM notification_jobs WHERE incident_id IN "
                "(SELECT incident_id FROM incidents WHERE site_id = :s)"
            ),
            {"s": SITE},
        )
        await conn.execute(text("DELETE FROM incidents WHERE site_id = :s"), {"s": SITE})


def _occ(user_id: str) -> str:
    return au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=user_id)


async def _vote(client, token: str):
    return await client.post(
        f"/sites/{SITE}/manual-activation-votes", json={}, headers=au.bearer(token)
    )


async def _incidentes() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT incident_id, trigger, severity, state, summary "
                    "FROM incidents WHERE site_id = :s"
                ),
                {"s": SITE},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def _jobs() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT channel, mode, status, target FROM notification_jobs "
                    "WHERE incident_id IN (SELECT incident_id FROM incidents WHERE site_id = :s)"
                ),
                {"s": SITE},
            )
        ).mappings()
        return [dict(r) for r in rows]


# --- Un voto no es un incidente ---------------------------------------------


async def test_un_solo_voto_no_abre_incidente(client, sitio) -> None:
    """La invariante de siempre, ahora también del lado del incidente.

    Un voto JAMÁS activa; si además abriera incidente, cada pulsación suelta
    dejaría una emergencia abierta en el SOC — y el SOC dejaría de creerlas.
    """
    resp = await _vote(client, _occ(OCC_A))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "counted"
    assert await _incidentes() == [], "un solo voto abrió un incidente"
    assert await _jobs() == [], "un solo voto encoló una notificación"


# --- El quórum sí ------------------------------------------------------------


async def test_el_quorum_abre_incidente_manual(client, sitio) -> None:
    """`trigger='manual'`: registra el hecho SIN llamarlo sismo.

    El valor lo contemplaba el CHECK del esquema desde el principio y nadie lo
    producía. Que sea `manual` y no `quorum` importa: `quorum` es el de ≥3
    inmuebles sacudiendo a la vez, que SÍ puede ordenar evacuar.
    """
    assert (await _vote(client, _occ(OCC_A))).status_code == 200
    resp = await _vote(client, _occ(OCC_B))
    assert resp.json()["status"] == "activated", resp.text

    incidentes = await _incidentes()
    assert len(incidentes) == 1, f"se esperaba un incidente, hay {len(incidentes)}"
    inc = incidentes[0]
    assert inc["trigger"] == "manual", (
        f"el incidente del pánico nació con trigger={inc['trigger']!r}: "
        "'sasmex' o 'quorum' lo presentarían como sísmico, que es la mentira de T-2.104"
    )
    assert inc["state"] == "open"
    assert inc["summary"]["source"] == "panic_quorum"
