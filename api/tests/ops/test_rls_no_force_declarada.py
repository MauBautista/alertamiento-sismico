"""`tenant_retire_codes` sin FORCE: no es un defecto, es la tercera excepción (T-2.73.b).

El verificador de `T-2.73` avisa en cada corrida de que `tenant_retire_codes`
lleva RLS `ENABLE` **sin FORCE** y no encaja en ninguna de sus dos excepciones
de TimescaleDB. La ficha pedía una migración que pusiera FORCE.

**Medido antes de escribirla: poner FORCE ROMPE el segundo factor del retiro.**
`app_verify_retire_code` es `SECURITY DEFINER` y corre como el DUEÑO de la tabla
(`takab_migrator`, que no es superusuario ni tiene `BYPASSRLS`). `SECURITY
DEFINER` cambia el USUARIO, no los GUC: `app_role()` sigue siendo el del que
llama. Con FORCE, el dueño queda sujeto a la única política —que exige
`takab_superadmin`— y la verificación devuelve **false para un código
correcto**: retirar un gabinete pasa a ser imposible para un `tenant_admin`.

La decisión ya estaba escrita en la migración 0025 y en `db/schema.sql:1052`
(`ALTER TABLE tenant_retire_codes NO FORCE ROW LEVEL SECURITY` — el ÚNICO
`NO FORCE` explícito de todo el esquema). Lo que faltaba era que el verificador
la leyera. Por eso el arreglo no es una migración: es enseñarle a distinguir
«nadie declaró FORCE aquí» de «el esquema declara EXPLÍCITAMENTE que no lo
lleva», que es exactamente la diferencia entre un olvido y una excepción.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from takab_api.ops.restore_check import (
    PASS,
    WARN,
    declared_expectations,
    verify,
)


def _check(conn: psycopg.Connection, nombre: str):
    encontrados = [c for c in verify(conn).checks if c.name == nombre]
    assert encontrados, f"el verificador no emitió {nombre!r}"
    return encontrados[0]


# ------------------------------------------------------- la excepción, declarada


def test_el_esquema_declara_tenant_retire_codes_sin_force() -> None:
    """La fuente de verdad ya lo dice, y lo dice UNA sola vez.

    La distinción que sostiene todo el arreglo: **ausencia de la línea de FORCE
    ≠ `NO FORCE` escrito**. De lo primero hay tres casos —las dos hypertables
    sin caggs y ésta—, y los dos primeros son un olvido inocuo que ya cubre la
    excepción de TimescaleDB. De lo segundo hay UNO, y es una decisión.

    Si algún día apareciera un segundo `NO FORCE`, este test obliga a mirarlo: la
    exención tiene que seguir siendo una decisión con nombre, no una costumbre.
    """
    exp = declared_expectations()
    assert exp.rls["tenant_retire_codes"] == (True, False)
    assert sorted(exp.no_force) == ["tenant_retire_codes"], (
        f"apareció otro `NO FORCE` declarado: {sorted(exp.no_force)}. No lo añadas a la "
        "excepción sin medir, como aquí abajo, qué se rompe al ponerle FORCE."
    )
    # Y la contraparte: sin `NO FORCE` escrito, no hay exención por omisión.
    omitidas = {t for t, (rls, force) in exp.rls.items() if rls and not force} - exp.no_force
    assert omitidas, "si esto queda vacío, la distinción de arriba dejó de tener sentido"


# --------------------------------------- por qué NO se le pone FORCE, medido


def test_poner_FORCE_rompe_la_verificacion_del_codigo_de_retiro(
    conn: psycopg.Connection,
) -> None:
    """**La medición que desmonta la ficha.** El mismo código, el mismo llamador:
    sin FORCE verifica; con FORCE, no.

    El arnés se confirma a sí mismo: primero exige el `true` SIN FORCE. Si eso
    fallara, el `false` de después no probaría nada — probaría que el código
    estaba mal escrito.
    """
    tenant = uuid.uuid4()
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, %s, 'Probe FORCE')",
        (tenant, f"t-force-{tenant.hex[:8]}"),
    )
    conn.execute(
        "INSERT INTO tenant_retire_codes (tenant_id, code_hash, rotated_by) "
        "VALUES (%s, crypt(%s, gen_salt('bf', 12)), %s)",
        (tenant, "SECRETO-123", uuid.uuid4()),
    )
    # El llamador real del retiro: un tenant_admin, no el superadmin que ROTA.
    conn.execute("SELECT set_config('app.role', 'tenant_admin', true)")
    verificar = "SELECT app_verify_retire_code(%s, %s)"

    assert conn.execute(verificar, (tenant, "SECRETO-123")).fetchone()[0] is True, (
        "el arnés no montó el escenario: sin FORCE el código correcto ya no verifica"
    )

    conn.execute("ALTER TABLE tenant_retire_codes FORCE ROW LEVEL SECURITY")

    assert conn.execute(verificar, (tenant, "SECRETO-123")).fetchone()[0] is False, (
        "con FORCE la verificación seguía funcionando: revisa esta ficha entera, "
        "porque su conclusión depende de que NO funcione"
    )


# ------------------------------------------------- el verificador deja de mentir


def test_el_verificador_no_avisa_de_una_excepcion_DECLARADA(conn: psycopg.Connection) -> None:
    """Lo que la ficha pedía arreglar, arreglado donde tocaba: en quien avisa."""
    check = _check(conn, "rls_on_tenant_tables")
    assert check.status == PASS, check.detail
    assert "tenant_retire_codes" not in check.detail


def test_una_tabla_sin_force_que_NADIE_declaro_sigue_avisando(conn: psycopg.Connection) -> None:
    """El control, y es el que impide que esto sea una puerta trasera.

    La exención sale de `db/schema.sql`, no de una lista dentro del verificador:
    una tabla con `tenant_id` y RLS sin FORCE que el esquema no declare sigue
    saliendo como AVISO. Para saltarse la comprobación hay que ESCRIBIR el
    `NO FORCE` en la fuente de verdad, que es donde se revisa.
    """
    conn.execute("CREATE TABLE probe_sin_force (id int, tenant_id uuid)")
    conn.execute("ALTER TABLE probe_sin_force ENABLE ROW LEVEL SECURITY")
    check = _check(conn, "rls_on_tenant_tables")
    assert check.status == WARN
    assert "probe_sin_force" in check.detail


def test_una_tabla_con_tenant_id_y_SIN_rls_sigue_siendo_FALLO(conn: psycopg.Connection) -> None:
    """Y la exención no se derrama hacia arriba: «sin FORCE declarado» jamás
    puede convertirse en «sin RLS», que es un fallo de aislamiento, no un
    matiz de propiedad."""
    conn.execute("CREATE TABLE probe_sin_rls (id int, tenant_id uuid)")
    check = _check(conn, "rls_on_tenant_tables")
    assert check.status != PASS
    assert "probe_sin_rls" in check.detail


@pytest.mark.parametrize("tabla", ["tenant_retire_codes"])
def test_la_excepcion_declarada_no_apaga_la_comprobacion_ESTRICTA(
    conn: psycopg.Connection, tabla: str
) -> None:
    """`rls_flags` compara el catálogo contra lo declarado tabla por tabla, así
    que la exención de arriba no deja hueco: si alguien APAGA la RLS de la tabla
    exenta, esa otra comprobación lo caza igual."""
    from takab_api.ops.restore_check import FAIL

    conn.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
    assert _check(conn, "rls_flags").status == FAIL
