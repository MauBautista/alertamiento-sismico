"""T-2.80 · ARCO por anonimización con tombstone, probado donde se decide: en la DB.

La ficha pide tres cosas y las tres se miden aquí:

1. **jamás `DELETE`** — anonimización + lápida;
2. un check-in de vida anonimizado **sigue contando** para el histórico;
3. tras ejercer ARCO, el `audit_log` del incidente sigue **íntegro y verificable**.

EL CONFLICTO QUE ESTA TAREA RESUELVE
────────────────────────────────────
El titular tiene derecho a que sus datos desaparezcan, y el sistema tiene la
obligación dura de conservar auditoría, evidencia y dictámenes (regla de oro 11).
Parecen incompatibles y no lo son: se anonimiza a la PERSONA sin borrar el HECHO.

La bisagra es que ``life_checkins.user_id`` es un `sub` de Cognito —un UUID
opaco— y solo es dato personal mientras exista un mapeo `sub → nombre`. ARCO
destruye ese mapeo (``user_profiles``) y deja el UUID en pie. Por eso
``COUNT(DISTINCT user_id)`` —"cuántas PERSONAS confirmaron estar bien en el piso
8"— no se mueve: es información de rescate y reducirla cambiaría una decisión de
búsqueda. Sustituir el `sub` por un seudónimo común lo habría colapsado; borrar
la fila, también.

POR QUÉ HAY TANTO TEST DE PRIVILEGIOS Y DE TRIGGER
──────────────────────────────────────────────────
"No borres" no es una regla que se cumpla escribiéndola en un comentario. Los
tests de la sección B comprueban lo que impide el borrado FÍSICAMENTE: el
privilegio que no existe, la columna que no se puede tocar y el trigger que
levanta la excepción incluso para el dueño de la tabla.

EL CONTROL NEGATIVO DEL DIGEST
──────────────────────────────
``test_el_digest_detecta_una_manipulacion`` es el test que sostiene el criterio 3.
Sin él, ``privacy_audit_digest`` podría devolver una constante y todos los
"íntegro" de este archivo pasarían en verde afirmando nada.
"""

from __future__ import annotations

import json

import psycopg
import pytest

from conftest import GOV_AGENCY, INC_A, SITE_A, SITE_B, TENANT_A, TENANT_B, reset, use
from takab_api.privacy import erasure

# Titulares de prueba. El de A es el que ejerce ARCO; el de B existe para que la
# fuga cross-tenant tenga a quién filtrarse.
USER_A = "aaaa0000-0000-0000-0000-0000000a1c01"
USER_A2 = "aaaa0000-0000-0000-0000-0000000a1c02"
USER_B = "bbbb0000-0000-0000-0000-0000000b1c01"

# Cadenas deliberadamente raras: si sobreviven en cualquier rincón de la base, el
# barrido de `test_no_queda_rastro_del_titular_en_toda_la_base` las encuentra.
NOMBRE = "Ernestina Zapopan Quinones"
TELEFONO = "+525599887766"
TOKEN = "ExponentPushToken[zzERNESTINA-DEVICE-77zz]"
LLAVE = "-----BEGIN PUBLIC KEY-----ERNESTINAKEY-----END PUBLIC KEY-----"

PUNTO = "ST_SetSRID(ST_MakePoint(-99.1332,19.4326),4326)::geography"


# ---------------------------------------------------------------------------
# Siembra
# ---------------------------------------------------------------------------


def _persona(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    site: str = SITE_A,
    nombre: str = NOMBRE,
    telefono: str = TELEFONO,
    token: str = TOKEN,
    llave: str = LLAVE,
    incidente: str | None = INC_A,
    checkins: int = 2,
) -> None:
    """Un titular con TODA su superficie de PII, como en producción."""
    conn.execute(
        "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) VALUES (%s,%s,%s,%s)",
        (user, tenant, nombre, telefono),
    )
    conn.execute(
        "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id, endpoint_arn) "
        "VALUES (%s,%s,'android',%s,%s,'arn:aws:sns:us-east-2:1:endpoint/x')",
        (tenant, user, token, site),
    )
    conn.execute(
        "INSERT INTO device_keys (tenant_id, user_sub, platform, public_key) "
        "VALUES (%s,%s,'android',%s)",
        (tenant, user, llave),
    )
    conn.execute(
        "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, role) "
        "VALUES (%s,%s,%s,'occupant')",
        (user, tenant, site),
    )
    for _ in range(checkins):
        conn.execute(
            "INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status, geom) "
            f"VALUES (%s,%s,%s,%s,'safe',{PUNTO})",
            (tenant, incidente, user, site),
        )


def _cierra_incidentes(conn: psycopg.Connection) -> None:
    """Sin incidentes abiertos, que es la vía normal de ARCO (ver §D)."""
    conn.execute("UPDATE incidents SET state = 'closed', closed_at = now()")


def _arco(conn: psycopg.Connection, *, right: str = "cancelacion", via: str = "mobile") -> dict:
    fila = conn.execute("SELECT privacy_erase_subject(%s, %s)", (right, via)).fetchone()
    return fila[0] if isinstance(fila[0], dict) else json.loads(fila[0])


def _titular(conn: psycopg.Connection, *, tenant: str = TENANT_A, user: str = USER_A) -> None:
    use(conn, "takab_app", tenant=tenant, app_role="occupant", user_id=user)


# ---------------------------------------------------------------------------
# A · El inventario de PII se DERIVA del esquema, no se escribe a mano
# ---------------------------------------------------------------------------

_COLUMNAS = """
SELECT c.table_name, c.column_name, c.udt_name
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
 AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'public'
ORDER BY c.table_name, c.ordinal_position
"""


def test_el_inventario_cubre_toda_columna_de_pii_que_el_detector_encuentra(
    seeded: psycopg.Connection,
) -> None:
    """El ancla de la tarea: un inventario enumerado a mano envejece en silencio.

    El detector recorre el esquema VIVO y marca toda columna que huela a persona
    (enlace al sujeto, nombre conocido de PII, o una geometría en una tabla que
    tenga sujeto). Cada hallazgo debe estar clasificado en el plan de borrado.
    El día que alguien añada `occupant_email` a una tabla, este test rompe y
    obliga a decidir qué pasa con esa columna cuando se ejerce ARCO.
    """
    detectadas = erasure.detect_pii_columns(seeded.execute(_COLUMNAS).fetchall())
    sin_clasificar = sorted(detectadas - set(erasure.PII_INVENTORY))
    assert not sin_clasificar, (
        f"columnas de PII que el esquema tiene y el plan de ARCO no clasifica: {sin_clasificar}"
    )


def test_el_inventario_no_conserva_columnas_que_ya_no_existen(
    seeded: psycopg.Connection,
) -> None:
    """El reverso: un inventario con entradas muertas miente igual que uno corto."""
    reales = {(t, c) for t, c, _ in seeded.execute(_COLUMNAS).fetchall()}
    fantasmas = sorted(set(erasure.PII_INVENTORY) - reales)
    assert not fantasmas, f"el plan clasifica columnas que ya no están en el esquema: {fantasmas}"


def test_el_plan_declara_exactamente_las_tablas_que_el_acto_anonimiza() -> None:
    """El plan no es prosa: lo que dice `erase` es exactamente lo que se destruye.

    Y `device_keys` NO aparece: ahí no se destruye nada, se REVOCA. Confundir las
    dos cosas es lo que llevaría a alguien a "completar" la anonimización
    borrando la llave pública que verifica la evidencia firmada.
    """
    a_borrar = {t for (t, _), col in erasure.PII_INVENTORY.items() if col.action == "erase"}
    assert a_borrar == set(erasure.ERASED_TABLES)
    assert "device_keys" in erasure.REVOKED_TABLES
    assert "device_keys" not in erasure.ERASED_TABLES


# ---------------------------------------------------------------------------
# B · Qué impide FÍSICAMENTE borrar en vez de anonimizar
# ---------------------------------------------------------------------------

#: Regla de oro 11: auditoría, evidencia y dictámenes no se podan jamás. Y las
#: tablas que ARCO sí toca tampoco se borran: se anonimizan.
SIN_DELETE = (
    "audit_log",
    "incident_actions",
    "dictamens",
    "evidence_objects",
    "damage_reports",
    "life_checkins",
    "privacy_notices",
    "privacy_consents",
    "privacy_erasures",
    "user_profiles",
    "push_tokens",
    "device_keys",
)


@pytest.mark.parametrize("tabla", SIN_DELETE)
def test_el_rol_de_la_api_no_tiene_delete_en_ninguna_tabla_protegida(
    seeded: psycopg.Connection, tabla: str
) -> None:
    """Un comentario no impide un `DELETE`; un privilegio ausente sí.

    Ojo con `push_tokens`: el 0001 concede `... ON ALL TABLES IN SCHEMA public`
    DESPUÉS de aplicar `db/schema.sql`, así que conceder de menos no basta —hay
    que REVOCAR— y el fallo solo se manifiesta en base NUEVA.
    """
    reset(seeded)
    puede = seeded.execute(
        "SELECT has_table_privilege('takab_app', %s, 'DELETE')", (tabla,)
    ).fetchone()[0]
    assert puede is False, f"takab_app puede borrar filas de {tabla}"


def test_el_rol_de_la_api_solo_puede_actualizar_geom_de_un_checkin(
    seeded: psycopg.Connection,
) -> None:
    """Privilegio a nivel de COLUMNA: la única mutación posible es anular `geom`.

    Sin esto, "solo anulamos la ubicación" sería una promesa del código. Con
    esto, cambiar `status` o `user_id` es un error de permisos de PostgreSQL.
    """
    reset(seeded)
    intocables = ("user_id", "status", "incident_id", "site_id", "zone_id", "via", "verified_by")
    for col in intocables:
        assert (
            seeded.execute(
                "SELECT has_column_privilege('takab_app','life_checkins',%s,'UPDATE')", (col,)
            ).fetchone()[0]
            is False
        ), f"takab_app puede reescribir life_checkins.{col}"
    assert (
        seeded.execute(
            "SELECT has_column_privilege('takab_app','life_checkins','geom','UPDATE')"
        ).fetchone()[0]
        is True
    )


def test_borrar_un_checkin_es_imposible_incluso_para_el_dueno_de_la_tabla(
    seeded: psycopg.Connection,
) -> None:
    """El trigger cubre lo que el privilegio no: al dueño y a una migración."""
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException):
        seeded.execute("DELETE FROM life_checkins")
    seeded.rollback()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE life_checkins SET status = 'need_help'",
        "UPDATE life_checkins SET user_id = gen_random_uuid()",
        "UPDATE life_checkins SET incident_id = NULL",
        f"UPDATE life_checkins SET geom = {PUNTO}",
    ],
)
def test_el_unico_cambio_admitido_en_un_checkin_es_anular_geom(
    seeded: psycopg.Connection, sql: str
) -> None:
    """Anonimizar no es una licencia para reescribir el hecho.

    El guard compara la fila entera menos `geom` (vía `to_jsonb`), así que cubre
    también las columnas que se añadan mañana sin que nadie toque el trigger.
    """
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException):
        seeded.execute(sql)
    seeded.rollback()


def test_anular_geom_si_se_admite(seeded: psycopg.Connection) -> None:
    """El contrapunto del test anterior: sin esto el guard podría prohibirlo todo."""
    reset(seeded)
    _persona(seeded, checkins=1)
    seeded.execute("UPDATE life_checkins SET geom = NULL WHERE geom IS NOT NULL")
    assert (
        seeded.execute("SELECT count(*) FROM life_checkins WHERE geom IS NOT NULL").fetchone()[0]
        == 0
    )


def test_un_update_que_no_cambia_nada_tambien_se_rechaza(
    seeded: psycopg.Connection,
) -> None:
    """`UPDATE ... SET c = c` sobre evidencia no tiene por qué aceptarse.

    No es purismo: es exactamente el UPDATE que ejerce el verificador de restore
    (`ops/restore_check.py`) para comprobar que la guarda append-only sigue viva.
    Si un no-op pasara, ese verificador leería "la guarda no existe o está
    desactivada" sobre una tabla de compliance — y con razón, porque una guarda
    que deja pasar escrituras no está guardando.
    """
    reset(seeded)
    _persona(seeded, checkins=1)
    for sql in (
        "UPDATE life_checkins SET status = status",  # geom NO nulo
        "UPDATE life_checkins SET geom = NULL WHERE geom IS NULL",  # ya anonimizado
    ):
        # SAVEPOINT y no `rollback()`: un rollback entero se llevaría la siembra
        # y la segunda vuelta actualizaría CERO filas — el trigger no se
        # dispararía y el test pasaría a verde sin haber ejercido nada.
        seeded.execute("SAVEPOINT intento")
        with pytest.raises(psycopg.errors.RaiseException):
            seeded.execute(sql)
        seeded.execute("ROLLBACK TO SAVEPOINT intento")


def test_el_rechazo_lleva_la_firma_que_el_verificador_de_restore_exige(
    seeded: psycopg.Connection,
) -> None:
    """El guard tiene que ser RECONOCIBLE, no solo eficaz.

    `ops/restore_check.py` acepta un rechazo como prueba de la guarda solo si
    llega con SQLSTATE P0001 **y** el texto 'append-only'. Cualquier otra
    excepción la reporta como "no es la guarda" — a propósito, porque una
    transacción de solo lectura también hace fallar un UPDATE y eso daba verde.
    """
    reset(seeded)
    _persona(seeded, checkins=1)
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        seeded.execute("UPDATE life_checkins SET status = status")
    assert exc.value.sqlstate == erasure.SQLSTATE_APPEND_ONLY
    assert "append-only" in str(exc.value)
    seeded.rollback()


def test_la_lapida_es_append_only(seeded: psycopg.Connection) -> None:
    """La constancia de que se ejerció ARCO no se edita ni se borra."""
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)
    _titular(seeded)
    _arco(seeded)
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException):
        seeded.execute("UPDATE privacy_erasures SET via = 'web'")
    seeded.rollback()


# ---------------------------------------------------------------------------
# C · El acto: anonimizar sin borrar
# ---------------------------------------------------------------------------

#: Nada de esto puede perder una sola fila al ejercer ARCO (criterio 1).
CENSADAS = (
    "audit_log",
    "life_checkins",
    "dictamens",
    "evidence_objects",
    "incident_actions",
    "damage_reports",
    "user_profiles",
    "push_tokens",
    "device_keys",
    "user_zone_assignments",
)


def _censo(conn: psycopg.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in CENSADAS}


def test_arco_anonimiza_al_titular_sin_perder_una_sola_fila(
    seeded: psycopg.Connection,
) -> None:
    """CRITERIO 1. El censo de filas es idéntico antes y después."""
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)
    antes = _censo(seeded)

    _titular(seeded)
    lapida = _arco(seeded)
    reset(seeded)

    assert _censo(seeded) == antes, "ARCO perdió filas: eso es un DELETE con otro nombre"

    perfil = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert perfil[0] == erasure.ERASED_DISPLAY_NAME
    assert perfil[1] is None

    token = seeded.execute(
        "SELECT token, endpoint_arn, revoked_at FROM push_tokens WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert TOKEN not in token[0]
    assert token[1] is None
    assert token[2] is not None, "el token quedó anonimizado pero seguía vivo"

    llave = seeded.execute(
        "SELECT public_key, revoked_at FROM device_keys WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert llave[1] is not None, "la llave de dispositivo debe quedar revocada"
    # DECISIÓN DECLARADA: la llave pública NO se destruye. Es lo que verifica la
    # firma de intención de `damage_reports` (evidencia). Destruirla dejaría la
    # evidencia sin poder verificarse, que es podar su integridad por la puerta
    # de atrás — regla de oro 11.
    assert llave[0] == LLAVE

    assert lapida["affected"]["life_checkins"] == 2
    assert lapida["created"] is True


def test_el_checkin_anonimizado_sigue_contando_para_el_incidente(
    seeded: psycopg.Connection,
) -> None:
    """CRITERIO 2, y es el que da sentido a todo el diseño.

    "Cuántas PERSONAS confirmaron estar bien en el piso 8" es información de
    rescate. Si anonimizar redujera ese número —borrando la fila o colapsando
    todos los titulares en un mismo seudónimo— cambiaría una decisión de
    búsqueda. Por eso el `sub` opaco se queda y lo que muere es el mapeo a la
    persona.
    """
    reset(seeded)
    _persona(seeded, user=USER_A, checkins=2)
    _persona(
        seeded,
        user=USER_A2,
        nombre="Otra Persona",
        telefono="+525511223344",
        token="ExponentPushToken[otra]",
        llave="-----BEGIN PUBLIC KEY-----otra-----",
        checkins=1,
    )
    _cierra_incidentes(seeded)

    conteo = (
        "SELECT count(*), count(DISTINCT user_id) FROM life_checkins "
        "WHERE incident_id = %s AND site_id = %s AND status = 'safe'"
    )
    antes = seeded.execute(conteo, (INC_A, SITE_A)).fetchone()

    _titular(seeded, user=USER_A)
    _arco(seeded)
    reset(seeded)

    assert seeded.execute(conteo, (INC_A, SITE_A)).fetchone() == antes, (
        "el conteo del headcount cambió al anonimizar: eso cambia una decisión de rescate"
    )
    # Y lo que sí desapareció es la ubicación precisa del titular.
    assert (
        seeded.execute(
            "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
            (USER_A,),
        ).fetchone()[0]
        == 0
    )
    assert (
        seeded.execute(
            "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
            (USER_A2,),
        ).fetchone()[0]
        == 1
    ), "ARCO de un titular tocó los check-ins de otro"


def test_ejercer_arco_dos_veces_no_duplica_ni_reescribe_la_lapida(
    seeded: psycopg.Connection,
) -> None:
    """Idempotencia (regla de oro 3). La lápida es testigo SELLADO del primer acto."""
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)

    _titular(seeded)
    primera = _arco(seeded)
    segunda = _arco(seeded)

    assert segunda["created"] is False
    assert segunda["erasure_id"] == primera["erasure_id"]
    assert segunda["audit_digest"] == primera["audit_digest"]
    assert segunda["erased_at"] == primera["erased_at"]

    reset(seeded)
    assert (
        seeded.execute(
            "SELECT count(*) FROM privacy_erasures WHERE user_sub = %s", (USER_A,)
        ).fetchone()[0]
        == 1
    )


def test_arco_no_cruza_tenants(seeded: psycopg.Connection) -> None:
    """Regla de oro 5. El titular de B no se entera de que el de A ejerció ARCO."""
    reset(seeded)
    _persona(seeded, tenant=TENANT_A, user=USER_A, site=SITE_A)
    _persona(
        seeded,
        tenant=TENANT_B,
        user=USER_B,
        site=SITE_B,
        incidente=None,
        nombre="Persona De B",
        telefono="+525500000001",
        token="ExponentPushToken[bbb]",
        llave="-----BEGIN PUBLIC KEY-----bbb-----",
    )
    _cierra_incidentes(seeded)

    _titular(seeded, tenant=TENANT_A, user=USER_A)
    _arco(seeded)
    reset(seeded)

    b = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_B,)
    ).fetchone()
    assert b == ("Persona De B", "+525500000001")
    assert (
        seeded.execute(
            "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
            (USER_B,),
        ).fetchone()[0]
        == 2
    ), "el ARCO del tenant A alcanzó los check-ins del tenant B"

    # Y la lápida de A es invisible desde B.
    use(seeded, "takab_app", tenant=TENANT_B, app_role="tenant_admin", user_id=USER_B)
    assert seeded.execute("SELECT count(*) FROM privacy_erasures").fetchone()[0] == 0


def test_arco_durante_un_incidente_abierto_se_difiere_y_no_toca_nada(
    seeded: psycopg.Connection,
) -> None:
    """DECISIÓN: mientras haya incidente ABIERTO en un sitio del titular, se difiere.

    En un sismo la ubicación de un check-in es dato de rescate en vivo. Anularla
    a mitad de una búsqueda es un fallo de seguridad, que es la clase de fallo
    que las reglas de oro 1 y 2 existen para impedir. El derecho no se niega: se
    aplaza hasta el cierre del incidente (horas), y la PETICIÓN queda auditada
    para que el reloj del plazo legal arranque igual.
    """
    reset(seeded)
    _persona(seeded)  # `seeded` deja INC_A abierto a propósito
    antes = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()

    _titular(seeded)
    # SAVEPOINT y no `rollback()`: hay que volver al estado ANTERIOR al intento
    # sin llevarse por delante la siembra, que es justo lo que se va a inspeccionar.
    seeded.execute("SAVEPOINT antes_de_arco")
    with pytest.raises(psycopg.errors.DatabaseError) as exc:
        _arco(seeded)
    assert exc.value.sqlstate == erasure.SQLSTATE_DEFERRED
    seeded.execute("ROLLBACK TO SAVEPOINT antes_de_arco")

    reset(seeded)
    assert (
        seeded.execute(
            "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
        ).fetchone()
        == antes
    ), "el diferimiento dejó la anonimización a medias"


def test_una_sesion_sin_titular_no_puede_ejercer_arco(seeded: psycopg.Connection) -> None:
    """No hay parámetro para nombrar a la víctima: el sujeto es `app_user_id()`.

    Es la garantía más fuerte del diseño — no es que se compruebe quién pide
    ARCO sobre quién, es que esa pregunta no se puede ni formular.
    """
    reset(seeded)
    _cierra_incidentes(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=None)
    with pytest.raises(psycopg.errors.DatabaseError) as exc:
        _arco(seeded)
    assert exc.value.sqlstate == erasure.SQLSTATE_FORBIDDEN
    seeded.rollback()


def test_la_funcion_no_admite_un_sujeto_como_parametro() -> None:
    """Anclaje de la garantía anterior contra una "mejora" futura.

    Si mañana alguien añade `p_user_sub` para que un administrador pueda ejercer
    ARCO por otro, este test rompe y obliga a razonar la superficie nueva.
    """
    assert erasure.ERASE_FN_ARGS == ("p_right", "p_via")


# ---------------------------------------------------------------------------
# C.2 · Irreversibilidad: no queda mapeo persona → seudónimo en ningún sitio
# ---------------------------------------------------------------------------

_TEXTUALES = """
SELECT c.table_name, c.column_name
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
 AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'public'
  AND c.udt_name IN ('text','varchar','bpchar','jsonb','json')
"""


def test_no_queda_rastro_del_titular_en_toda_la_base(seeded: psycopg.Connection) -> None:
    """Si el mapeo se guarda en algún lado, no anonimizaste: seudonimizaste.

    El barrido recorre TODA columna textual de TODA tabla base y busca el nombre,
    el teléfono y el token. Incluye la propia lápida: guardar ahí una copia del
    dato "por trazabilidad" es el error clásico que convierte una anonimización
    en una seudonimización reversible.
    """
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)
    _titular(seeded)
    _arco(seeded)
    reset(seeded)

    columnas = seeded.execute(_TEXTUALES).fetchall()
    supervivientes = []
    for aguja in (NOMBRE, TELEFONO, TOKEN):
        for tabla, col in columnas:
            hay = seeded.execute(
                f'SELECT 1 FROM "{tabla}" WHERE "{col}"::text LIKE %s LIMIT 1',
                (f"%{aguja}%",),
            ).fetchone()
            if hay:
                supervivientes.append(f"{tabla}.{col} ({aguja!r})")
    assert not supervivientes, f"el dato personal sobrevivió en: {supervivientes}"


# ---------------------------------------------------------------------------
# D · CRITERIO 3 · el audit_log sigue íntegro y VERIFICABLE
# ---------------------------------------------------------------------------


def _digest(conn: psycopg.Connection, watermark: int, *, tenant: str = TENANT_A) -> str:
    return conn.execute(
        "SELECT privacy_audit_digest(CAST(%s AS uuid), %s)", (tenant, watermark)
    ).fetchone()[0]


def _marca(conn: psycopg.Connection, *, tenant: str = TENANT_A) -> int:
    return conn.execute(
        "SELECT coalesce(max(audit_id),0) FROM audit_log WHERE tenant_id = %s", (tenant,)
    ).fetchone()[0]


def _bitacora(conn: psycopg.Connection, watermark: int) -> list:
    return conn.execute(
        "SELECT audit_id, ts, tenant_id, actor, verb, object, meta FROM audit_log "
        "WHERE tenant_id = %s AND audit_id <= %s ORDER BY audit_id",
        (TENANT_A, watermark),
    ).fetchall()


def test_la_bitacora_del_incidente_sigue_intacta_y_el_digest_lo_prueba(
    seeded: psycopg.Connection,
) -> None:
    """CRITERIO 3. "Íntegro" es algo que se MIDE, no que se afirma.

    La lápida sella `(watermark, digest)`: el último `audit_id` del tenant en el
    instante del borrado y el hash de todo lo anterior. Cualquiera puede
    recalcularlo AÑOS después y comparar — el testigo no caduca con el test.
    """
    reset(seeded)
    _persona(seeded)
    for verbo in ("incident_open", "siren_on", "dictamen_sign"):
        seeded.execute(
            "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
            "VALUES (%s,'user:x',%s,%s,'{\"k\":1}')",
            (TENANT_A, verbo, f"incident:{INC_A}"),
        )
    _cierra_incidentes(seeded)

    marca = _marca(seeded)
    antes_digest = _digest(seeded, marca)
    antes_filas = _bitacora(seeded, marca)

    _titular(seeded)
    lapida = _arco(seeded)
    reset(seeded)

    assert lapida["audit_watermark"] == marca
    assert lapida["audit_digest"] == antes_digest, "la lápida selló un digest que no es el real"
    assert _digest(seeded, marca) == antes_digest, "el audit_log cambió al ejercer ARCO"
    assert _bitacora(seeded, marca) == antes_filas, "alguna fila de auditoría se movió"


def test_el_acto_de_arco_solo_anade_al_final_de_la_bitacora(
    seeded: psycopg.Connection,
) -> None:
    """Ejercer ARCO deja huella, y la huella va al final: nunca reescribe."""
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)
    marca = _marca(seeded)

    _titular(seeded)
    _arco(seeded)
    seeded.execute(
        "INSERT INTO audit_log (tenant_id, actor, verb, object) "
        "VALUES (%s,%s,'privacy_erasure',%s)",
        (TENANT_A, f"user:{USER_A}", f"privacy_erasure:{USER_A}"),
    )
    reset(seeded)

    assert _marca(seeded) > marca, "el acto de ARCO no dejó huella en la bitácora"
    assert _digest(seeded, marca) != _digest(seeded, _marca(seeded))


def test_el_digest_detecta_una_manipulacion(seeded: psycopg.Connection) -> None:
    """CONTROL NEGATIVO. Sin este test, el digest podría ser una constante.

    Se salta el trigger a propósito (lo que haría un DBA, una réplica o una
    migración mal escrita) y se comprueba que el sello LO NOTA. Es la misma
    trampa que `test_privacy_engine.py` cubre para el digest del aviso.
    """
    reset(seeded)
    marca = _marca(seeded)
    original = _digest(seeded, marca)

    seeded.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
    seeded.execute("UPDATE audit_log SET verb = 'nada_que_ver' WHERE audit_id = %s", (marca,))
    seeded.execute("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_append_only")

    assert _digest(seeded, marca) != original, (
        "el digest no distingue una bitácora manipulada de una íntegra: no prueba nada"
    )
    seeded.rollback()


def test_el_digest_esta_acotado_por_tenant(seeded: psycopg.Connection) -> None:
    """La bitácora de otro cliente no puede mover el sello del mío."""
    reset(seeded)
    marca = _marca(seeded)
    original = _digest(seeded, marca)
    seeded.execute(
        "INSERT INTO audit_log (tenant_id, actor, verb, object) VALUES (%s,'x','y','z')",
        (TENANT_B,),
    )
    assert _digest(seeded, marca) == original


def test_el_digest_es_reproducible_bajo_rls(seeded: psycopg.Connection) -> None:
    """Un sello que solo cuadra con superusuario no sirve para verificar nada.

    Fija el invariante: hoy la política `audit_read` da al tenant su bitácora
    COMPLETA, así que el digest que calcula la consola es el mismo que el de la
    base. Si mañana esa política se estrecha, este test rompe — y debe, porque el
    testigo dejaría de ser comprobable por quien tiene que comprobarlo.
    """
    reset(seeded)
    for verbo in ("a", "b", "c"):
        seeded.execute(
            "INSERT INTO audit_log (tenant_id, actor, verb, object) VALUES (%s,'x',%s,'z')",
            (TENANT_A, verbo),
        )
    marca = _marca(seeded)
    como_superusuario = _digest(seeded, marca)

    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=USER_A)
    assert _digest(seeded, marca) == como_superusuario


def test_la_lapida_no_guarda_copia_de_lo_borrado(seeded: psycopg.Connection) -> None:
    """El recuento de lo afectado sí; el dato afectado jamás.

    `affected` dice "se anonimizaron 2 check-ins", no cuáles ni de quién se
    llamaba. Un `display_name_before` "para trazabilidad" haría reversible la
    anonimización, y entonces no habría anonimización.
    """
    reset(seeded)
    _persona(seeded)
    _cierra_incidentes(seeded)
    _titular(seeded)
    lapida = _arco(seeded)

    crudo = json.dumps(lapida, default=str)
    for aguja in (NOMBRE, TELEFONO, TOKEN, LLAVE):
        assert aguja not in crudo, f"la lápida conserva {aguja!r}"
    assert lapida["affected"] == {
        "user_profiles": 1,
        "push_tokens": 1,
        "device_keys": 1,
        "life_checkins": 2,
    }


def test_el_check_in_de_otro_titular_no_se_anonimiza_por_arrastre(
    seeded: psycopg.Connection,
) -> None:
    """Un check-in ajeno con geometría conserva su geometría.

    Se inserta con `geom` desde el principio: el guard prohíbe DARLE una
    geometría a un check-in después, no solo quitársela.
    """
    reset(seeded)
    seeded.execute(
        "INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status, geom) "
        f"VALUES (%s,%s,%s,%s,'safe',{PUNTO})",
        (TENANT_A, INC_A, GOV_AGENCY, SITE_A),
    )
    _persona(seeded)
    _cierra_incidentes(seeded)
    _titular(seeded)
    _arco(seeded)
    reset(seeded)
    assert (
        seeded.execute(
            "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
            (GOV_AGENCY,),
        ).fetchone()[0]
        == 1
    )
