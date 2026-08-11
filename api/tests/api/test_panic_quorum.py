"""T-2.13 · Pánico del occupant por quórum-de-2 (1.9 · RBAC §4.3).

Emergencia NO sísmica del inmueble: 2 votos de usuarios DISTINTOS en la ventana
⇒ sirena por el pipeline HMAC existente. Invariantes probados:
- 1 voto JAMÁS activa; 2 votos del MISMO usuario JAMÁS activan.
- 2 usuarios distintos en ventana ⇒ comando + audit + votos consumed.
- fuera de ventana ⇒ nada; GPS fuera de radio ⇒ descartado; SIN GPS ⇒ cuenta.
- solo ``occupant`` (panic_vote); rate-limit por usuario.
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

KEY = "clave-panic-test"
THING = "gw-panic-test"
GW_PANIC = "7c500000-0000-0000-0000-0000000000d1"
SITE_PANIC = "7c500000-0000-0000-0000-00000000015d"
ZONE_PANIC = "7c500000-0000-0000-0000-0000000000e1"
OCC_A = "70000000-0000-0000-0000-0000000cc001"
OCC_B = "70000000-0000-0000-0000-0000000cc002"
# Sitio en Cholula: el geofence usa este centro; el seed base usa el mismo geom.
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
async def panic_site(base_data) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-PANIC', 'Sitio pánico', "
                "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_PANIC, "t": au.DB_TENANT_PRIV, "lon": SITE_LON, "lat": SITE_LAT},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-PANIC', :thing) ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW_PANIC, "t": au.DB_TENANT_PRIV, "s": SITE_PANIC, "thing": THING},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'PB') ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONE_PANIC, "t": au.DB_TENANT_PRIV, "s": SITE_PANIC},
        )
        for user in (OCC_A, OCC_B):
            await conn.execute(
                text(
                    "INSERT INTO user_zone_assignments "
                    "(user_id, tenant_id, site_id, zone_id, role) "
                    "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "t": au.DB_TENANT_PRIV, "s": SITE_PANIC, "z": ZONE_PANIC},
            )
        # manual_activation_votes SÍ se trunca por suite; se limpia por si acaso.
        await conn.execute(
            text("DELETE FROM manual_activation_votes WHERE site_id = :s"), {"s": SITE_PANIC}
        )


def _occ(user_id: str) -> str:
    return au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=user_id)


async def _vote(client, token: str, location=None):
    body = {"location": location} if location is not None else {}
    return await client.post(
        f"/sites/{SITE_PANIC}/manual-activation-votes", json=body, headers=au.bearer(token)
    )


async def _count_votes() -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text("SELECT count(*) FROM manual_activation_votes WHERE site_id = :s"),
                {"s": SITE_PANIC},
            )
        ).scalar_one()


async def test_un_voto_jamas_activa(client, panic_site, publisher) -> None:
    r = await _vote(client, _occ(OCC_A))
    assert r.status_code == 200
    assert r.json()["status"] == "counted"
    assert r.json()["remaining"] == 1
    assert publisher.published == []


async def test_dos_votos_mismo_usuario_jamas_activan(client, panic_site, publisher) -> None:
    await _vote(client, _occ(OCC_A))
    r = await _vote(client, _occ(OCC_A))
    assert r.json()["status"] == "counted"
    assert r.json()["distinct_voters"] == 1  # el mismo usuario no suma quórum
    assert publisher.published == []


async def test_dos_usuarios_distintos_activan_y_consumen(client, panic_site, publisher) -> None:
    first = await _vote(client, _occ(OCC_A))
    assert first.json()["status"] == "counted"
    second = await _vote(client, _occ(OCC_B))
    assert second.json()["status"] == "activated"
    assert len(publisher.published) == 1  # sirena disparada por el pipeline HMAC
    _topic, envelope = publisher.published[0]
    assert envelope["payload"]["channel"] == "siren"
    assert envelope["payload"]["action"] == "activate"
    assert envelope["payload"]["source"] == "panic_quorum"

    engine = get_engine()
    async with engine.begin() as conn:
        unconsumed = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM manual_activation_votes "
                    "WHERE site_id = :s AND consumed = false"
                ),
                {"s": SITE_PANIC},
            )
        ).scalar_one()
        verbs = [
            r.verb
            for r in (
                await conn.execute(
                    text("SELECT verb FROM audit_log WHERE object = :o ORDER BY ts"),
                    {"o": f"site:{SITE_PANIC}"},
                )
            ).all()
        ]
    assert unconsumed == 0  # los votos del quórum quedaron consumed
    assert verbs.count("panic_vote") == 2  # todo voto audita


async def test_fuera_de_ventana_no_activa(client, panic_site, publisher) -> None:
    """Un voto viejo (>30 s) no cuenta para el quórum de la ventana."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO manual_activation_votes (tenant_id, site_id, user_id, created_at) "
                "VALUES (:t, :s, :u, now() - interval '90 seconds')"
            ),
            {"t": au.DB_TENANT_PRIV, "s": SITE_PANIC, "u": OCC_A},
        )
    r = await _vote(client, _occ(OCC_B))
    assert r.json()["status"] == "counted"  # solo 1 en ventana
    assert r.json()["distinct_voters"] == 1
    assert publisher.published == []


async def test_gps_fuera_de_radio_se_descarta(client, panic_site, publisher) -> None:
    # ~4 km al norte del sitio (fuera de los 500 m del radio default)
    r = await _vote(client, _occ(OCC_A), location=[SITE_LON, SITE_LAT + 0.04])
    assert r.json()["status"] == "discarded"
    assert await _count_votes() == 0  # el voto descartado NO se insertó
    assert publisher.published == []


async def test_gps_dentro_del_radio_cuenta(client, panic_site) -> None:
    r = await _vote(client, _occ(OCC_A), location=[SITE_LON, SITE_LAT])  # en el sitio
    assert r.json()["status"] == "counted"


async def test_solo_occupant_vota(client, panic_site) -> None:
    """El brigadista no vota pánico (usa manual_activate individual)."""
    brig = au.make_token(
        "brigadista", tenant=au.DB_TENANT_PRIV, surface="mobile", site_scope=SITE_PANIC
    )
    assert (await _vote(client, brig)).status_code == 403


# --- [T-2.106] la superficie que ve el ocupante ---------------------------------


@pytest.fixture
async def panic_gw_latiendo(panic_site):
    """Un latido fresco del gabinete del sitio de pánico, y sin residuo al salir.

    `device_health` NO entra en el TRUNCATE de la suite (porta seeds globales) y
    los tests de ingesta CUENTAN sus filas: un latido huérfano los rompe.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, relays_state) "
                "VALUES (now(), :t, :g, 'heartbeat', 'reported')"
            ),
            {"t": au.DB_TENANT_PRIV, "g": GW_PANIC},
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM device_health WHERE gateway_id = :g"), {"g": GW_PANIC})


async def _ack_de_ejecucion() -> None:
    """Lo que hace el worker de ingesta al recibir el CommandAck del gabinete:
    `pending → acked`. Vive fuera del proceso de la API, así que aquí se simula
    su efecto sobre la tabla — el camino real está probado en
    `tests/commands/test_ack_ingest.py`."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE commands SET status = 'acked' WHERE site_id = :s AND channel = 'siren'"),
            {"s": SITE_PANIC},
        )


async def _mobile_state(client, token: str) -> dict:
    resp = await client.get(f"/sites/{SITE_PANIC}/mobile-state", headers=au.bearer(token))
    assert resp.status_code == 200
    return resp.json()


async def test_un_panico_JAMAS_produce_alert_active(client, panic_gw_latiendo, publisher) -> None:
    """[T-2.106 · criterio 3] EL ANCLA, de arriba abajo y por el endpoint real.

    `alert_active` es la fase que toma la pantalla completa con la instrucción de
    evacuación sísmica. Un pánico de ocupantes NO es un sismo: es la alarma del
    inmueble. Este test recorre el camino entero —dos votos por el endpoint real,
    comando `siren/activate` firmado y publicado, ack de ejecución— y afirma que
    en NINGÚN punto la app recibe `alert_active`.

    Se comprueba además que el pánico no fabrica incidente (nunca lo hizo, y esa
    es justamente la razón por la que hasta hoy la app no mostraba nada) y que la
    fase nueva es `building_alarm`.
    """
    fases: list[str] = []

    # 1) Un voto: no hay quórum, no hay comando, no hay nada que anunciar.
    assert (await _vote(client, _occ(OCC_A))).json()["status"] == "counted"
    fases.append((await _mobile_state(client, _occ(OCC_A)))["phase"])

    # 2) Quórum: sirena firmada y publicada, pero el gabinete AÚN NO confirma su
    #    ejecución. La app no afirma que suena una sirena sin el ack (regla de
    #    oro 8 pide ack de ejecución; regla de oro 7 prohíbe pintarlo antes).
    assert (await _vote(client, _occ(OCC_B))).json()["status"] == "activated"
    assert len(publisher.published) == 1
    estado_sin_ack = await _mobile_state(client, _occ(OCC_A))
    fases.append(estado_sin_ack["phase"])
    assert estado_sin_ack["building_alarm"] is None

    # 3) El gabinete confirma que ejecutó: AHORA la app lo anuncia.
    await _ack_de_ejecucion()
    estado = await _mobile_state(client, _occ(OCC_A))
    fases.append(estado["phase"])

    assert "alert_active" not in fases, f"un pánico ordenó evacuar (fases: {fases})"
    assert fases == ["idle", "idle", "building_alarm"]
    assert estado["incident"] is None, "el pánico no fabrica incidente sísmico"
    assert estado["building_alarm"]["since"] is not None
    # Y no bloquea el reingreso: no hubo sismo del que volver.
    assert estado["reentry"]["blocked"] is False


async def test_la_alarma_se_apaga_cuando_alguien_silencia(
    client, panic_gw_latiendo, publisher
) -> None:
    """[T-2.106] Lo último que EJECUTÓ el relé manda. Un `siren/deactivate`
    posterior devuelve el sitio a `idle`: la app deja de anunciar una sirena que
    ya no suena (regla de oro 7 al derecho)."""
    await _vote(client, _occ(OCC_A))
    assert (await _vote(client, _occ(OCC_B))).json()["status"] == "activated"
    await _ack_de_ejecucion()
    assert (await _mobile_state(client, _occ(OCC_A)))["phase"] == "building_alarm"

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
                "action, nonce, issued_at, expires_at, status) VALUES "
                "(:t, :s, :g, :u, 'siren', 'deactivate', :n, now(), "
                "now() + interval '30 seconds', 'acked')"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "s": SITE_PANIC,
                "g": GW_PANIC,
                "u": OCC_B,
                "n": f"nonce-silencio-{SITE_PANIC}",
            },
        )
    estado = await _mobile_state(client, _occ(OCC_A))
    assert estado["phase"] == "idle"
    assert estado["building_alarm"] is None
