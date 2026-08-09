"""T-2.86.b · `RO-8.e`: el rate-limit POR SITIO, el que nadie probaba.

`command_rate_site_per_min` estaba implementado en
`api/src/takab_api/commands/service.py` desde T-1.60 y **sin un solo test**: la
suite solo cubría el límite usuario+sitio (`RO-8.d`). La diferencia importa
porque son presupuestos distintos — dos operadores coordinados agotan el del
sitio sin que ninguno rebase el suyo, y nada se ponía rojo.

Lo que se fija aquí:
- el presupuesto del SITIO es común y no se multiplica por operadores;
- un tercer operador con su cuota intacta también se queda fuera;
- el 429 del sitio se distingue del 429 de usuario (motivo distinto en la
  bitácora, no solo un código repetido);
- agotarlo NO derrama al sitio vecino.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands import rejection_audit as ra
from takab_api.commands.publisher import PublishError
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.asyncio

KEY = "clave-rate-sitio"
THING = "gw-rate-site-a"
THING_B = "gw-rate-site-b"
GW_A = "7f600000-0000-0000-0000-0000000000ca"
GW_B = "7f600000-0000-0000-0000-0000000000cb"
SITE_A = "7f600000-0000-0000-0000-00000000015a"
SITE_B = "7f600000-0000-0000-0000-00000000015b"

OP_1 = "7f600000-0000-0000-0000-000000000001"
OP_2 = "7f600000-0000-0000-0000-000000000002"
OP_3 = "7f600000-0000-0000-0000-000000000003"

BODY = {"channel": "siren", "action": "activate", "event_id": None}


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if not topic:
            raise PublishError("topic vacío")
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
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY, THING_B: KEY}))
    # Presupuesto del SITIO estrecho, y el de usuario MÁS ANCHO a propósito: si
    # el límite por sitio no existiera, ningún operador rebasaría el suyo y todo
    # saldría 201. Es exactamente el agujero que RO-8.e denunciaba.
    monkeypatch.setenv("TAKAB_API_COMMAND_RATE_SITE_PER_MIN", "3")
    monkeypatch.setenv("TAKAB_API_COMMAND_RATE_USER_SITE_PER_MIN", "10")


@pytest.fixture
async def sites(base_data) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM gateways WHERE gateway_id = ANY(:g) OR iot_thing = ANY(:th)"),
            {"g": [GW_A, GW_B], "th": [THING, THING_B]},
        )
        for sid, code, lon in ((SITE_A, "S-RATE-A", -98.41), (SITE_B, "S-RATE-B", -98.42)):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                    "(:s, :t, :c, 'Sitio rate', "
                    "ST_SetSRID(ST_MakePoint(:lon, 19.16), 4326)::geography) "
                    "ON CONFLICT (site_id) DO NOTHING"
                ),
                {"s": sid, "t": au.DB_TENANT_PRIV, "c": code, "lon": lon},
            )
        for gid, sid, thing, serial in (
            (GW_A, SITE_A, THING, "SER-RATE-A"),
            (GW_B, SITE_B, THING_B, "SER-RATE-B"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                    "VALUES (:g, :t, :s, :sn, :thing)"
                ),
                {"g": gid, "t": au.DB_TENANT_PRIV, "s": sid, "sn": serial, "thing": thing},
            )


def _op(user_id: str) -> str:
    return au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, user_id=user_id)


async def _post(client, site: str, user_id: str):
    return await client.post(f"/sites/{site}/commands", json=BODY, headers=au.bearer(_op(user_id)))


async def _reasons() -> list[str]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT meta FROM audit_log WHERE verb = :v ORDER BY audit_id"),
                {"v": ra.REJECTION_VERB},
            )
        ).scalars()
        return [r["reason"] for r in rows]


async def test_dos_operadores_coordinados_agotan_el_presupuesto_del_sitio(
    client, sites, publisher: _FakePublisher
) -> None:
    """Ninguno rebasa su cuota personal (10/min); el SITIO tiene 3/min."""
    assert (await _post(client, SITE_A, OP_1)).status_code == 201
    assert (await _post(client, SITE_A, OP_1)).status_code == 201
    assert (await _post(client, SITE_A, OP_2)).status_code == 201

    cuarto = await _post(client, SITE_A, OP_2)
    assert cuarto.status_code == 429, cuarto.text
    assert "sitio" in cuarto.json()["detail"]
    assert len(publisher.published) == 3  # el cuarto jamás salió al gabinete


async def test_un_tercer_operador_con_su_cuota_intacta_tambien_queda_fuera(
    client, sites, publisher: _FakePublisher
) -> None:
    """El presupuesto es del edificio, no de la persona: un operador que nunca
    ha comandado se topa igual con el techo del sitio."""
    for user in (OP_1, OP_1, OP_2):
        assert (await _post(client, SITE_A, user)).status_code == 201

    virgen = await _post(client, SITE_A, OP_3)
    assert virgen.status_code == 429, virgen.text
    assert len(publisher.published) == 3


async def test_el_429_del_sitio_se_distingue_del_429_del_usuario_en_la_bitacora(
    client, sites, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dos techos distintos ⇒ dos motivos distintos. Un 429 a secas no le dice a
    Protección Civil si se topó una persona o el edificio entero."""
    monkeypatch.setenv("TAKAB_API_COMMAND_RATE_USER_SITE_PER_MIN", "2")
    assert (await _post(client, SITE_A, OP_1)).status_code == 201
    assert (await _post(client, SITE_A, OP_1)).status_code == 201
    assert (await _post(client, SITE_A, OP_1)).status_code == 429  # su cuota
    assert (await _post(client, SITE_A, OP_2)).status_code == 201  # tercero del sitio
    assert (await _post(client, SITE_A, OP_2)).status_code == 429  # techo del sitio

    assert await _reasons() == ["rate_limit_user_site", "rate_limit_site"]


async def test_agotar_un_sitio_no_derrama_al_vecino(client, sites) -> None:
    """El presupuesto es POR sitio: el edificio de al lado sigue comandable."""
    for user in (OP_1, OP_1, OP_2):
        assert (await _post(client, SITE_A, user)).status_code == 201
    assert (await _post(client, SITE_A, OP_1)).status_code == 429

    assert (await _post(client, SITE_B, OP_1)).status_code == 201, "el vecino quedó bloqueado"
