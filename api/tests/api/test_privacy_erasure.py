"""T-2.80 · ``/privacy/erasure`` de punta a punta.

Lo que se mide aquí y no en `tests/test_privacy_erasure.py` (que prueba la capa
de datos): que el derecho se ejerce **por HTTP con el token del titular**, que la
respuesta no lleva PII, y las dos decisiones de producto que solo se ven desde
fuera —el diferimiento por incidente abierto y el 200 idempotente—.

LA TRAMPA DE ESTE ARCHIVO
─────────────────────────
El `sub` va FIJO en cada token (``make_token`` genera uno aleatorio si no se le
da): con un sub distinto por petición, el titular que ejerce ARCO y el que lo
consulta serían personas distintas y la mitad de los tests pasarían por el motivo
equivocado. Es la misma trampa que documenta ``test_privacy.py``.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app

# Titulares fijos (ver la nota de arriba).
OCC = "7f000000-0000-0000-0000-00000000cc01"
OCC_LIMPIO = "7f000000-0000-0000-0000-00000000cc02"
OCC_B = "7f000000-0000-0000-0000-00000000cc03"

NOMBRE = "Ernestina Zapopan Quinones"
TELEFONO = "+525599887799"
PUNTO = "ST_SetSRID(ST_MakePoint(-99.1332,19.4326),4326)::geography"


def _ocupante(user: str = OCC, tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token("occupant", tenant=tenant, site_scope="*", user_id=user))


@pytest.fixture
async def limpia_arco(base_data):
    """`privacy_erasures` es append-only: DELETE lo veta el trigger, TRUNCATE no.

    [T-2.80.b] Y con ella la CONSTANCIA, que también lo es. Se nombran las dos
    aunque `CASCADE` no arrastre hacia el padre: una constancia superviviente haría
    que `app_can_erase_subject` fuera cierto en el test siguiente, y un test que
    exige "sin constancia no se ejerce" pasaría por el motivo equivocado.
    """
    yield
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE privacy_erasures, privacy_erasure_requests CASCADE"))


async def _siembra(
    user: str = OCC,
    tenant: str = au.DB_TENANT_PRIV,
    site: str = au.DB_SITE_PRIV,
    *,
    incident_id: str | None = None,
    nombre: str = NOMBRE,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) "
                "VALUES (CAST(:u AS uuid), :t, :n, :p) ON CONFLICT (user_sub) DO NOTHING"
            ),
            {"u": user, "t": tenant, "n": nombre, "p": TELEFONO},
        )
        await conn.execute(
            text(
                "INSERT INTO life_checkins "
                "(tenant_id, incident_id, user_id, site_id, status, geom) "
                f"VALUES (:t, CAST(:i AS uuid), CAST(:u AS uuid), :s, 'safe', {PUNTO})"
            ),
            {"t": tenant, "i": incident_id, "u": user, "s": site},
        )


@pytest.mark.anyio
async def test_el_titular_ejerce_arco_y_la_respuesta_no_lleva_pii(limpia_arco) -> None:
    """201 con los conteos de lo anonimizado, y ni rastro del dato anonimizado."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure",
            json={"right": "cancelacion", "via": "mobile", "confirm": True},
            headers=_ocupante(),
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["user_sub"] == OCC
    assert body["affected"]["life_checkins"] == 1
    assert body["affected"]["user_profiles"] == 1
    assert len(body["audit_digest"]) == 64
    # El cuerpo entero, no solo los campos que se me ocurra mirar.
    assert NOMBRE not in resp.text
    assert TELEFONO not in resp.text


@pytest.mark.anyio
async def test_ejercerlo_dos_veces_devuelve_200_y_la_misma_lapida(limpia_arco) -> None:
    """Idempotencia por HTTP. Un 409 aquí haría creer que el borrado no ocurrió."""
    await _siembra()
    cuerpo = {"right": "cancelacion", "via": "mobile", "confirm": True}
    async with au.client_for(create_app()) as client:
        primera = await client.post("/privacy/erasure", json=cuerpo, headers=_ocupante())
        segunda = await client.post("/privacy/erasure", json=cuerpo, headers=_ocupante())
    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["created"] is False
    assert segunda.json()["erasure_id"] == primera.json()["erasure_id"]
    assert segunda.json()["audit_digest"] == primera.json()["audit_digest"]


@pytest.mark.anyio
async def test_un_incidente_abierto_difiere_el_borrado(limpia_arco, make_incident) -> None:
    """DECISIÓN de producto, visible solo desde fuera.

    La ubicación de un check-in es dato de rescate EN VIVO. El derecho no se
    niega: se aplaza, y el mensaje lo dice para que la app no lo pinte como un
    error del usuario.
    """
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
    await _siembra(incident_id=inc)
    async with au.client_for(create_app()) as client:
        resp = await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
    assert resp.status_code == 409, resp.text
    assert "difiere" in resp.json()["detail"]

    # Y no dejó la anonimización a medias.
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            await conn.execute(
                text("SELECT display_name FROM user_profiles WHERE user_sub = CAST(:u AS uuid)"),
                {"u": OCC},
            )
        ).first()
    assert fila[0] == NOMBRE


@pytest.mark.anyio
async def test_la_peticion_diferida_queda_auditada(limpia_arco, make_incident) -> None:
    """El 409 hace rollback: sin auditoría FUERA DE BANDA no quedaría constancia.

    Importa porque el plazo legal de respuesta corre desde que el titular pide,
    no desde que el sistema puede. Sin esta fila, una solicitud diferida sería
    indistinguible de una que nunca se hizo.
    """
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
    await _siembra(incident_id=inc)
    async with au.client_for(create_app()) as client:
        await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())

    engine = get_engine()
    async with engine.begin() as conn:
        n = await conn.scalar(
            text("SELECT count(*) FROM audit_log WHERE verb = 'privacy_erasure_deferred'")
        )
    assert n == 1


@pytest.mark.anyio
async def test_sin_confirmacion_explicita_no_se_borra_nada(limpia_arco) -> None:
    """La anonimización es IRREVERSIBLE: un POST accidental no puede deshacerse."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        sin = await client.post("/privacy/erasure", json={}, headers=_ocupante())
        falso = await client.post("/privacy/erasure", json={"confirm": False}, headers=_ocupante())
    assert sin.status_code == 422
    assert falso.status_code == 422


@pytest.mark.anyio
async def test_el_cuerpo_no_admite_un_sujeto(limpia_arco) -> None:
    """`extra="forbid"`: intentar ejercer ARCO por otro es un 422, no un borrado ajeno.

    La defensa real está en la base (la función no tiene parámetro de sujeto);
    esto solo hace que el intento falle ruidosamente en la frontera.
    """
    await _siembra()
    await _siembra(user=OCC_LIMPIO, nombre="Otra Persona")
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure",
            json={"confirm": True, "user_sub": OCC_LIMPIO},
            headers=_ocupante(),
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_la_prueba_de_integridad_se_recalcula_en_vivo(limpia_arco) -> None:
    """CRITERIO 3 por HTTP: el servidor recalcula el sello y declara si cuadra."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        antes = await client.get("/privacy/erasure", headers=_ocupante())
        assert antes.status_code == 404

        creada = await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
        prueba = await client.get("/privacy/erasure", headers=_ocupante())

    assert prueba.status_code == 200
    body = prueba.json()
    assert body["audit_intact"] is True
    assert body["audit_digest_now"] == creada.json()["audit_digest"]
    assert body["erasure"]["erasure_id"] == creada.json()["erasure_id"]


@pytest.mark.anyio
async def test_la_lapida_de_otro_tenant_no_se_ve(limpia_arco) -> None:
    """Regla de oro 5, en la superficie HTTP."""
    await _siembra(user=OCC, tenant=au.DB_TENANT_PRIV, site=au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
        ajeno = await client.get(
            "/privacy/erasure", headers=_ocupante(user=OCC, tenant=au.DB_TENANT_PRIV2)
        )
    assert ajeno.status_code == 404


# ---------------------------------------------------------------------------
# T-2.80.b · El responsable ejecuta un ARCO recibido POR ESCRITO
# ---------------------------------------------------------------------------

ADMIN = "7f000000-0000-0000-0000-00000000ad01"
ADMIN_B = "7f000000-0000-0000-0000-00000000ad02"
DIGEST = "9" * 64


def _responsable(user: str = ADMIN, tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token("tenant_admin", tenant=tenant, site_scope="*", user_id=user))


def _constancia(user: str = OCC, **over) -> dict:
    cuerpo = {
        "user_sub": user,
        "right": "cancelacion",
        "channel": "written",
        "received_at": "2026-08-09T18:30:00+00:00",
        "proof_ref": "expediente ARCO-2026-014",
        "proof_digest": DIGEST,
    }
    cuerpo.update(over)
    return cuerpo


@pytest.mark.anyio
async def test_el_responsable_registra_la_constancia_y_ejerce_por_el_titular(
    limpia_arco,
) -> None:
    """El caso real de la ficha, de punta a punta y en dos actos."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        alta = await client.post(
            "/privacy/erasure-requests", json=_constancia(), headers=_responsable()
        )
        assert alta.status_code == 201, alta.text
        request_id = alta.json()["request_id"]
        assert alta.json()["created_by"] == ADMIN
        # La respuesta no filtra PII del titular más allá de su `sub` opaco.
        assert NOMBRE not in alta.text
        assert TELEFONO not in alta.text

        hecho = await client.post(
            f"/privacy/erasure-requests/{request_id}/erasure",
            json={"confirm": True},
            headers=_responsable(),
        )

    assert hecho.status_code == 201, hecho.text
    body = hecho.json()
    assert body["created"] is True
    assert body["user_sub"] == OCC, "el sujeto sale de la constancia, no del cuerpo"
    assert body["requested_by"] == ADMIN, "quién lo ejecutó"
    assert body["request_id"] == request_id, "con qué prueba"
    assert body["via"] == "console_admin"
    assert body["affected"]["user_profiles"] == 1
    assert NOMBRE not in hecho.text
    assert TELEFONO not in hecho.text


@pytest.mark.anyio
async def test_sin_constancia_no_se_ejerce_por_cuenta_de_otro(limpia_arco) -> None:
    """CRITERIO 2 en la superficie HTTP: no hay atajo que salte el registro."""
    await _siembra()
    inventado = "7f000000-0000-0000-0000-0000000000ff"
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            f"/privacy/erasure-requests/{inventado}/erasure",
            json={"confirm": True},
            headers=_responsable(),
        )
    assert resp.status_code == 404, resp.text
    assert "constancia" in resp.json()["detail"]

    engine = get_engine()
    async with engine.begin() as conn:
        nombre = await conn.scalar(
            text("SELECT display_name FROM user_profiles WHERE user_sub = CAST(:u AS uuid)"),
            {"u": OCC},
        )
    assert nombre == NOMBRE


@pytest.mark.anyio
async def test_la_constancia_no_puede_nombrar_a_un_titular_de_otro_cliente(
    limpia_arco,
) -> None:
    """CRITERIO 3 en la superficie HTTP, y con la respuesta correcta.

    404 y no 403: para el responsable de un cliente, un titular ajeno **no
    existe**. Un 403 le diría "existe pero no puedes", que es filtrar la
    pertenencia de una persona a otro tenant (regla de oro 5).
    """
    await _siembra(user=OCC_B, tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure-requests",
            json=_constancia(user=OCC_B),
            headers=_responsable(),
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.anyio
async def test_un_ocupante_no_registra_constancias_ni_ejerce_por_otro(limpia_arco) -> None:
    """La acción de matriz, medida donde se nota: el 403 llega limpio."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        alta = await client.post(
            "/privacy/erasure-requests", json=_constancia(), headers=_ocupante()
        )
        ejecuta = await client.post(
            f"/privacy/erasure-requests/{'7f000000-0000-0000-0000-0000000000ff'}/erasure",
            json={"confirm": True},
            headers=_ocupante(),
        )
    assert alta.status_code == 403
    assert ejecuta.status_code == 403


@pytest.mark.anyio
async def test_el_audit_log_dice_quien_pidio_quien_ejecuto_y_con_que_prueba(
    limpia_arco,
) -> None:
    """CRITERIO 2, literal. Las tres piezas, en la fila que no se poda jamás.

    Y una cuarta cosa por omisión: `proof_ref` NO está. Es texto libre que un
    operador puede llenar con un correo o un nombre, y el `audit_log` es eterno.
    El `proof_digest` identifica el documento sin copiarlo.
    """
    await _siembra()
    async with au.client_for(create_app()) as client:
        alta = await client.post(
            "/privacy/erasure-requests", json=_constancia(), headers=_responsable()
        )
        request_id = alta.json()["request_id"]
        await client.post(
            f"/privacy/erasure-requests/{request_id}/erasure",
            json={"confirm": True},
            headers=_responsable(),
        )

    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            await conn.execute(
                text(
                    "SELECT actor, meta FROM audit_log "
                    "WHERE verb = 'privacy_erasure_on_behalf' ORDER BY audit_id DESC LIMIT 1"
                )
            )
        ).first()
        alta_fila = (
            await conn.execute(
                text(
                    "SELECT actor, meta FROM audit_log "
                    "WHERE verb = 'privacy_erasure_request' ORDER BY audit_id DESC LIMIT 1"
                )
            )
        ).first()

    assert fila is not None, "el acto por cuenta de otro no dejó fila en la bitácora"
    actor, meta = fila
    assert actor == f"user:{ADMIN}"  # quién lo EJECUTÓ
    assert meta["requested_by_subject"] == OCC  # quién lo PIDIÓ
    assert meta["executed_by"] == ADMIN
    assert meta["request_id"] == request_id  # con qué PRUEBA
    assert meta["proof_digest"] == DIGEST
    assert meta["request_channel"] == "written"
    assert "proof_ref" not in meta
    assert NOMBRE not in str(meta) and TELEFONO not in str(meta)

    # Y el acto de RECIBIR la solicitud tiene su propia fila y su propia fecha:
    # de ahí corre el plazo legal, no de cuándo el responsable llegó a ejecutarla.
    assert alta_fila is not None
    assert alta_fila[1]["subject_sub"] == OCC
    assert alta_fila[1]["received_at"].startswith("2026-08-09")


@pytest.mark.anyio
async def test_el_cuerpo_de_ejecucion_no_admite_un_sujeto(limpia_arco) -> None:
    """`extra="forbid"`: tampoco por esta puerta se nombra a una persona.

    La defensa real está en la base (la función resuelve el sujeto contra el
    padrón del tenant de la sesión); esto solo hace que el intento falle
    ruidosamente en la frontera.
    """
    await _siembra()
    await _siembra(user=OCC_LIMPIO, nombre="Otra Persona")
    async with au.client_for(create_app()) as client:
        alta = await client.post(
            "/privacy/erasure-requests", json=_constancia(), headers=_responsable()
        )
        request_id = alta.json()["request_id"]
        resp = await client.post(
            f"/privacy/erasure-requests/{request_id}/erasure",
            json={"confirm": True, "user_sub": OCC_LIMPIO},
            headers=_responsable(),
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_el_responsable_no_puede_fabricarse_su_propia_constancia(limpia_arco) -> None:
    """Una constancia es la solicitud de OTRO.

    Si el responsable pudiera registrarse una a su nombre, el registro que prueba
    "alguien me lo pidió" se firmaría solo. Para su propio ARCO tiene el
    autoservicio, igual que cualquier titular.
    """
    await _siembra(user=ADMIN, nombre="Responsable Del Tratamiento")
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure-requests", json=_constancia(user=ADMIN), headers=_responsable()
        )
    assert resp.status_code == 400, resp.text


@pytest.mark.anyio
async def test_ejercer_por_constancia_lo_que_el_titular_ya_ejercio_es_idempotente(
    limpia_arco,
) -> None:
    """200 y la MISMA lápida: el testigo sellado del primer acto no se reescribe.

    Es el caso real de una solicitud por escrito que llega tarde, después de que
    la persona ya lo hiciera desde la app. Un 409 aquí haría creer al responsable
    que no se ejecutó y le empujaría a "arreglarlo" a mano.
    """
    await _siembra()
    async with au.client_for(create_app()) as client:
        primera = await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
        alta = await client.post(
            "/privacy/erasure-requests", json=_constancia(), headers=_responsable()
        )
        segunda = await client.post(
            f"/privacy/erasure-requests/{alta.json()['request_id']}/erasure",
            json={"confirm": True},
            headers=_responsable(),
        )
    assert primera.status_code == 201
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["created"] is False
    assert segunda.json()["erasure_id"] == primera.json()["erasure_id"]
    # La lápida sigue diciendo que la ejerció el TITULAR: la constancia llegó
    # después y no reescribe la historia.
    assert segunda.json()["requested_by"] == OCC
    assert segunda.json()["request_id"] is None
