"""[T-2.151 · D-23] ARCO sobre un sujeto-teléfono, que no tiene `sub` ninguno.

`store.forget_msisdn()` existía desde `T-2.150` y estaba probada, pero el flujo
ARCO entero está tecleado por `user_sub` y un titular que solo dio su número **no
tiene ninguno**: no hay fila en `user_profiles`, así que tampoco el FK compuesto
que impide nombrar a un titular de otro cliente. Faltaba decidir **cómo se
acredita** a quien pide el borrado, que es una pregunta de identidad y no de
código. La respondió [`D-23`](takab-docs/DECISIONES-MAURICIO.md): **la acredita el
cliente institucional** que recogió el consentimiento. TAKAB ejecuta y audita; no
verifica identidades por su cuenta ni custodia documentos.

LAS DOS PROPIEDADES QUE ESTE ARCHIVO MIDE, Y QUE SE PERSIGUEN A LA VEZ
──────────────────────────────────────────────────────────────────────
1. **No es un oráculo de existencia.** La respuesta es la misma exista el número
   o no. Un «no encontrado» frente a un «borrado» convertiría el endpoint en un
   buscador de personas: permitiría comprobar si un teléfono consta y, con él, en
   qué edificio está quien lo lleva.
2. **Nadie borra el consentimiento de otro.** Sin acreditación no se ejecuta —
   destruir la prueba de la base legal de un tercero es justo lo que `D-07`
   construyó el cripto-borrado para impedir.

Van juntas porque por separado son triviales y en direcciones opuestas: callar
siempre cumple la primera y borrar siempre cumple la segunda.

POR QUÉ UN SOLO ENDPOINT, CUANDO EL ARCO POR ESCRITO SON DOS
─────────────────────────────────────────────────────────────
`T-2.80.b` separó *registrar* de *ejecutar* a propósito: son dos actos con dos
fechas, y de la primera corre el plazo legal. Aquí van fundidos, y la razón es
material: **para ejecutar hay que tener el número delante**. La constancia
tendría que guardar su índice —el mismo HMAC con pimienta que indexa el sello— y
`privacy_erasure_requests` es **append-only por trigger**, así que ese índice no
podría borrarse jamás: sobreviviría al borrado que lo motivó. Fundidos, el número
entra por el cuerpo, se usa y no se persiste en ninguna parte.

Las dos fechas **no se pierden**: `received_at` viene del escrito (lo pone el
cliente, no `now()`) y `erased_at` lo pone la base. Lo que se pierde es la
posibilidad de registrar hoy y ejecutar la semana que viene — y a cambio no queda
un rastro permanente del número en la tabla eterna.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.privacy import crypto, store
from takab_api.settings import Settings

pytestmark = pytest.mark.anyio

#: El que SÍ consintió: se sella al consentir y este archivo lo borra.
MSISDN = "+525512345678"
#: Uno que no consta en ninguna parte. Mismo formato, para que la única
#: diferencia entre las dos peticiones sea la existencia.
FANTASMA = "+525577770000"

RUTA = "/privacy/phone-erasures"

#: Lo único que puede diferir entre dos respuestas: identificadores del acto y su
#: instante. Cualquier campo NUEVO que aparezca fuera de esta lista y que además
#: cambie según si el número existía es, por definición, la fuga que la ficha
#: prohíbe — y el test lo dirá por su nombre.
CAMPOS_IRREPETIBLES = {"erasure_id", "request_id", "erased_at", "audit_watermark", "audit_digest"}


@pytest.fixture(autouse=True)
def _secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los dos secretos del despliegue, fuera de la base como en producción."""
    monkeypatch.setenv("TAKAB_API_PRIVACY_SUBJECT_PEPPER", "pimienta-de-prueba-no-produccion")
    monkeypatch.setenv("TAKAB_API_PRIVACY_SUBJECT_MASTER_KEY", "clave-maestra-de-prueba")


@pytest.fixture
async def limpio(base_data):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM privacy_subject_secrets"))
        await conn.execute(
            text("TRUNCATE privacy_consents, privacy_notices, privacy_erasures CASCADE")
        )
        await conn.execute(text("TRUNCATE privacy_erasure_requests CASCADE"))
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM privacy_subject_secrets"))
        await conn.execute(
            text("TRUNCATE privacy_consents, privacy_notices, privacy_erasures CASCADE")
        )
        await conn.execute(text("TRUNCATE privacy_erasure_requests CASCADE"))


def _admin(tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(
        au.make_token(
            "tenant_admin",
            tenant=tenant,
            site_scope="*",
            user_id="70000000-0000-0000-0000-0000000ad001",
        )
    )


def _operador() -> dict[str, str]:
    """Un rol que NO es responsable del tratamiento."""
    return au.bearer(
        au.make_token(
            "operator",
            tenant=au.DB_TENANT_PRIV,
            site_scope="*",
            user_id="70000000-0000-0000-0000-0000000op01",
        )
    )


def _solicitud(msisdn: str) -> dict[str, Any]:
    """El cuerpo completo: el número MÁS la acreditación del cliente."""
    return {
        "msisdn": msisdn,
        "right": "cancelacion",
        "channel": "written",
        "received_at": "2026-08-20T10:00:00Z",
        "proof_ref": "oficio 2026/114 de la Dirección de Protección Civil",
        "proof_digest": "a" * 64,
    }


async def _consentir(msisdn: str = MSISDN, tenant: str = au.DB_TENANT_PRIV) -> None:
    """Un opt-in por su ruta real, que es lo que sella el número."""
    async with au.client_for(create_app()) as client:
        aviso = (
            await client.get(
                "/privacy/notice", params={"purpose": "whatsapp_alerts"}, headers=_admin(tenant)
            )
        ).json()
        resp = await client.post(
            "/privacy/consents/third-party",
            json={
                "purpose": "whatsapp_alerts",
                "digest": aviso["digest"],
                "msisdn": msisdn,
                "via": "out_of_band",
                "decision": "accept",
            },
            headers=_admin(tenant),
        )
        assert resp.status_code == 201, resp.text


async def _sigue_sellado(msisdn: str, tenant: str = au.DB_TENANT_PRIV) -> bool:
    lookup = crypto.lookup_ref(Settings(), tenant_id=tenant, msisdn=msisdn)
    engine = get_engine()
    async with engine.begin() as conn:
        return (await store.resolve_msisdn(conn, tenant_id=tenant, lookup_ref=lookup)) is not None


async def _borrar(msisdn: str, headers: dict[str, str] | None = None):
    async with au.client_for(create_app()) as client:
        return await client.post(
            RUTA, json=_solicitud(msisdn), headers=headers if headers is not None else _admin()
        )


# ---------------------------------------------------------------------------
# 1 · La respuesta no puede ser un oráculo de existencia
# ---------------------------------------------------------------------------


async def test_la_respuesta_es_la_misma_exista_o_no_el_numero(limpio) -> None:
    """**El criterio 2, comparado campo a campo.**

    Se borra un número que SÍ consta y otro que no ha existido nunca, con el
    mismo cuerpo salvo el teléfono. Si algo en la respuesta —el código, una
    clave, un conteo— permitiera distinguir los dos casos, cualquiera con una
    credencial de responsable podría barrer un rango de números y saber cuáles
    constan en el edificio.
    """
    await _consentir()

    existe = await _borrar(MSISDN)
    no_existe = await _borrar(FANTASMA)

    assert existe.status_code == no_existe.status_code, (
        f"el código de estado delata la existencia: {existe.status_code} frente a "
        f"{no_existe.status_code}"
    )
    a, b = existe.json(), no_existe.json()
    assert set(a) == set(b), f"las claves difieren: {sorted(set(a) ^ set(b))}"

    delatan = {k: (a[k], b[k]) for k in a if k not in CAMPOS_IRREPETIBLES and a[k] != b[k]}
    assert not delatan, (
        f"campo(s) que revelan si el número constaba: {delatan}. La respuesta a quien no "
        "acredita —y a quien acredita sobre un número que no existe— tiene que ser la misma "
        "SIEMPRE, o el endpoint es un buscador de personas."
    )
    # No-vacuidad: si `affected` desapareciera del modelo, lo de arriba pasaría
    # por no tener nada que comparar. Es el campo donde un conteo delataría.
    assert a["affected"] == {}, (
        f"`affected` trae conteos ({a['affected']!r}): un 1 frente a un 0 es exactamente el "
        "oráculo que la ficha prohíbe"
    )


async def test_borrar_dos_veces_tampoco_delata_que_ya_estaba_borrado(limpio) -> None:
    """La segunda vuelta es el mismo oráculo por otra puerta.

    Si repetir el borrado respondiera «ya estaba» y la primera «hecho», bastaría
    con pedirlo dos veces para saber si el número constaba.
    """
    await _consentir()
    primera = await _borrar(MSISDN)
    segunda = await _borrar(MSISDN)

    assert primera.status_code == segunda.status_code
    a, b = primera.json(), segunda.json()
    delatan = {k: (a[k], b[k]) for k in a if k not in CAMPOS_IRREPETIBLES and a[k] != b[k]}
    assert not delatan, f"la repetición delata el estado anterior: {delatan}"


# ---------------------------------------------------------------------------
# 2 · Sin acreditación no se ejecuta
# ---------------------------------------------------------------------------


async def test_sin_rol_de_responsable_no_se_borra_un_solo_numero(limpio) -> None:
    """`D-23` puso la acreditación en el cliente institucional; en el sistema eso
    es el responsable del tratamiento y nadie más. Y no basta con que la respuesta
    sea 403: **el número tiene que seguir ahí**."""
    await _consentir()
    resp = await _borrar(MSISDN, headers=_operador())
    assert resp.status_code == 403, resp.text
    assert await _sigue_sellado(MSISDN), (
        "el borrado se ejecutó pese al 403: la respuesta decía que no y la base decía que sí"
    )


async def test_sin_prueba_del_escrito_no_se_ejecuta(limpio) -> None:
    """El escrito es la acreditación. Un cuerpo sin `proof_digest` es alguien
    ejerciendo el ARCO de un tercero de palabra, que es justo lo que `D-07`
    construyó el cripto-borrado para impedir."""
    await _consentir()
    cuerpo = _solicitud(MSISDN)
    del cuerpo["proof_digest"]
    async with au.client_for(create_app()) as client:
        resp = await client.post(RUTA, json=cuerpo, headers=_admin())
    assert resp.status_code == 422, resp.text
    assert await _sigue_sellado(MSISDN), "se borró sin prueba del escrito"


async def test_el_numero_de_otro_cliente_no_se_puede_nombrar(limpio) -> None:
    """Regla de oro 5, y aquí sale gratis: el índice se deriva con el `tenant_id`
    de la SESIÓN, así que el mismo teléfono produce índices distintos en dos
    clientes. Nombrar al titular de otro no se rechaza por una comprobación —es
    que no se puede formular—."""
    await _consentir(MSISDN, tenant=au.DB_TENANT_PRIV)
    await _consentir(MSISDN, tenant=au.DB_TENANT_GOV)

    resp = await _borrar(MSISDN, headers=_admin(au.DB_TENANT_PRIV))
    assert resp.status_code == 201, resp.text

    assert not await _sigue_sellado(MSISDN, tenant=au.DB_TENANT_PRIV), "no borró el suyo"
    assert await _sigue_sellado(MSISDN, tenant=au.DB_TENANT_GOV), (
        "borró el número del OTRO cliente: el mismo teléfono en dos tenants tiene que ser "
        "dos sujetos distintos e inalcanzables entre sí"
    )


# ---------------------------------------------------------------------------
# 3 · La lápida cubre al sujeto-teléfono, y no guarda una copia del número
# ---------------------------------------------------------------------------


async def test_la_lapida_registra_el_acto_del_sujeto_telefono(limpio) -> None:
    """El criterio 4: que el borrado deje el mismo testigo sellado que el de un
    `sub`. Sin lápida, ejercer ARCO por teléfono no sería auditable y la
    diferencia entre «se ejecutó» y «se dijo que se ejecutó» desaparecería."""
    await _consentir()
    resp = await _borrar(MSISDN)
    assert resp.status_code == 201, resp.text

    engine = get_engine()
    async with engine.begin() as conn:
        filas = (
            (
                await conn.execute(
                    text(
                        "SELECT subject_kind, user_sub, right_exercised, via, request_id, "
                        "       audit_watermark, audit_digest "
                        "FROM privacy_erasures WHERE tenant_id = :t"
                    ),
                    {"t": au.DB_TENANT_PRIV},
                )
            )
            .mappings()
            .all()
        )
    assert len(filas) == 1, f"se esperaba una lápida, hay {len(filas)}"
    lapida = dict(filas[0])
    assert lapida["subject_kind"] == "msisdn"
    assert lapida["user_sub"] is None, (
        "la lápida de un sujeto-teléfono trae un `user_sub`: ese titular no tiene ninguno y "
        "rellenarlo con algo inventado haría que la fila mintiera sobre a quién nombra"
    )
    assert lapida["request_id"] is not None, "la lápida no apunta a la constancia que la autoriza"
    assert lapida["audit_digest"] and lapida["audit_watermark"] is not None, (
        "sin el par marca-de-agua/digest la bitácora deja de ser verificable, que es lo que "
        "hace la lápida algo más que una afirmación"
    )


async def test_ni_el_numero_ni_su_indice_quedan_en_la_lapida(limpio) -> None:
    """**El criterio 5, buscado en la fila ENTERA y no en las columnas que uno
    recuerda.** Guardar el número «para trazabilidad» convertiría el borrado en
    una seudonimización reversible; guardar su índice sería lo mismo con un paso
    más, porque es determinista y se recomputa con la pimienta en la mano.

    Se busca también en la constancia, que es append-only: lo que caiga ahí no se
    puede quitar nunca.
    """
    await _consentir()
    lookup = crypto.lookup_ref(Settings(), tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)
    assert await _borrar(MSISDN)

    engine = get_engine()
    async with engine.begin() as conn:
        for tabla in ("privacy_erasures", "privacy_erasure_requests"):
            filas = (
                (
                    await conn.execute(
                        text(f"SELECT to_jsonb(t)::text FROM {tabla} t WHERE tenant_id = :x"),
                        {"x": au.DB_TENANT_PRIV},
                    )
                )
                .scalars()
                .all()
            )
            # Sin esto el bucle no mira nada cuando la consulta viene vacía, y un
            # test que no mira nada aprueba cualquier fuga. Pasó: dos sabotajes
            # —el número en claro y su índice— se colaron en verde por aquí.
            assert filas, f"`{tabla}` no devolvió ni una fila: no se comprobó ninguna fuga"
            for cruda in filas:
                assert MSISDN not in cruda, (
                    f"el teléfono en claro está en `{tabla}`: {cruda}. Esa tabla es append-only, "
                    "así que ahí se queda PARA SIEMPRE."
                )
                assert lookup not in cruda, (
                    f"el ÍNDICE del teléfono está en `{tabla}`: {cruda}. Es determinista — con "
                    "la pimienta se comprueba cualquier número candidato—, así que sobrevivir "
                    "al borrado lo convierte en una seudonimización que no se puede deshacer."
                )


async def test_el_consentimiento_queda_byte_a_byte_intacto(limpio) -> None:
    """La propiedad de `D-07` que esta ruta no puede romper: desaparece la
    capacidad de leer a quién, y se conserva la prueba de QUE hubo consentimiento
    y CUÁNDO."""
    engine = get_engine()

    async def _consentimientos() -> list[dict]:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "SELECT consent_id, subject_kind, subject_ref, decision, notice_digest, "
                        "decided_at FROM privacy_consents WHERE tenant_id = :t ORDER BY decided_at"
                    ),
                    {"t": au.DB_TENANT_PRIV},
                )
            ).mappings()
            return [dict(f) for f in filas]

    await _consentir()
    antes = await _consentimientos()
    assert antes, "no se sembró ningún consentimiento: el test pasaría por vacuidad"

    assert (await _borrar(MSISDN)).status_code == 201
    assert await _consentimientos() == antes, (
        "la fila del consentimiento cambió al ejercer ARCO: eso es abrir el hueco en el guard "
        "append-only que D-07 existe para NO abrir"
    )
    assert not await _sigue_sellado(MSISDN), "el número sobrevivió al borrado"


async def test_la_constancia_conserva_la_prueba_del_escrito(limpio) -> None:
    """El acto queda acreditado: de qué canal llegó, cuándo lo recibió el cliente
    y con qué documento. `received_at` sale del escrito y no de `now()` — es de
    esa fecha de la que corre el plazo legal, no de la de ejecución."""
    await _consentir()
    assert (await _borrar(MSISDN)).status_code == 201

    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT subject_kind, user_sub, channel, received_at, proof_ref, "
                        "       proof_digest, created_by "
                        "FROM privacy_erasure_requests WHERE tenant_id = :t"
                    ),
                    {"t": au.DB_TENANT_PRIV},
                )
            )
            .mappings()
            .one()
        )
    assert fila["subject_kind"] == "msisdn"
    assert fila["user_sub"] is None
    assert fila["channel"] == "written"
    assert fila["proof_digest"] == "a" * 64
    assert fila["received_at"].isoformat().startswith("2026-08-20T10:00"), (
        f"`received_at` no es la del escrito sino {fila['received_at']}: si fuera `now()`, el "
        "plazo legal correría desde que TAKAB ejecuta y no desde que el cliente recibió"
    )
