"""T-2.86.b · La bitácora de los actuadores también registra lo que NO pasó.

Huecos `RO-8.g` y `RO-8.k` de la matriz. La superficie que abre válvulas de gas
auditaba únicamente el camino feliz (`command_issued`): un atacante que sondease
con comandos repetidos era **invisible** en `audit_log`, que es justo donde se
investigaría el incidente.

Lo que estos tests fijan, y que no es negociable después:

1. **Todo rechazo posterior a la resolución del sitio queda auditado, con su
   motivo** — replay, rate-limit, firma de intención, llave desconocida, sin
   clave HMAC. Antes de resolver el sitio no se audita aquí: no se sabe a QUIÉN
   se le intentó tocar el gabinete (ver el docstring del módulo de origen).
2. **Auditar un rechazo no puede ser el vector.** `audit_log` es append-only y
   NUNCA se poda por retención (regla de oro 11): una fila por intento sin techo
   convierte la bitácora en el blanco. Hay presupuesto por (tenant, actor,
   ventana) y la última fila del presupuesto es una MARCA de agotamiento, no un
   detalle más — el silencio posterior queda declarado dentro de la propia tabla.
3. **El tenant del archivo es el TOCADO, no el del operador** (lección de
   T-2.71): quien pregunta "¿quién intentó abrir MI válvula?" es el dueño del
   edificio, y en su bitácora tiene que estar.
4. **Un rechazo por firma no asciende a hecho lo que no se probó.** La sesión SÍ
   está probada (el JWT valida contra Cognito, MFA a nivel de pool); el
   DISPOSITIVO no. El `key_id` que venía en la intención se archiva como
   *reclamado*, la firma jamás se archiva en claro y el nonce tampoco.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands import rejection_audit as ra
from takab_api.commands.intent import canonical_intent
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.asyncio

KEY = "clave-rechazo-test"
THING = "gw-reject-audit"
GW_REJ = "7e500000-0000-0000-0000-0000000000ce"
SITE_REJ = "7e500000-0000-0000-0000-00000000015e"
INTENT_SECRET = "secreto-rechazo-test"

BRIG = "7e500000-0000-0000-0000-0000000000b1"
BRIG_2 = "7e500000-0000-0000-0000-0000000000b2"
ADMIN = "7e500000-0000-0000-0000-0000000000a1"
SUPER = "7e500000-0000-0000-0000-0000000000f1"


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
    """Sitio y gabinete DEDICADOS: `sites`/`gateways` no entran al TRUNCATE de la
    suite, así que un sitio compartido acumularía things de otros ficheros."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM gateways WHERE gateway_id = :g OR iot_thing = :thing"),
            {"g": GW_REJ, "thing": THING},
        )
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-REJ', 'Sitio rechazo', "
                "ST_SetSRID(ST_MakePoint(-98.31, 19.15), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_REJ, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-REJ', :thing)"
            ),
            {"g": GW_REJ, "t": au.DB_TENANT_PRIV, "s": SITE_REJ, "thing": THING},
        )


# --- utilidades ----------------------------------------------------------------


async def _rejections() -> list[dict]:
    """Filas `command_rejected`, en orden de escritura."""
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tenant_id::text AS tenant_id, actor, object, meta "
                    "FROM audit_log WHERE verb = :v ORDER BY audit_id"
                ),
                {"v": ra.REJECTION_VERB},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def _rejections_as(tenant: str, role: str = "tenant_admin") -> list[dict]:
    """Lo mismo, pero BAJO RLS con el contexto de un tenant concreto: es la
    pregunta real del cliente ("¿qué se intentó contra MI edificio?")."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text('SET LOCAL ROLE "takab_app"'))
        await conn.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": tenant})
        await conn.execute(text("SELECT set_config('app.role', :v, true)"), {"v": role})
        rows = (
            await conn.execute(
                text(
                    "SELECT tenant_id::text AS tenant_id, object, meta "
                    "FROM audit_log WHERE verb = :v ORDER BY audit_id"
                ),
                {"v": ra.REJECTION_VERB},
            )
        ).mappings()
        return [dict(r) for r in rows]


def _brig(user_id: str = BRIG) -> str:
    return au.make_token(
        "brigadista",
        tenant=au.DB_TENANT_PRIV,
        user_id=user_id,
        surface="mobile",
        site_scope=SITE_REJ,
    )


def _admin(user_id: str = ADMIN, tenant: str = au.DB_TENANT_PRIV) -> str:
    return au.make_token("tenant_admin", tenant=tenant, user_id=user_id)


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


async def _nonce(client, token: str) -> str:
    r = await client.post(f"/sites/{SITE_REJ}/command-nonce", headers=au.bearer(token))
    assert r.status_code == 201, r.text
    return r.json()["nonce"]


async def _armed(client, token: str, *, action: str = "activate") -> tuple[dict, str]:
    """Intención VÁLIDA (llave registrada + nonce del servidor + firma buena)."""
    private, pem = _ec_keypair()
    key_id = await _register_key(client, token, pem)
    nonce = await _nonce(client, token)
    message = canonical_intent(
        key_id=key_id, site_id=SITE_REJ, channel="siren", action=action, nonce=nonce
    )
    body = {
        "channel": "siren",
        "action": action,
        "intent": {"key_id": key_id, "nonce": nonce, "signature": _sign_ec(private, message)},
    }
    return body, key_id


# --- RO-8.g · el replay deja huella ---------------------------------------------


async def test_replay_rechazado_queda_auditado_con_su_motivo(
    client, gateway, publisher: _FakePublisher
) -> None:
    """El sondeo con comandos repetidos deja de ser invisible."""
    tok = _brig()
    body, key_id = await _armed(client, tok)

    ok = await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert ok.status_code == 201, ok.text
    assert await _rejections() == []  # el camino feliz no ensucia la bitácora

    replay = await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert replay.status_code == 409

    rows = await _rejections()
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["meta"]["reason"] == "nonce_replay"
    assert row["meta"]["status"] == 409
    assert row["object"] == f"site:{SITE_REJ}"
    assert row["actor"] == f"user:{BRIG}"
    assert row["tenant_id"] == au.DB_TENANT_PRIV
    assert (row["meta"]["channel"], row["meta"]["action"]) == ("siren", "activate")
    # Honestidad sobre lo SABIDO: el replay se corta ANTES de verificar la firma
    # del dispositivo (así el nonce quemado no se convierte en oráculo para quien
    # tiene sesión pero no el teléfono). En ese instante lo probado es la sesión y
    # nada más, así que el key_id viaja como RECLAMADO y no como hecho.
    assert row["meta"]["actor_proof"] == "session"
    assert row["meta"]["claimed_intent_key_id"] == key_id
    assert "intent_key_id" not in row["meta"]
    assert len(publisher.published) == 1  # el replay nunca salió al gabinete


async def test_el_replay_no_archiva_el_nonce_ni_la_firma_en_claro(client, gateway) -> None:
    """`audit_log` guarda el HECHO, no la credencial (criterio de T-2.36)."""
    tok = _brig()
    body, _key_id = await _armed(client, tok)
    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))

    meta = json.dumps((await _rejections())[0]["meta"])
    assert body["intent"]["nonce"] not in meta
    assert body["intent"]["signature"] not in meta
    # …pero SÍ una huella, para correlacionar sondeos del mismo nonce.
    assert len((await _rejections())[0]["meta"]["nonce_sha256"]) == 64


# --- RO-8.k · lo que se intentó y no pasó ---------------------------------------


async def test_firma_de_intencion_invalida_queda_auditada_sin_creerse_el_dispositivo(
    client, gateway
) -> None:
    """La sesión está probada (el JWT valida); el DISPOSITIVO no.

    El `key_id` que viaja en una intención cuya firma NO verifica es un dato
    ofrecido por quien fue rechazado: se archiva como *reclamado*, jamás como
    identidad establecida.
    """
    tok = _brig()
    body, key_id = await _armed(client, tok, action="activate")
    body["action"] = "deactivate"  # la firma ya no corresponde al payload

    r = await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert r.status_code == 403, r.text

    rows = await _rejections()
    assert len(rows) == 1, rows
    meta = rows[0]["meta"]
    assert meta["reason"] == "intent_signature_invalid"
    assert meta["status"] == 403
    # Sabido: la sesión. NO sabido: que el teléfono con esa llave hiciera esto.
    assert meta["actor_proof"] == "session"
    assert meta["claimed_intent_key_id"] == key_id
    assert "intent_key_id" not in meta  # no se asciende lo reclamado a hecho
    assert body["intent"]["signature"] not in json.dumps(meta)


async def test_llave_de_dispositivo_desconocida_queda_auditada(client, gateway) -> None:
    tok = _brig()
    otro = _brig(user_id=BRIG_2)
    private, pem = _ec_keypair()
    key_ajena = await _register_key(client, otro, pem)  # registrada por OTRO usuario
    nonce = await _nonce(client, tok)
    msg = canonical_intent(
        key_id=key_ajena, site_id=SITE_REJ, channel="siren", action="activate", nonce=nonce
    )
    r = await client.post(
        f"/sites/{SITE_REJ}/commands",
        json={
            "channel": "siren",
            "action": "activate",
            "intent": {"key_id": key_ajena, "nonce": nonce, "signature": _sign_ec(private, msg)},
        },
        headers=au.bearer(tok),
    )
    assert r.status_code == 403

    rows = await _rejections()
    assert [r_["meta"]["reason"] for r_ in rows] == ["device_key_unknown"]
    assert rows[0]["meta"]["actor_proof"] == "session"
    assert rows[0]["meta"]["claimed_intent_key_id"] == key_ajena


async def test_nonce_de_otro_operador_queda_auditado_con_el_submotivo(client, gateway) -> None:
    """El nonce lo firma el servidor: reusar el de otro operador es un fallo de
    firma, y la bitácora dice CUÁL."""
    tok = _brig()
    private, pem = _ec_keypair()
    key_id = await _register_key(client, tok, pem)
    otro = _brig(user_id=BRIG_2)
    _p2, pem2 = _ec_keypair()
    await _register_key(client, otro, pem2)
    ajeno = await _nonce(client, otro)
    msg = canonical_intent(
        key_id=key_id, site_id=SITE_REJ, channel="siren", action="activate", nonce=ajeno
    )
    r = await client.post(
        f"/sites/{SITE_REJ}/commands",
        json={
            "channel": "siren",
            "action": "activate",
            "intent": {"key_id": key_id, "nonce": ajeno, "signature": _sign_ec(private, msg)},
        },
        headers=au.bearer(tok),
    )
    assert r.status_code == 403

    rows = await _rejections()
    assert len(rows) == 1
    assert rows[0]["meta"]["reason"] == "intent_nonce_rejected"
    assert "otro operador" in rows[0]["meta"]["detail"]


async def test_sin_clave_hmac_el_503_queda_auditado(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed POR GABINETE (T-1.38): el 503 es un comando que NO ocurrió y
    tiene que verse en la bitácora del edificio, no solo en un log de servidor."""
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({"otro-thing": "x"}))
    r = await client.post(
        f"/sites/{SITE_REJ}/commands",
        json={"channel": "siren", "action": "activate", "event_id": None},
        headers=au.bearer(_admin()),
    )
    assert r.status_code == 503

    rows = await _rejections()
    assert [r_["meta"]["reason"] for r_ in rows] == ["hmac_key_unresolvable"]
    assert rows[0]["meta"]["status"] == 503
    assert rows[0]["actor"] == f"user:{ADMIN}"
    # Consola web: la prueba es la sesión (MFA a nivel de pool), no un dispositivo.
    assert rows[0]["meta"]["actor_proof"] == "session"


async def test_rate_limit_por_usuario_queda_auditado(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TAKAB_API_COMMAND_RATE_USER_SITE_PER_MIN", "1")
    tok = _admin()
    body = {"channel": "siren", "action": "activate", "event_id": None}
    assert (
        await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    ).status_code == 201
    r = await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert r.status_code == 429

    rows = await _rejections()
    assert [r_["meta"]["reason"] for r_ in rows] == ["rate_limit_user_site"]
    assert rows[0]["meta"]["status"] == 429
    assert rows[0]["object"] == f"site:{SITE_REJ}"


# --- la auditoría del rechazo no puede ser el vector -----------------------------


async def test_el_sondeo_repetido_no_puede_inflar_la_bitacora_sin_techo(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`audit_log` es append-only y NUNCA se poda (regla de oro 11): una fila por
    intento sin techo convierte la propia bitácora en el blanco del ataque.

    Hay presupuesto por (tenant, actor, ventana). La ÚLTIMA fila del presupuesto
    no es un detalle más: es la marca de agotamiento, para que el silencio
    posterior esté declarado DENTRO de la tabla y no se lea como calma.
    """
    monkeypatch.setattr(ra, "AUDIT_BUDGET", 4)
    tok = _brig()
    body, _kid = await _armed(client, tok)
    assert (
        await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    ).status_code == 201

    for _ in range(12):  # doce sondeos con el MISMO nonce quemado
        replay = await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
        assert replay.status_code == 409  # la decisión de seguridad no cambia jamás

    rows = await _rejections()
    assert len(rows) == 4, [r_["meta"]["reason"] for r_ in rows]
    assert [r_["meta"]["reason"] for r_ in rows[:3]] == ["nonce_replay"] * 3
    assert rows[3]["meta"]["reason"] == ra.BUDGET_EXHAUSTED
    assert rows[3]["meta"]["suppressed_reason"] == "nonce_replay"
    assert rows[3]["meta"]["window_s"] == ra.AUDIT_WINDOW_S


async def test_el_presupuesto_de_un_actor_no_silencia_a_otro(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El techo se lleva por actor autenticado, que es lo NO rotable: el sitio de
    la URL lo elige quien ataca, el `sub` del token no."""
    monkeypatch.setattr(ra, "AUDIT_BUDGET", 2)
    ruidoso = _brig()
    body, _kid = await _armed(client, ruidoso)
    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(ruidoso))
    for _ in range(6):
        await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(ruidoso))

    limpio = _brig(user_id=BRIG_2)
    otro_body, _k = await _armed(client, limpio)
    await client.post(f"/sites/{SITE_REJ}/commands", json=otro_body, headers=au.bearer(limpio))
    replay = await client.post(
        f"/sites/{SITE_REJ}/commands", json=otro_body, headers=au.bearer(limpio)
    )
    assert replay.status_code == 409

    por_actor: dict[str, list[str]] = {}
    for row in await _rejections():
        por_actor.setdefault(row["actor"], []).append(row["meta"]["reason"])
    assert por_actor[f"user:{BRIG}"] == ["nonce_replay", ra.BUDGET_EXHAUSTED]
    assert por_actor[f"user:{BRIG_2}"] == ["nonce_replay"]


async def test_un_intento_rechazado_escribe_exactamente_una_fila(client, gateway) -> None:
    """Idempotencia (regla de oro 3): una petición ⇒ una fila. Dos sondeos
    distintos ⇒ dos filas — no se colapsan, que es justo lo que se investiga."""
    tok = _brig()
    body, _kid = await _armed(client, tok)
    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))

    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert len(await _rejections()) == 1
    await client.post(f"/sites/{SITE_REJ}/commands", json=body, headers=au.bearer(tok))
    assert len(await _rejections()) == 2


# --- el tenant del archivo es el TOCADO (T-2.71) ---------------------------------


async def test_el_rechazo_se_archiva_bajo_el_tenant_TOCADO_no_el_del_operador(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-2.71 se pagó una vez: quien pregunta "¿quién intentó abrir MI válvula?"
    es el dueño del edificio. Un interno de TAKAB (que ve todos los sitios) toca
    un gabinete ajeno y es rechazado: la fila vive en la bitácora del DUEÑO.
    """
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({"otro-thing": "x"}))
    interno = au.make_token(
        "takab_superadmin", tenant=au.DB_TENANT_PRIV2, user_id=SUPER, site_scope="*"
    )
    r = await client.post(
        f"/sites/{SITE_REJ}/commands",
        json={"channel": "gas_valve", "action": "activate", "event_id": None},
        headers=au.bearer(interno),
    )
    assert r.status_code == 503, r.text

    rows = await _rejections()
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == au.DB_TENANT_PRIV  # el TOCADO
    assert rows[0]["tenant_id"] != au.DB_TENANT_PRIV2  # no el del operador
    assert rows[0]["actor"] == f"user:{SUPER}"
    assert rows[0]["meta"]["channel"] == "gas_valve"

    # Y se ve bajo RLS desde el tenant dueño — y NO desde el del operador.
    assert len(await _rejections_as(au.DB_TENANT_PRIV)) == 1
    assert await _rejections_as(au.DB_TENANT_PRIV2) == []


# ---------------------------------------------------------------------------
# El valor que se DESPLIEGA, no solo el mecanismo
# ---------------------------------------------------------------------------
#
# Todos los tests de arriba monkeypatchean `AUDIT_BUDGET` a 2 o 4 para no escribir
# veinte filas por caso. Eso prueba el MECANISMO —presupuesto, marca de agotamiento,
# silencio declarado— pero deja sin anclar **el número que sale a producción**.
#
# Medido: subir `AUDIT_BUDGET` a 10**9 no pone ni un test en rojo. El mecanismo
# seguiría "funcionando" —hay techo— y el techo sería inútil: una inundación llenaría
# `audit_log`, que es append-only y **no se poda por retención** (regla de oro 11).
#
# Es la misma clase de hueco que esta fase lleva cazando: una guarda cuyo límite se
# puede aflojar sin que nadie se entere. El mecanismo es derivado; el valor es una
# decisión, y una decisión se ancla.


def test_el_presupuesto_QUE_SE_DESPLIEGA_sigue_siendo_una_cota_util() -> None:
    """El techo real tiene que caber en una tabla que nunca se poda."""
    assert 1 <= ra.AUDIT_BUDGET <= 100, (
        f"AUDIT_BUDGET = {ra.AUDIT_BUDGET}: un presupuesto grande deja de ser una cota. "
        "`audit_log` es append-only con REVOKE DELETE y no se poda por retención "
        "(regla de oro 11), así que estas filas se quedan para siempre. Si hace falta "
        "subirlo, cámbialo aquí también y escribe por qué."
    )
    assert 30.0 <= ra.AUDIT_WINDOW_S <= 3600.0, (
        f"AUDIT_WINDOW_S = {ra.AUDIT_WINDOW_S}: una ventana corta multiplica el "
        "presupuesto por el tiempo (una ventana de 1 s son 20 filas por segundo); una "
        "larga hace que un sondeo lento nunca se registre. Las dos direcciones importan."
    )
