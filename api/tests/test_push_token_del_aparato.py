"""[T-9.05] `app_claim_push_token`: el token de push es del APARATO, no de la persona.

La RLS `pt_self` de `push_tokens` acota cada fila a su `user_sub`, y eso impedía
al SIGUIENTE usuario del mismo teléfono registrar el mismo token FCM: el
ON CONFLICT DO UPDATE chocaba con la política («new row violates row-level
security policy (USING expression)») y la app —best-effort— se callaba. El
teléfono se quedaba sin push para el edificio del usuario nuevo.

La salida es la de `app_notify_delivery`/`gov_ack_incident`: una función
`SECURITY DEFINER` con dueño `takab_ingest` (BYPASSRLS). Lo que la hace segura
no es la RLS —la salta a propósito— sino lo que se comprueba aquí:

* la identidad sale SOLO de la sesión (`app_user_id()`, `app_tenant_id()`,
  `app_role()`); la firma no tiene por dónde recibir otra;
* un sitio de OTRO tenant se rechaza DENTRO, aunque el router ya lo filtre;
* nadie más que `takab_app` puede ejecutarla.

Contra la base de verdad, en una transacción que se revierte.
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import SITE_A, SITE_B, TENANT_A, TENANT_B, reset, use

USER_1 = "70000000-0000-0000-0000-0000000905a1"
USER_2 = "70000000-0000-0000-0000-0000000905b2"

_FIRMA = "app_claim_push_token(text,text,uuid)"


def _reclamar(conn: psycopg.Connection, token: str, site: str | None, platform: str = "android"):
    return conn.execute(
        "SELECT push_token_id, tenant_id::text, user_sub::text, role, site_id::text "
        "FROM app_claim_push_token(%s, %s, %s::uuid)",
        (token, platform, site),
    ).fetchone()


def test_la_funcion_es_SECURITY_DEFINER_de_takab_ingest(conn: psycopg.Connection) -> None:
    """Sin dueño `takab_ingest` correría como el migrador, la RLS FORCE la dejaría
    ciega y el traspaso seguiría fallando — en silencio, porque la app calla."""
    fila = conn.execute(
        "SELECT pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig "
        "FROM pg_proc p WHERE p.oid = %s::regprocedure",
        (_FIRMA,),
    ).fetchone()
    assert fila is not None, "falta app_claim_push_token(text, text, uuid)"
    dueño, secdef, config = fila
    assert dueño == "takab_ingest"
    assert secdef is True
    assert any(c.startswith("search_path=") for c in (config or [])), (
        "SECURITY DEFINER sin search_path fijo: cualquiera con CREATE en un esquema "
        "anterior podría suplantar una tabla dentro de la función"
    )


def test_la_firma_NO_admite_identidad_por_parametro(conn: psycopg.Connection) -> None:
    """Ni `user_sub` ni `tenant_id` pueden llegar como argumento: si pudieran, un
    llamante registraría el aparato a nombre de otro."""
    args = conn.execute(
        "SELECT pg_get_function_identity_arguments(%s::regprocedure)", (_FIRMA,)
    ).fetchone()[0]
    assert args == "p_token text, p_platform text, p_site uuid"


def test_solo_takab_app_puede_ejecutarla(conn: psycopg.Connection) -> None:
    for rol, esperado in (("takab_app", True), ("public", False)):
        tiene = conn.execute(
            "SELECT has_function_privilege(%s, %s::regprocedure, 'EXECUTE')", (rol, _FIRMA)
        ).fetchone()[0]
        assert tiene is esperado, rol
    # Y su dueño puede INSERTAR: sin esto la función sólo sabría actualizar.
    assert conn.execute(
        "SELECT has_table_privilege('takab_ingest', 'push_tokens', 'INSERT')"
    ).fetchone()[0]


def test_el_siguiente_usuario_del_telefono_se_queda_la_fila(seeded: psycopg.Connection) -> None:
    """El defecto medido, a nivel de base: antes era un error de RLS."""
    conn = seeded
    use(conn, "takab_app", tenant=TENANT_A, app_role="occupant", user_id=USER_1)
    primero = _reclamar(conn, "fcm-db-compartido", SITE_A)
    use(conn, "takab_app", tenant=TENANT_B, app_role="brigadista", user_id=USER_2)
    segundo = _reclamar(conn, "fcm-db-compartido", SITE_B)

    assert segundo[0] == primero[0], "un aparato, una fila"
    assert segundo[1:] == (TENANT_B, USER_2, "brigadista", SITE_B)
    reset(conn)
    assert (
        conn.execute(
            "SELECT count(*) FROM push_tokens WHERE token = 'fcm-db-compartido'"
        ).fetchone()[0]
        == 1
    )


def test_sin_identidad_de_sesion_no_reclama_nada(seeded: psycopg.Connection) -> None:
    conn = seeded
    use(conn, "takab_app", tenant=TENANT_A, app_role="occupant", user_id=None)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _reclamar(conn, "fcm-sin-sesion", None)


def test_un_sitio_de_OTRO_tenant_se_rechaza_DENTRO(seeded: psycopg.Connection) -> None:
    """Defensa en profundidad: el router ya lo filtra con `assert_site_access`,
    pero una función SECURITY DEFINER no puede fiarse de quien la llama."""
    conn = seeded
    use(conn, "takab_app", tenant=TENANT_A, app_role="occupant", user_id=USER_1)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _reclamar(conn, "fcm-sitio-ajeno", SITE_B)


def test_una_lapida_de_ARCO_se_rechaza_DENTRO(seeded: psycopg.Connection) -> None:
    conn = seeded
    use(conn, "takab_app", tenant=TENANT_A, app_role="occupant", user_id=USER_1)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _reclamar(conn, "arco:00000000-0000-0000-0000-000000000000", None)


def test_el_espejo_lleva_EL_MISMO_cuerpo_que_la_migracion(conn: psycopg.Connection) -> None:
    """`db/schema.sql` y la 0071 escriben la función dos veces. Una base creada
    desde el espejo tiene que reclamar igual que una migrada: se compara el
    cuerpo del espejo con el que la base de verdad está ejecutando."""
    from pathlib import Path

    esquema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text("utf-8")
    inicio = esquema.index("CREATE FUNCTION app_claim_push_token(")
    cuerpo_espejo = esquema[inicio:].split("$fn$")[1]
    cuerpo_vivo = conn.execute(
        "SELECT prosrc FROM pg_proc WHERE oid = %s::regprocedure", (_FIRMA,)
    ).fetchone()[0]
    assert cuerpo_espejo.strip() == cuerpo_vivo.strip()
