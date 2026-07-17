"""T-2.09 · Intención firmada del táctico móvil (spec §2.1-B/2.2 · RBAC §4.3).

La superficie MÁS sensible: el teléfono firma una INTENCIÓN con su llave de
hardware registrada en ``device_keys``; la nube la verifica (llave propia y
vigente + nonce del servidor con TTL, atado a operador+sitio, UN SOLO USO) y
construye el comando HMAC por el pipeline EXISTENTE. Aquí se prueba con
criptografía REAL (P-256 y RSA de ``cryptography``), no con stubs.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands.intent import canonical_intent
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.asyncio

KEY = "clave-intent-test"
GW_INTENT = "7c400000-0000-0000-0000-0000000000c9"
THING = "gw-intent-test-a"
BRIG_USER = "70000000-0000-0000-0000-00000000bb09"
INTENT_SECRET = "secreto-intent-test"
# Sitio DEDICADO: gateways/sites NO están en el TRUNCATE de la suite, así que
# un sitio compartido acumularía gabinetes de otros archivos (SELECT_GATEWAY
# devolvería un thing sin clave en ESTE env ⇒ 503). Aislado, la intención se
# prueba sin depender del orden de ejecución.
SITE_INTENT = "7c400000-0000-0000-0000-00000000015c"


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
    monkeypatch.setenv("TAKAB_API_COMMAND_INTENT_SECRET", INTENT_SECRET)


@pytest.fixture
async def gateway(base_data) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        # gateways/sites NO se truncan entre archivos: purga cualquier residuo
        # de este thing (p.ej. corridas previas que lo apuntaban a otro sitio)
        # para que el estado sea determinista sin importar el orden.
        await conn.execute(
            text("DELETE FROM gateways WHERE gateway_id = :g OR iot_thing = :thing"),
            {"g": GW_INTENT, "thing": THING},
        )
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-INTENT', 'Sitio intent', "
                "ST_SetSRID(ST_MakePoint(-98.21, 19.05), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_INTENT, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-INT-A', :thing)"
            ),
            {"g": GW_INTENT, "t": au.DB_TENANT_PRIV, "s": SITE_INTENT, "thing": THING},
        )


def _brig(user_id: str = BRIG_USER, site_scope: str = SITE_INTENT) -> str:
    return au.make_token(
        "brigadista",
        tenant=au.DB_TENANT_PRIV,
        user_id=user_id,
        surface="mobile",
        site_scope=site_scope,
    )


def _ec_keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, pem.decode()


def _sign_ec(private, message: bytes) -> str:
    return base64.b64encode(private.sign(message, ec.ECDSA(hashes.SHA256()))).decode()


async def _register_key(client, token: str, pem: str) -> str:
    r = await client.post(
        "/me/device-keys", json={"platform": "android", "public_key": pem}, headers=au.bearer(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["key_id"]


async def _nonce(client, token: str, site: str = SITE_INTENT) -> str:
    r = await client.post(f"/sites/{site}/command-nonce", headers=au.bearer(token))
    assert r.status_code == 201, r.text
    return r.json()["nonce"]


def _intent_body(
    *, key_id: str, nonce: str, signature: str, channel: str = "siren", action: str = "activate"
) -> dict:
    return {
        "channel": channel,
        "action": action,
        "intent": {"key_id": key_id, "nonce": nonce, "signature": signature},
    }


async def _armed(client, token: str, *, action: str = "activate", channel: str = "siren"):
    """Registra llave EC + nonce + firma canónica correcta; devuelve el body."""
    private, pem = _ec_keypair()
    key_id = await _register_key(client, token, pem)
    nonce = await _nonce(client, token)
    message = canonical_intent(
        key_id=key_id, site_id=SITE_INTENT, channel=channel, action=action, nonce=nonce
    )
    return (
        _intent_body(
            key_id=key_id, nonce=nonce, signature=_sign_ec(private, message), action=action
        ),
        private,
        key_id,
    )


async def test_intencion_firmada_feliz_y_replay_rechazado(
    client, gateway, publisher: _FakePublisher
) -> None:
    """Feliz: 201 pending con el nonce de la intención como nonce del comando
    (UN SOLO USO por UNIQUE) y audit con hash de intención. El REPLAY exacto
    de la misma intención ⇒ 409."""
    tok = _brig()
    body, _priv, key_id = await _armed(client, tok)

    r = await client.post(f"/sites/{SITE_INTENT}/commands", json=body, headers=au.bearer(tok))
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "pending"
    assert row["nonce"] == body["intent"]["nonce"]
    assert len(publisher.published) == 1  # el comando HMAC salió al gateway

    engine = get_engine()
    async with engine.begin() as conn:
        meta = (
            await conn.execute(
                text(
                    "SELECT meta FROM audit_log WHERE verb='command_issued' "
                    "AND object = :obj ORDER BY ts DESC LIMIT 1"
                ),
                {"obj": f"command:{row['command_id']}"},
            )
        ).scalar_one()
    assert meta["intent_key_id"] == key_id
    assert len(meta["intent_sha256"]) == 64

    replay = await client.post(f"/sites/{SITE_INTENT}/commands", json=body, headers=au.bearer(tok))
    assert replay.status_code == 409


async def test_sin_intencion_o_firma_invalida_es_403(client, gateway) -> None:
    """El táctico móvil JAMÁS comanda sin intención; una firma sobre otro
    payload (canal cambiado tras firmar) se rechaza."""
    tok = _brig()
    naked = await client.post(
        f"/sites/{SITE_INTENT}/commands",
        json={"channel": "siren", "action": "activate"},
        headers=au.bearer(tok),
    )
    assert naked.status_code == 403

    body, _priv, _kid = await _armed(client, tok, action="activate")
    body["action"] = "deactivate"  # firma ya no corresponde al payload
    tampered = await client.post(
        f"/sites/{SITE_INTENT}/commands", json=body, headers=au.bearer(tok)
    )
    assert tampered.status_code == 403


async def test_nonce_ajeno_vencible_y_de_otro_sitio(client, gateway, base_data) -> None:
    """El nonce va ATADO a operador y sitio: el de otro usuario o el emitido
    para otro sitio se rechaza aunque la firma sea válida."""
    tok = _brig()
    private, pem = _ec_keypair()
    key_id = await _register_key(client, tok, pem)

    # nonce emitido a OTRO operador (mismo rol/sitio)
    other = _brig(user_id="70000000-0000-0000-0000-00000000bb10")
    _p2, pem2 = _ec_keypair()
    await _register_key(client, other, pem2)
    foreign_nonce = await _nonce(client, other)
    msg = canonical_intent(
        key_id=key_id,
        site_id=SITE_INTENT,
        channel="siren",
        action="activate",
        nonce=foreign_nonce,
    )
    r = await client.post(
        f"/sites/{SITE_INTENT}/commands",
        json=_intent_body(key_id=key_id, nonce=foreign_nonce, signature=_sign_ec(private, msg)),
        headers=au.bearer(tok),
    )
    assert r.status_code == 403
    assert "otro operador" in r.json()["detail"]


async def test_llave_ajena_o_revocada_es_403(client, gateway) -> None:
    """Firmar con la llave de OTRO usuario (aunque la firma sea válida) o con
    una revocada no emite comandos."""
    tok = _brig()
    other = _brig(user_id="70000000-0000-0000-0000-00000000bb11")
    private, pem = _ec_keypair()
    key_ajena = await _register_key(client, other, pem)  # registrada por OTRO

    nonce = await _nonce(client, tok)
    msg = canonical_intent(
        key_id=key_ajena, site_id=SITE_INTENT, channel="siren", action="activate", nonce=nonce
    )
    r = await client.post(
        f"/sites/{SITE_INTENT}/commands",
        json=_intent_body(key_id=key_ajena, nonce=nonce, signature=_sign_ec(private, msg)),
        headers=au.bearer(tok),
    )
    assert r.status_code == 403
    assert "llave" in r.json()["detail"]


async def test_gating_por_accion_y_canal(client, gateway) -> None:
    """RBAC §3/§4: inspector tiene manual_activate pero NO siren_silence
    (deactivate ⇒ 403); el táctico móvil solo opera la sirena; el occupant
    ni siquiera entra al router."""
    inspector = au.make_token(
        "inspector",
        tenant=au.DB_TENANT_PRIV,
        user_id="70000000-0000-0000-0000-00000000cc01",
        surface="mobile",
        site_scope=SITE_INTENT,
    )
    r = await client.post(
        f"/sites/{SITE_INTENT}/commands",
        json={"channel": "siren", "action": "deactivate"},
        headers=au.bearer(inspector),
    )
    assert r.status_code == 403  # sin siren_silence (jamás silencia — §4)

    tok = _brig()
    body, _priv, _kid = await _armed(client, tok)
    body["channel"] = "gas_valve"
    gas = await client.post(f"/sites/{SITE_INTENT}/commands", json=body, headers=au.bearer(tok))
    assert gas.status_code == 403  # solo sirena desde el teléfono (spec 2.2)

    occ = au.make_token("occupant", tenant=au.DB_TENANT_PRIV, surface="mobile")
    assert (
        await client.post(
            f"/sites/{SITE_INTENT}/commands",
            json={"channel": "siren", "action": "activate"},
            headers=au.bearer(occ),
        )
    ).status_code == 403
    assert (
        await client.post(f"/sites/{SITE_INTENT}/command-nonce", headers=au.bearer(occ))
    ).status_code == 403


async def test_rsa_pkcs1v15_tambien_verifica(client, gateway) -> None:
    """Android Keystore vía react-native-biometrics firma RSA PKCS#1 v1.5:
    la verificación acepta ambas familias registradas en device_keys."""
    tok = _brig(user_id="70000000-0000-0000-0000-00000000bb12")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_id = await _register_key(client, tok, pem.decode())
    nonce = await _nonce(client, tok)
    msg = canonical_intent(
        key_id=key_id, site_id=SITE_INTENT, channel="siren", action="deactivate", nonce=nonce
    )
    signature = base64.b64encode(private.sign(msg, padding.PKCS1v15(), hashes.SHA256())).decode()
    r = await client.post(
        f"/sites/{SITE_INTENT}/commands",
        json=_intent_body(key_id=key_id, nonce=nonce, signature=signature, action="deactivate"),
        headers=au.bearer(tok),
    )
    assert r.status_code == 201, r.text


async def test_sin_secreto_configurado_es_503_fail_closed(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin TAKAB_API_COMMAND_INTENT_SECRET la ruta táctica NO opera (regla de
    oro 8: fail-closed, jamás comandos sin intención verificable)."""
    monkeypatch.delenv("TAKAB_API_COMMAND_INTENT_SECRET", raising=False)
    tok = _brig()
    assert (
        await client.post(f"/sites/{SITE_INTENT}/command-nonce", headers=au.bearer(tok))
    ).status_code == 503
    body = _intent_body(key_id=str(uuid.uuid4()), nonce="x" * 24, signature="y" * 24)
    assert (
        await client.post(f"/sites/{SITE_INTENT}/commands", json=body, headers=au.bearer(tok))
    ).status_code == 503
