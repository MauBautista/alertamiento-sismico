"""[T-2.120] El censo del relé llega del acuse al teléfono, por el endpoint real.

`tests/commands/test_building_alarm_desde_el_acuse.py` fija la regla pura. Este
test cubre lo que una función pura no puede: que el censo **sobreviva al SQL** —
``commands.ack->'channel_state'`` en ``queries/mobile.SIREN_ORDER``— y salga en
el contrato que lee la app (`GET /sites/{id}/mobile-state`).

Los dos caminos, y el orden importa:

1. **El gabinete de HOY** (`gw-dev-0001` corre el código anterior a `T-2.116`):
   su acuse no trae ``channel_state``. La alarma se anuncia igual y se declara
   ``source="order_inferred"``. Esto no es una rama de cortesía: es el caso que
   está corriendo en el campo mientras se escribe esto.
2. **El gabinete re-desplegado**: el acuse trae el censo. ``relay_measured``
   cuando el relé quedó activado, y **silencio** cuando el arbitraje no lo dejó
   activado, aunque la orden se ejecutara con éxito.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.anyio

# UUIDs propios (prefijo 7ba1 — libre: panic usa 7c50, deadlock 7e60).
GW_BA = "7ba10000-0000-0000-0000-0000000000d1"
SITE_BA = "7ba10000-0000-0000-0000-00000000015d"
ZONE_BA = "7ba10000-0000-0000-0000-0000000000e1"
OCC_BA = "7ba10000-0000-0000-0000-0000000cc001"
ADMIN_BA = "7ba10000-0000-0000-0000-0000000ad001"

#: El censo tal cual sale del gabinete real: vector compartido de `T-2.116`
#: (`edge/tests/vectors/command_ack_siren_arbitrado.json`, pata 1 del E2E).
CENSO_SONANDO = {
    "channel": "siren",
    "energized": True,
    "activated": True,
    "fail_safe": "NO",
    "reason": "alert",
    "alert_latched": True,
}
CENSO_EN_REPOSO = {**CENSO_SONANDO, "energized": False, "activated": False, "reason": None}


@pytest.fixture(autouse=True)
def _pool_de_ocupantes(monkeypatch: pytest.MonkeyPatch) -> None:
    """El ocupante vive en su propio pool de Cognito (spec móvil §5.1): sin esto
    su token es de otro issuer y la API responde 401."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def sitio_con_gabinete(base_data) -> None:
    """Sitio + gabinete latiendo + un ocupante asignado. Sin residuo al salir.

    `device_health` NO entra en el TRUNCATE de la suite y los tests de ingesta
    cuentan sus filas: el latido se borra explícitamente (misma disciplina que
    `panic_gw_latiendo` en `test_panic_quorum.py`).
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-BALARM', 'Sitio alarma', "
                "ST_SetSRID(ST_MakePoint(-98.3014, 19.0633), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_BA, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                "VALUES (:g, :t, :s, 'SER-BALARM') ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW_BA, "t": au.DB_TENANT_PRIV, "s": SITE_BA},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'PB') ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONE_BA, "t": au.DB_TENANT_PRIV, "s": SITE_BA},
        )
        await conn.execute(
            text(
                "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role) "
                "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
            ),
            {"u": OCC_BA, "t": au.DB_TENANT_PRIV, "s": SITE_BA, "z": ZONE_BA},
        )
        await conn.execute(
            text(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, relays_state) "
                "VALUES (now(), :t, :g, 'heartbeat', 'reported')"
            ),
            {"t": au.DB_TENANT_PRIV, "g": GW_BA},
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM device_health WHERE gateway_id = :g"), {"g": GW_BA})


async def _acuse_de_activacion(ack: dict[str, Any] | None) -> None:
    """Lo que deja el worker de ingesta al recibir el `CommandAck` del gabinete:
    ``status='acked'`` + el acuse crudo en ``commands.ack``. ``ack=None`` es el
    gabinete anterior a `T-2.116`, que ni siquiera trae la clave."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
                "action, nonce, issued_at, expires_at, status, ack) VALUES "
                "(:t, :s, :g, :u, 'siren', 'activate', :n, now(), "
                "now() + interval '30 seconds', 'acked', CAST(:ack AS jsonb))"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "s": SITE_BA,
                "g": GW_BA,
                "u": ADMIN_BA,
                # `nonce` es único en la tabla: uno por inserción, sin depender de
                # que el TRUNCATE entre tests llegue a tiempo.
                "n": f"nonce-balarm-{uuid.uuid4()}",
                "ack": json.dumps(ack) if ack is not None else None,
            },
        )


def _ack(channel_state: dict[str, Any] | None) -> dict[str, Any]:
    """El acuse completo tal cual lo persiste `handle_command_ack`."""
    base: dict[str, Any] = {
        "channel": "siren",
        "action": "activate",
        "success": True,
        "latency_s": 0.03,
        "executed_at": "2026-08-11T12:00:00Z",
        "detail": "relay",
        "results": None,
    }
    if channel_state is not None:
        base["channel_state"] = channel_state
    return base


async def _mobile_state(client) -> dict:
    token = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_BA)
    resp = await client.get(f"/sites/{SITE_BA}/mobile-state", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_el_gabinete_de_HOY_anuncia_la_alarma_como_INFERIDA(
    client, sitio_con_gabinete
) -> None:
    """El caso de campo: acuse sin `channel_state` (firmware ≤ schema 1.10.0).

    La alarma se anuncia —no se pierde nada de lo que `T-2.106` ya sostenía— y
    el contrato dice de dónde salió, para que la pantalla no pueda redactar como
    medición lo que es una deducción.
    """
    await _acuse_de_activacion(_ack(None))
    estado = await _mobile_state(client)
    assert estado["phase"] == "building_alarm"
    assert estado["building_alarm"]["since"] is not None
    assert estado["building_alarm"]["source"] == "order_inferred"


async def test_el_acuse_con_censo_anuncia_la_alarma_como_MEDIDA(client, sitio_con_gabinete) -> None:
    """Gabinete re-desplegado: el relé viaja en el acuse y llega hasta el JSON."""
    await _acuse_de_activacion(_ack(CENSO_SONANDO))
    estado = await _mobile_state(client)
    assert estado["phase"] == "building_alarm"
    assert estado["building_alarm"]["source"] == "relay_measured"


async def test_el_censo_EN_REPOSO_apaga_la_alarma_pese_al_acuse_exitoso(
    client, sitio_con_gabinete
) -> None:
    """El falso positivo que cierra esta ficha, por el endpoint real.

    ``status='acked'`` con ``success=true`` describe LA ORDEN. El censo describe
    EL RELÉ, y dice que el arbitraje no dejó la sirena activada. Con el método de
    `T-2.106` esto encendía la pantalla del inmueble entero.
    """
    await _acuse_de_activacion(_ack(CENSO_EN_REPOSO))
    estado = await _mobile_state(client)
    assert estado["phase"] == "idle"
    assert estado["building_alarm"] is None
