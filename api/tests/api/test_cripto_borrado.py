"""[T-2.150 · D-07] El teléfono del consentimiento: cifrado, y borrable sin abrir el guard.

`D-07` se negó a elegir entre los dos bienes que aquí chocaban —el derecho del
titular sobre su número, y la prueba de la base legal del envío que ese número
autorizó—. La salida: el número **no entra** en `privacy_consents`, y ejercer
ARCO borra una fila de **otra** tabla.

LAS TRES PROPIEDADES QUE LA DECISIÓN COMPRABA, Y QUE ESTE ARCHIVO MIDE
──────────────────────────────────────────────────────────────────────
1. **`privacy_consents` queda byte a byte intacta** — el guard append-only no se
   abre, y su digest sigue probando.
2. **Se conserva la prueba de QUE hubo consentimiento y CUÁNDO.**
3. **Desaparece la capacidad de leer A QUIÉN**, de forma irreversible.

`test_borrar_destruye_el_numero_SIN_TOCAR_el_consentimiento` mide las tres a la
vez, porque separadas no dicen nada: conservar la fila es fácil si no se borra
nada, y borrar es fácil si se rompe la fila.

LO QUE ESTE ARCHIVO **NO** AFIRMA
──────────────────────────────────
Que el índice sea anónimo. No lo es: el espacio de teléfonos es de ~10^10 y con
la pimienta en la mano se invierte por fuerza bruta. Lo que protege es el
escenario real —una copia de la base **sin** los secretos del despliegue—, y eso
sí se mide aquí (`test_la_base_sola_no_revela_el_numero`).

Si un número cifrado sigue siendo dato personal mientras exista la clave es la
pregunta que `D-07` mandó al abogado. Este módulo la implementa de forma que la
respuesta pueda cambiarse sin rehacerlo.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.privacy import crypto, store
from takab_api.settings import Settings

pytestmark = pytest.mark.anyio

MSISDN = "+525512345678"
OTRO = "+525599998888"


@pytest.fixture(autouse=True)
def _secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los dos secretos del despliegue. Fuera de la base, como en producción."""
    monkeypatch.setenv("TAKAB_API_PRIVACY_SUBJECT_PEPPER", "pimienta-de-prueba-no-produccion")
    monkeypatch.setenv("TAKAB_API_PRIVACY_SUBJECT_MASTER_KEY", "clave-maestra-de-prueba")


@pytest.fixture
async def limpio(base_data):
    """Las dos tablas del sujeto, en limpio.

    `privacy_consents` es append-only —el trigger veta el DELETE— así que se
    vacía con TRUNCATE, igual que hace el resto de la suite de privacidad.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM privacy_subject_secrets"))
        await conn.execute(text("TRUNCATE privacy_consents, privacy_notices CASCADE"))
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM privacy_subject_secrets"))
        await conn.execute(text("TRUNCATE privacy_consents, privacy_notices CASCADE"))


def _admin() -> dict[str, str]:
    return au.bearer(
        au.make_token(
            "tenant_admin",
            tenant=au.DB_TENANT_PRIV,
            site_scope="*",
            user_id="70000000-0000-0000-0000-0000000ad001",
        )
    )


def _ajustes() -> Settings:
    return Settings()


async def _consentir(msisdn: str = MSISDN) -> None:
    """Un opt-in de WhatsApp POR SU RUTA REAL.

    Se consiente por HTTP y no llamando al store: lo que hay que probar es el
    camino que de verdad escribe consentimientos en producción, incluida la
    resolución del aviso vigente.
    """
    async with au.client_for(create_app()) as client:
        aviso = (
            await client.get(
                "/privacy/notice", params={"purpose": "whatsapp_alerts"}, headers=_admin()
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
            headers=_admin(),
        )
        assert resp.status_code == 201, resp.text


async def _filas_de_consentimiento() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT consent_id, subject_kind, subject_ref, decision, notice_digest, "
                    "decided_at FROM privacy_consents WHERE tenant_id = :t "
                    "AND subject_kind = 'msisdn' ORDER BY decided_at"
                ),
                {"t": au.DB_TENANT_PRIV},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def _sellos() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(text("SELECT lookup_ref, sealed FROM privacy_subject_secrets"))
        ).mappings()
        return [dict(r) for r in rows]


# --- El número no entra en el consentimiento ---------------------------------


async def test_el_consentimiento_NO_guarda_el_numero(limpio) -> None:
    """El defecto original, cerrado: el `msisdn` ya no está en la tabla eterna."""
    await _consentir()

    filas = await _filas_de_consentimiento()
    assert len(filas) == 1, f"se esperaba un consentimiento, hay {len(filas)}"
    guardado = filas[0]["subject_ref"]

    assert MSISDN not in guardado, (
        f"el teléfono sigue en claro en `privacy_consents` ({guardado!r}): esa tabla "
        "es append-only y exenta de poda, así que ahí se queda PARA SIEMPRE"
    )
    assert len(guardado) == 64 and all(c in "0123456789abcdef" for c in guardado), (
        f"`subject_ref` no es el índice esperado: {guardado!r}"
    )


async def test_el_numero_sigue_siendo_recuperable_mientras_no_se_borre(limpio) -> None:
    """No-vacuidad: cifrar sin poder leer sería romper el envío, no protegerlo.

    El worker de notificaciones NECESITA el número para mandar el aviso. Si
    esto fallara, el sistema habría «protegido» el dato dejando a la gente sin
    su alerta de sismo.
    """
    await _consentir()
    lookup = crypto.lookup_ref(_ajustes(), tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)

    engine = get_engine()
    async with engine.begin() as conn:
        recuperado = await store.resolve_msisdn(
            conn, tenant_id=au.DB_TENANT_PRIV, lookup_ref=lookup
        )
    assert recuperado == MSISDN


# --- LA PROPIEDAD QUE JUSTIFICA LA DECISIÓN ----------------------------------


async def test_borrar_destruye_el_numero_SIN_TOCAR_el_consentimiento(limpio) -> None:
    """LAS TRES PROPIEDADES A LA VEZ, porque separadas no dicen nada.

    Conservar la fila es fácil si no se borra nada; borrar es fácil si se rompe
    la fila. Lo que `D-07` compró es exactamente la conjunción.
    """
    await _consentir()
    antes = await _filas_de_consentimiento()
    lookup = crypto.lookup_ref(_ajustes(), tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)

    engine = get_engine()
    async with engine.begin() as conn:
        borrado = await store.forget_msisdn(conn, tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)
    assert borrado is True

    # 1 · El consentimiento, byte a byte.
    despues = await _filas_de_consentimiento()
    assert despues == antes, (
        "la fila del consentimiento cambió al ejercer ARCO: eso es abrir el hueco "
        "en el guard append-only que D-07 existe para NO abrir"
    )

    # 2 · La prueba de QUE y CUÁNDO sobrevive.
    assert despues[0]["decision"] == "accept"
    assert despues[0]["decided_at"] is not None
    assert despues[0]["notice_digest"], "se perdió el digest del aviso aceptado"

    # 3 · El número ya no se puede leer.
    async with engine.begin() as conn:
        recuperado = await store.resolve_msisdn(
            conn, tenant_id=au.DB_TENANT_PRIV, lookup_ref=lookup
        )
    assert recuperado is None, (
        "el número sigue siendo recuperable tras ejercer ARCO: el borrado no fue tal"
    )
    assert await _sellos() == [], "quedó una copia del sello en alguna parte"


async def test_borrar_dos_veces_no_es_un_error(limpio) -> None:
    """Ejercer un derecho ya ejercido devuelve `False`, no una excepción.

    Un titular que insiste no puede recibir un error: no hay nada que arreglar,
    y un 500 le haría creer que su derecho no se atendió.
    """
    await _consentir()
    engine = get_engine()
    async with engine.begin() as conn:
        assert await store.forget_msisdn(conn, tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN) is True
    async with engine.begin() as conn:
        assert await store.forget_msisdn(conn, tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN) is False


async def test_borrar_a_uno_no_alcanza_al_otro(limpio) -> None:
    """No-vacuidad del borrado: es por sujeto, no una purga."""
    await _consentir(MSISDN)
    await _consentir(OTRO)
    assert len(await _sellos()) == 2

    engine = get_engine()
    async with engine.begin() as conn:
        await store.forget_msisdn(conn, tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)

    sellos = await _sellos()
    assert len(sellos) == 1, f"el borrado alcanzó a más de un sujeto: quedan {len(sellos)}"
    lookup_otro = crypto.lookup_ref(_ajustes(), tenant_id=au.DB_TENANT_PRIV, msisdn=OTRO)
    assert sellos[0]["lookup_ref"] == lookup_otro


# --- Lo que protege de verdad, y lo que no -----------------------------------


async def test_la_base_sola_no_revela_el_numero(limpio) -> None:
    """El escenario REAL: una copia de la base sin los secretos del despliegue.

    Es lo que este mecanismo protege. NO protege de quien ya tiene la pimienta
    —con ella, 10^10 candidatos se recorren en nada— y eso está escrito en el
    módulo en vez de insinuado.
    """
    await _consentir()

    engine = get_engine()
    async with engine.begin() as conn:
        volcado = (
            await conn.execute(
                text(
                    "SELECT subject_ref::text FROM privacy_consents "
                    "WHERE subject_kind = 'msisdn' AND tenant_id = :t "
                    "UNION ALL SELECT encode(sealed, 'hex') FROM privacy_subject_secrets"
                ),
                {"t": au.DB_TENANT_PRIV},
            )
        ).scalars()
        todo = " ".join(volcado)

    assert MSISDN not in todo, f"el número aparece en claro en un volcado de la base: {todo[:200]}"
    for trozo in (MSISDN[1:], MSISDN[-8:]):
        assert trozo not in todo, f"un trozo del número ({trozo}) aparece en claro"


def test_el_indice_es_DISTINTO_por_tenant() -> None:
    """Regla de oro 5 aplicada al índice.

    Sin el `tenant_id` dentro del HMAC, el mismo número daría el mismo índice en
    dos clientes — y cruzar las dos tablas revelaría que se trata de la misma
    persona, que es más de lo que ninguno de los dos consintió.
    """
    a = crypto.lookup_ref(
        _ajustes(), tenant_id="11111111-1111-1111-1111-111111111111", msisdn=MSISDN
    )
    b = crypto.lookup_ref(
        _ajustes(), tenant_id="22222222-2222-2222-2222-222222222222", msisdn=MSISDN
    )
    assert a != b, "el mismo número da el mismo índice en dos tenants: es un identificador global"


def test_el_sellado_no_es_determinista() -> None:
    """Nonce nuevo por sellado.

    Con AES-GCM, reutilizar un par (clave, nonce) no filtra «un poco»: rompe la
    confidencialidad y la autenticación de los dos mensajes. Un sello
    determinista además delataría que dos filas son el mismo número.
    """
    uno = crypto.seal(_ajustes(), msisdn=MSISDN)
    dos = crypto.seal(_ajustes(), msisdn=MSISDN)
    assert uno != dos, "dos sellados del mismo número dieron el mismo criptograma"
    assert crypto.unseal(_ajustes(), sealed=uno) == MSISDN
    assert crypto.unseal(_ajustes(), sealed=dos) == MSISDN


def test_un_sello_alterado_no_se_abre() -> None:
    """GCM autentica: un criptograma tocado revienta en vez de devolver basura."""
    sellado = bytearray(crypto.seal(_ajustes(), msisdn=MSISDN))
    sellado[-1] ^= 0x01
    with pytest.raises(Exception):  # noqa: B017 — InvalidTag es de `cryptography`
        crypto.unseal(_ajustes(), sealed=bytes(sellado))


# --- Fail-closed ---------------------------------------------------------------


def test_sin_secretos_NO_se_degrada_a_texto_en_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    """LA GUARDA QUE IMPIDE QUE ESTO SE DESHAGA SOLO.

    Un despliegue sin los secretos configurados no puede escribir teléfonos en
    claro «por compatibilidad»: los escribiría en una tabla que no se puede
    reescribir, en silencio y para siempre. Falla en cerrado, como los comandos
    sin clave HMAC resoluble.
    """
    monkeypatch.delenv("TAKAB_API_PRIVACY_SUBJECT_PEPPER", raising=False)
    monkeypatch.delenv("TAKAB_API_PRIVACY_SUBJECT_MASTER_KEY", raising=False)
    ajustes = Settings()

    assert crypto.disponible(ajustes) is False
    with pytest.raises(crypto.PrivacyCryptoUnavailable):
        crypto.lookup_ref(ajustes, tenant_id=au.DB_TENANT_PRIV, msisdn=MSISDN)
    with pytest.raises(crypto.PrivacyCryptoUnavailable):
        crypto.seal(ajustes, msisdn=MSISDN)


async def test_la_BASE_ya_no_acepta_un_consentimiento_con_el_numero_en_claro(limpio) -> None:
    """[T-2.164] El invariante deja de depender de que nadie se equivoque.

    `T-2.150` selló el sujeto, pero el `CHECK` siguió admitiendo **las dos
    formas** por las filas anteriores — y mientras las admitía, **la ausencia de
    filas viejas no se podía distinguir de que nadie las hubiera mirado**. Se
    contaron (cero en local, cero en `takab_test`, cero en la nube dev) y se
    apretó: escribir el número en claro ahora lo rechaza la BASE, no una
    convención del código.

    Se prueba por la puerta de atrás —`INSERT` directo— a propósito: por la
    puerta de delante `store.record_decision()` sella antes de insertar, así que
    nunca podría producir esta fila. Lo que se está anclando es que el defecto
    sea **inexpresable**, no que el camino feliz lo evite.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        with pytest.raises(Exception) as exc:
            await conn.execute(
                text(
                    "INSERT INTO privacy_consents "
                    "(tenant_id, purpose, subject_kind, subject_ref, decision, "
                    " notice_source, notice_digest, notice_version, notice_locale, via, actor_sub) "
                    "VALUES (CAST(:t AS uuid), 'whatsapp_alerts', 'msisdn', '+525512345678', "
                    "        'accept', 'repo', :d, 1, 'es-MX', 'out_of_band', :a)"
                ),
                {
                    "t": au.DB_TENANT_PRIV,
                    "d": "a" * 64,
                    "a": "d712fb34-446b-4545-a45c-c50f177a612d",
                },
            )
    assert "pc_sujeto_coherente" in str(exc.value), (
        f"lo rechazó, pero no el CHECK del sujeto: {exc.value}"
    )


async def test_la_forma_SELLADA_sigue_entrando(limpio) -> None:
    """La contraparte que hace no-vacuo al test de arriba: si el `CHECK` apretado
    rechazara también el índice, el rechazo del número en claro no probaría
    nada — estaría rechazando todo."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO privacy_consents "
                "(tenant_id, purpose, subject_kind, subject_ref, decision, "
                " notice_source, notice_digest, notice_version, notice_locale, via, actor_sub) "
                "VALUES (CAST(:t AS uuid), 'whatsapp_alerts', 'msisdn', :ref, "
                "        'accept', 'repo', :d, 1, 'es-MX', 'out_of_band', :a)"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "ref": "b" * 64,
                "d": "a" * 64,
                "a": "d712fb34-446b-4545-a45c-c50f177a612d",
            },
        )
