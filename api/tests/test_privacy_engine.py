"""T-2.79 · El motor de consentimiento, probado donde se decide: en la DB.

La ficha pide tres cosas y la tercera es la que tiene trampa:

1. el aviso es un objeto VERSIONADO;
2. el consentimiento guarda QUÉ versión aceptó cada quien y CUÁNDO;
3. **cambiar el aviso no reescribe consentimientos anteriores**.

Un diseño de `privacy_notices(version, body)` + FK desde `privacy_consents`
cumple 1 y 2 y **falla el 3 en silencio**: si alguien corrige una errata de la
v1.0.0, todos los consentimientos que apuntaban a esa fila pasan a apuntar a un
texto distinto del que se aceptó. La FK sigue íntegra, la etiqueta de versión
sigue diciendo "1.0.0" y el registro miente. Por eso el consentimiento se ata al
CONTENIDO —un digest SHA-256— y no al número de versión.

Los dos tests que sostienen la tarea son
``test_texto_corregido_deja_obsoleto_el_consentimiento_de_ayer`` (la vía normal:
el aviso es append-only, corregir = publicar otra fila) y
``test_edicion_por_detras_del_trigger_sigue_siendo_detectable`` (la vía sucia: un
DBA, una réplica o una migración mal escrita muta la fila igualmente). El segundo
comprueba explícitamente que un diseño por FK+versión habría pasado en verde.
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import TENANT_A, TENANT_B, reset, use
from takab_api.privacy.artifacts import notice_digest

USER_A = "aaaa0000-0000-0000-0000-0000000000a1"
USER_B = "bbbb0000-0000-0000-0000-0000000000b1"

_CUERPO = (
    "Aviso de privacidad provisional. TAKAB Ailert trata su nombre, su zona "
    "asignada y sus check-ins de vida como datos de proteccion civil del inmueble."
)


def _publica(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    purpose: str = "privacy_notice",
    locale: str = "es-MX",
    version: str = "1.0.0",
    title: str = "Aviso de privacidad",
    body: str = _CUERPO,
    by: str = USER_A,
) -> tuple[str, str]:
    """Publica un aviso de tenant y devuelve ``(notice_id, digest)``."""
    row = conn.execute(
        "INSERT INTO privacy_notices "
        "(tenant_id, purpose, locale, version, title, body, published_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING notice_id, digest",
        (tenant, purpose, locale, version, title, body, by),
    ).fetchone()
    return str(row[0]), row[1]


def _consiente(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    notice_id: str | None,
    digest: str,
    version: str = "1.0.0",
    decision: str = "accept",
    purpose: str = "privacy_notice",
    via: str = "web",
) -> str:
    row = conn.execute(
        "INSERT INTO privacy_consents "
        "(tenant_id, purpose, subject_kind, user_sub, subject_ref, decision, "
        " notice_source, notice_id, notice_digest, notice_version, notice_locale, "
        " via, actor_sub) "
        "VALUES (%s,%s,'user',%s,%s,%s,%s,%s,%s,%s,'es-MX',%s,%s) RETURNING consent_id",
        (
            tenant,
            purpose,
            user,
            user,
            decision,
            "tenant" if notice_id else "repo",
            notice_id,
            digest,
            version,
            via,
            user,
        ),
    ).fetchone()
    return str(row[0])


# ---------------------------------------------------------------------------
# El digest: una sola definición, dos implementaciones que deben coincidir
# ---------------------------------------------------------------------------

# Pares con acentos, emoji fuera del BMP y saltos de linea: los tres sitios donde
# una implementacion en Python y otra en SQL se separan sin avisar.
_CASOS = [
    ("es-MX", "Aviso", "cuerpo simple"),
    ("es-MX", "Aviso de privacidad", "Con acentos: informacion, proteccion, numero."),
    ("es-MX", "Aviso \U0001f6a8", "Emoji fuera del BMP \U0001f30e y texto despues."),
    ("en-US", "Notice", "Line one\nline two\n\nline four"),
    ("es-MX", "", ""),
    ("es-MX", "A\nB", "C"),
    ("es-MX", "A", "B\nC"),
]


@pytest.mark.parametrize(("locale", "title", "body"), _CASOS)
def test_digest_de_python_coincide_con_el_de_sql(
    seeded: psycopg.Connection, locale: str, title: str, body: str
) -> None:
    """Dos implementaciones independientes del MISMO digest, sobre 7 entradas.

    No basta con una: una sola entrada no distingue una funcion de una constante
    que hoy coincide. Aqui hay acentos, un emoji de 4 bytes y saltos de linea.
    """
    reset(seeded)
    en_sql = seeded.execute(
        "SELECT privacy_notice_digest(%s,%s,%s)", (locale, title, body)
    ).fetchone()[0]
    assert en_sql == notice_digest(locale, title, body)


def test_el_digest_distingue_donde_acaba_el_titulo() -> None:
    """``titulo="A\\nB", cuerpo="C"`` NO puede colisionar con ``"A"`` + ``"B\\nC"``.

    Un ``locale + "\\n" + titulo + "\\n" + cuerpo` los hace identicos: el mismo
    digest para dos avisos distintos deja pasar un cambio de texto como si no lo
    fuera. El prefijo de longitud por campo es lo que lo impide.
    """
    assert notice_digest("es-MX", "A\nB", "C") != notice_digest("es-MX", "A", "B\nC")


def test_el_digest_no_depende_de_la_etiqueta_de_version(seeded: psycopg.Connection) -> None:
    """El digest sella lo que la persona LEE, no como lo etiqueta el administrador.

    Consecuencia buscada: republicar el mismo texto con otra etiqueta no invalida
    los consentimientos ya dados (no es un cambio de aviso), y el indice unico lo
    rechaza como duplicado — una version nueva sin texto nuevo no es una version.
    """
    reset(seeded)
    _publica(seeded, version="1.0.0")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _publica(seeded, version="1.0.1")


def test_dos_textos_distintos_dan_digests_distintos(seeded: psycopg.Connection) -> None:
    reset(seeded)
    _, d1 = _publica(seeded, version="1.0.0", body=_CUERPO)
    _, d2 = _publica(seeded, version="1.1.0", body=_CUERPO + " Parrafo nuevo sobre ubicacion.")
    assert d1 != d2


# ---------------------------------------------------------------------------
# Append-only (regla de oro 11): ni el rol mas privilegiado edita el registro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tabla", "noop"),
    [("privacy_notices", "version = version"), ("privacy_consents", "decision = decision")],
)
def test_append_only_veta_el_update(seeded: psycopg.Connection, tabla: str, noop: str) -> None:
    reset(seeded)
    nid, dig = _publica(seeded)
    _consiente(seeded, notice_id=nid, digest=dig)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute(f"UPDATE {tabla} SET {noop}")


@pytest.mark.parametrize("tabla", ["privacy_notices", "privacy_consents"])
def test_append_only_veta_el_delete(seeded: psycopg.Connection, tabla: str) -> None:
    reset(seeded)
    nid, dig = _publica(seeded)
    _consiente(seeded, notice_id=nid, digest=dig)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute(f"DELETE FROM {tabla}")


def test_retirar_el_consentimiento_es_una_fila_nueva(seeded: psycopg.Connection) -> None:
    """Un consentimiento que no se puede retirar no es un consentimiento.

    Y retirarlo no puede borrar el de ayer: el registro tiene que poder decir que
    entre el dia 1 y el dia 2 SI habia consentimiento (art. 8 LFPDPPP: la
    revocacion opera hacia adelante, no reescribe el pasado).
    """
    reset(seeded)
    nid, dig = _publica(seeded)
    _consiente(seeded, notice_id=nid, digest=dig, decision="accept")
    _consiente(seeded, notice_id=nid, digest=dig, decision="withdraw")
    filas = seeded.execute(
        "SELECT decision FROM privacy_consents WHERE user_sub = %s ORDER BY decided_at", (USER_A,)
    ).fetchall()
    assert [f[0] for f in filas] == ["accept", "withdraw"]


# ---------------------------------------------------------------------------
# EL CORAZON DE LA TAREA: cambiar el aviso no reescribe lo ya consentido
# ---------------------------------------------------------------------------


def test_texto_corregido_deja_obsoleto_el_consentimiento_de_ayer(
    seeded: psycopg.Connection,
) -> None:
    """Se corrige una errata del aviso; el consentimiento de ayer queda obsoleto.

    La ETIQUETA de version es la misma ("1.0.0") en las dos filas a proposito: si
    la identidad fuera el numero de version, este test no distinguiria nada. Lo
    que cambia es el CONTENIDO, y es el contenido lo que el consentimiento sello.
    """
    reset(seeded)
    nid_v1, dig_v1 = _publica(seeded, version="1.0.0", body=_CUERPO)
    _consiente(seeded, notice_id=nid_v1, digest=dig_v1, version="1.0.0")

    # Corregir NO edita: el trigger append-only lo prohibe (arriba). Se publica
    # otra fila, con la misma etiqueta y una coma distinta.
    nid_v2, dig_v2 = _publica(seeded, version="1.0.0-r2", body=_CUERPO + " Correccion de errata.")

    vigente = seeded.execute(
        "SELECT notice_id, digest, version FROM privacy_notices "
        "WHERE tenant_id = %s AND purpose = 'privacy_notice' AND locale = 'es-MX' "
        "  AND effective_at <= now() "
        "ORDER BY effective_at DESC, seq DESC LIMIT 1",
        (TENANT_A,),
    ).fetchone()
    consentido = seeded.execute(
        "SELECT notice_digest, notice_version FROM privacy_consents "
        "WHERE user_sub = %s ORDER BY decided_at DESC LIMIT 1",
        (USER_A,),
    ).fetchone()

    assert str(vigente[0]) == nid_v2, "el aviso vigente es la fila nueva"
    assert vigente[1] == dig_v2
    assert consentido[0] == dig_v1, "el consentimiento de ayer conserva SU texto"
    assert consentido[0] != vigente[1], "y el sistema puede decir que ya no corresponde"

    # La fila v1 sigue entera: cambiar el aviso no reescribio nada hacia atras.
    v1 = seeded.execute(
        "SELECT digest, body FROM privacy_notices WHERE notice_id = %s", (nid_v1,)
    ).fetchone()
    assert v1[0] == dig_v1
    assert v1[1] == _CUERPO


def test_edicion_por_detras_del_trigger_sigue_siendo_detectable(
    seeded: psycopg.Connection,
) -> None:
    """La vía sucia: alguien MUTA la fila del aviso saltandose el trigger.

    ``session_replication_role = replica`` es exactamente lo que hace una
    herramienta de replicacion o un DBA con prisa, y desactiva los triggers de
    usuario. Es el escenario que un diseno por FK+version no puede ver:

    - la FK sigue apuntando a la MISMA fila,
    - la etiqueta de version no se ha movido,
    - y el texto que hay hoy no es el que se acepto.

    Lo que lo delata es el digest, que la propia base recalcula (columna
    GENERATED): no hay forma de mutar el cuerpo y dejar el sello quieto.
    """
    reset(seeded)
    nid, dig_original = _publica(seeded, version="1.0.0", body=_CUERPO)
    _consiente(seeded, notice_id=nid, digest=dig_original, version="1.0.0")

    seeded.execute("SET session_replication_role = replica")
    seeded.execute(
        "UPDATE privacy_notices SET body = %s WHERE notice_id = %s",
        (_CUERPO + " Parrafo anadido a escondidas.", nid),
    )
    seeded.execute("SET session_replication_role = origin")

    fila = seeded.execute(
        "SELECT c.notice_id, c.notice_version, c.notice_digest, n.version, n.digest "
        "FROM privacy_consents c JOIN privacy_notices n ON n.notice_id = c.notice_id "
        "WHERE c.user_sub = %s",
        (USER_A,),
    ).fetchone()

    # Lo que un diseno por FK + numero de version habria comprobado, y que aqui
    # PASA en verde mientras el registro miente:
    assert str(fila[0]) == nid, "la integridad referencial esta intacta"
    assert fila[1] == fila[3] == "1.0.0", "la etiqueta de version no se movio"
    # Lo unico que lo caza:
    assert fila[2] == dig_original
    assert fila[2] != fila[4], "el digest del texto de hoy ya no es el que se acepto"


def test_el_digest_del_aviso_lo_calcula_la_base_no_quien_inserta(
    seeded: psycopg.Connection,
) -> None:
    """``digest`` es GENERATED: no se puede insertar uno que no corresponda.

    Si fuera una columna normal, quien escribe podria sellar el texto A con el
    digest de B y el candado entero seria decorativo.
    """
    reset(seeded)
    with pytest.raises(psycopg.errors.GeneratedAlways):
        seeded.execute(
            "INSERT INTO privacy_notices "
            "(tenant_id, purpose, locale, version, title, body, published_by, digest) "
            "VALUES (%s,'privacy_notice','es-MX','9.9.9','Aviso',%s,%s,%s)",
            (TENANT_A, _CUERPO, USER_A, "0" * 64),
        )


# ---------------------------------------------------------------------------
# Regla de oro 5: aislamiento multi-tenant probado como takab_app, no leyendo
# una bandera (FORCE no protege del superusuario: BYPASSRLS va por delante).
# ---------------------------------------------------------------------------


def test_rls_el_aviso_de_otro_tenant_no_se_ve(seeded: psycopg.Connection) -> None:
    reset(seeded)
    _publica(seeded, tenant=TENANT_A, version="1.0.0")
    _publica(seeded, tenant=TENANT_B, version="2.0.0", body=_CUERPO + " Version del tenant B.")

    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=USER_A)
    filas = seeded.execute("SELECT tenant_id FROM privacy_notices").fetchall()
    assert filas, "el tenant A debe ver su propio aviso"
    assert {str(f[0]) for f in filas} == {TENANT_A}


def test_rls_el_consentimiento_de_otro_tenant_no_se_ve(seeded: psycopg.Connection) -> None:
    reset(seeded)
    nid_a, dig_a = _publica(seeded, tenant=TENANT_A)
    nid_b, dig_b = _publica(seeded, tenant=TENANT_B, body=_CUERPO + " Version del tenant B.")
    _consiente(seeded, tenant=TENANT_A, user=USER_A, notice_id=nid_a, digest=dig_a)
    _consiente(seeded, tenant=TENANT_B, user=USER_B, notice_id=nid_b, digest=dig_b)

    # Un tenant_admin ve los consentimientos de SU tenant (necesidad de
    # cumplimiento), jamas los del vecino.
    use(seeded, "takab_app", tenant=TENANT_B, app_role="tenant_admin", user_id=USER_B)
    filas = seeded.execute("SELECT tenant_id, user_sub FROM privacy_consents").fetchall()
    assert {str(f[0]) for f in filas} == {TENANT_B}
    assert {str(f[1]) for f in filas} == {USER_B}


def test_rls_no_se_puede_consentir_a_nombre_de_otro_tenant(seeded: psycopg.Connection) -> None:
    reset(seeded)
    nid, dig = _publica(seeded, tenant=TENANT_A)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="tenant_admin", user_id=USER_B)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _consiente(seeded, tenant=TENANT_A, user=USER_A, notice_id=nid, digest=dig)


def test_rls_un_ocupante_no_lee_el_consentimiento_de_su_companero(
    seeded: psycopg.Connection,
) -> None:
    """Dentro del MISMO tenant: quien no administra solo ve su propia fila."""
    reset(seeded)
    nid, dig = _publica(seeded, tenant=TENANT_A)
    _consiente(seeded, tenant=TENANT_A, user=USER_A, notice_id=nid, digest=dig)
    _consiente(seeded, tenant=TENANT_A, user=USER_B, notice_id=nid, digest=dig)

    use(seeded, "takab_app", tenant=TENANT_A, app_role="occupant", user_id=USER_B)
    filas = seeded.execute("SELECT user_sub FROM privacy_consents").fetchall()
    assert {str(f[0]) for f in filas} == {USER_B}


def test_rls_owner_con_force(seeded: psycopg.Connection) -> None:
    """``takab_migrator`` es DUENO de las tablas; FORCE lo sujeta igual a la RLS."""
    reset(seeded)
    _publica(seeded, tenant=TENANT_A)
    _publica(seeded, tenant=TENANT_B, body=_CUERPO + " Version del tenant B.")
    use(seeded, "takab_migrator", tenant=TENANT_A, app_role="tenant_admin", user_id=USER_A)
    filas = seeded.execute("SELECT tenant_id FROM privacy_notices").fetchall()
    assert {str(f[0]) for f in filas} == {TENANT_A}


# ---------------------------------------------------------------------------
# Coherencia del sujeto: la costura de WhatsApp (T-2.77) cabe en el motor
# ---------------------------------------------------------------------------


def test_optin_de_whatsapp_se_registra_contra_un_numero(seeded: psycopg.Connection) -> None:
    """El sujeto de un opt-in de WhatsApp es un TELEFONO, no un usuario.

    T-2.77 lo dejo escrito: hoy ``notifications.whatsapp.to`` es un numero suelto
    en el ``rule_set``, sin quien, sin cuando y sin prueba. El motor lo admite sin
    migracion: ``subject_kind='msisdn'``.
    """
    reset(seeded)
    _, dig = _publica(seeded, purpose="whatsapp_alerts", version="1.0.0", title="Aviso de contacto")
    fila = seeded.execute(
        "INSERT INTO privacy_consents "
        "(tenant_id, purpose, subject_kind, subject_ref, decision, notice_source, "
        " notice_digest, notice_version, notice_locale, via, actor_sub) "
        "VALUES (%s,'whatsapp_alerts','msisdn','+525512345678','accept','repo',"
        " %s,'1.0.0','es-MX','out_of_band',%s) RETURNING decided_at",
        (TENANT_A, dig, USER_A),
    ).fetchone()
    assert fila[0] is not None


def test_un_sujeto_msisdn_no_puede_llevar_user_sub(seeded: psycopg.Connection) -> None:
    reset(seeded)
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "INSERT INTO privacy_consents "
            "(tenant_id, purpose, subject_kind, user_sub, subject_ref, decision, "
            " notice_source, notice_digest, notice_version, notice_locale, via, actor_sub) "
            "VALUES (%s,'whatsapp_alerts','msisdn',%s,'+525512345678','accept','repo',"
            " %s,'1.0.0','es-MX','out_of_band',%s)",
            (TENANT_A, USER_A, "a" * 64, USER_A),
        )


def test_un_sujeto_usuario_no_puede_apuntar_a_otro_sub(seeded: psycopg.Connection) -> None:
    """``subject_ref`` tiene que ser el propio ``user_sub``: si pudieran diverger,
    la consulta por sujeto y la consulta por usuario darian respuestas distintas
    sobre la misma persona."""
    reset(seeded)
    nid, dig = _publica(seeded)
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "INSERT INTO privacy_consents "
            "(tenant_id, purpose, subject_kind, user_sub, subject_ref, decision, "
            " notice_source, notice_id, notice_digest, notice_version, notice_locale, "
            " via, actor_sub) "
            "VALUES (%s,'privacy_notice','user',%s,%s,'accept','tenant',%s,%s,'1.0.0',"
            " 'es-MX','web',%s)",
            (TENANT_A, USER_A, USER_B, nid, dig, USER_A),
        )


def test_el_origen_del_aviso_no_puede_mentir(seeded: psycopg.Connection) -> None:
    """``notice_source='tenant'`` exige la fila; ``'repo'`` exige que NO la haya."""
    reset(seeded)
    nid, dig = _publica(seeded)
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "INSERT INTO privacy_consents "
            "(tenant_id, purpose, subject_kind, user_sub, subject_ref, decision, "
            " notice_source, notice_id, notice_digest, notice_version, notice_locale, "
            " via, actor_sub) "
            "VALUES (%s,'privacy_notice','user',%s,%s,'accept','repo',%s,%s,'1.0.0',"
            " 'es-MX','web',%s)",
            (TENANT_A, USER_A, USER_A, nid, dig, USER_A),
        )
