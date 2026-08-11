"""T-2.122 · Una corrida no puede heredar el veredicto de la anterior.

`T-2.115` cerró que el veredicto dependiera del **orden de recolección** dentro de un
proceso. Quedaba viva la mitad más cara: ``tenants``, ``sites``, ``sensors``,
``gateways``, ``zones`` y ``visibility_grants`` **no entraban en ningún ``TRUNCATE``**
de teardown, así que sobrevivían a la corrida entera y la siguiente arrancaba sobre
lo que dejó la anterior. Ése es el mecanismo que costó una sesión: el defecto de
T-2.115 no se pudo reproducir hasta borrar esas filas a mano.

**Medido (2026-08-11), no razonado por parecido.** Sobre la base que dejó una corrida
completa y verde, UNA fila en ``visibility_grants`` —un grant ``target_all`` para el
tenant compartido, que **ninguna fixture siembra**— pone en rojo seis pruebas de
aislamiento multi-tenant:

    tests/api/test_compliance_labels.py::test_pedir_las_de_otro_cliente_es_404_y_NO_un_documento_vacio
    tests/api/test_console_scope.py::test_un_alcance_ajeno_no_devuelve_nada_del_tenant
    tests/api/test_dictamens.py::test_cross_tenant_sign_is_404
    tests/api/test_drills_schedule.py::test_agenda_con_sitio_ajeno_o_inexistente_404
    tests/api/test_events.py::test_un_voto_de_otra_red_no_inventa_etiqueta
    tests/api/test_incidents.py::test_cross_tenant_incident_is_invisible

Es la refutación del otro camino que ofrecía la ficha: una siembra autoritativa
(``ON CONFLICT … DO UPDATE``) corrige el **valor** de una fila que alguien vuelve a
sembrar, pero **no puede hacer nada** contra una fila que **nadie siembra**. Por eso
lo elegido es vaciar en el arranque —``conftest._base_sin_herencia``—, y entero: la
lista de tablas se deriva del catálogo de Postgres, no de una lista a mano.

Los dos candados de este fichero:

1. **De extremo a extremo** — se deja el residuo COMMITEADO y se corre un pytest hijo
   sobre el nodo que ese residuo rompe. Tiene que salir verde. Sin el vaciado sale
   rojo en menos de un segundo.
2. **Observado** — el censo tomado justo después de vaciar, sobre TODAS las tablas de
   negocio del catálogo, tiene que ser cero. Cubre la siguiente tabla que alguien
   añada sin que nadie se acuerde de limpiarla.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

import auth_utils as au
import seed_shared

API_DIR = Path(__file__).resolve().parents[1]

#: Nodo que el residuo rompe. Es una prueba de aislamiento multi-tenant (regla de oro
#: 5): el residuo no la pone "un poco" rara, la invierte.
NODO_VICTIMA = "tests/api/test_incidents.py::test_cross_tenant_incident_is_invisible"

#: Autor ficticio del grant residual. No existe en `user_profiles` a propósito:
#: `created_by` no tiene FK, y una corrida anterior bien pudo dejar el id de un
#: usuario que ya no está.
AUTOR_DEL_RESIDUO = "00000000-0000-0000-0000-0000000000ff"

#: Las tablas que sobrevivían a la corrida entera antes de T-2.122, con su censo real
#: al terminar una suite completa y verde (2026-08-11):
#: sites 19, gateways 10, sensors 9, tenants 8, zones 5, visibility_grants 0-o-1.
#: Se nombran para que exentar cualquiera de ellas del vaciado sea un rojo, no un
#: descuido silencioso.
TABLAS_QUE_SOBREVIVIAN = frozenset(
    {"tenants", "sites", "sensors", "gateways", "zones", "visibility_grants"}
)


def _dsn() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://") if url else None


# --- 1. Candado de extremo a extremo: el residuo no decide el veredicto ---------


def _sembrar_residuo(dsn: str) -> None:
    """Deja COMMITEADO el residuo que una corrida anterior pudo dejar.

    El tenant se inserta con su valor canónico (y ``DO NOTHING``) solo para satisfacer
    la FK del grant: lo que se está probando es el **grant**, que no lo siembra nadie
    y por tanto ninguna siembra autoritativa podría corregir.
    """
    tenant_id, code, visibilidad = next(
        fila for fila in seed_shared.SHARED_TENANTS if fila[0] == au.DB_TENANT_PRIV
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (tenant_id) DO NOTHING",
            (tenant_id, code, seed_shared.TENANT_NAME, visibilidad),
        )
        conn.execute(
            "INSERT INTO visibility_grants "
            "(grantee_tenant_id, target_all, can_view_metadata, can_view_data, created_by) "
            "VALUES (%s, true, true, true, %s) ON CONFLICT DO NOTHING",
            (tenant_id, AUTOR_DEL_RESIDUO),
        )


def _borrar_residuo(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM visibility_grants WHERE created_by = %s", (AUTOR_DEL_RESIDUO,))


def test_una_corrida_no_hereda_el_veredicto_de_la_anterior() -> None:
    """Con el residuo de la corrida anterior dentro, el hijo tiene que salir verde.

    Corre en un proceso aparte porque "de qué estado arranca la corrida" es una
    propiedad del proceso de pytest, no de un test. Sin el vaciado de arranque el hijo
    sale rojo: el grant residual le abre a un tenant los datos de otro.
    """
    dsn = _dsn()
    if not dsn:
        pytest.skip("sin DATABASE_URL")
    _sembrar_residuo(dsn)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:randomly",
                "-p",
                "no:cacheprovider",
                NODO_VICTIMA,
            ],
            cwd=API_DIR,
            env={**os.environ},
            capture_output=True,
            text=True,
            timeout=600,
        )
    finally:
        _borrar_residuo(dsn)
    assert proc.returncode == 0, (
        "una corrida heredó el estado de la anterior: un grant residual en "
        "`visibility_grants` cambió el veredicto de una prueba de aislamiento "
        "multi-tenant (T-2.122).\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-2000:]}"
    )


# --- 2. Candado observado: el censo de arranque es cero -------------------------
#
# El censo llega COMO FIXTURE, no por `import conftest`: con `tests/__init__.py`
# presente pytest carga el conftest como `tests.conftest`, así que un `import
# conftest` devuelve otro objeto módulo con el censo vacío — y estos tres candados
# saldrían verdes midiendo la nada. Medido: pasa exactamente eso.


def test_el_censo_de_arranque_se_tomo_de_verdad(_base_sin_herencia: dict[str, int]) -> None:
    """Sin censo no hay candado: los de abajo saldrían verdes por vacío."""
    assert _base_sin_herencia, (
        "`conftest._base_sin_herencia` no dejó censo: o no corrió, o no encontró "
        "tablas. Un candado que no mide nada es peor que no tenerlo (T-2.122)."
    )


def test_la_corrida_arranca_sin_una_sola_fila_heredada(
    _base_sin_herencia: dict[str, int],
) -> None:
    """TODA tabla de negocio arranca vacía. La lista sale del catálogo, no de aquí."""
    con_filas = {t: n for t, n in _base_sin_herencia.items() if n}
    assert not con_filas, (
        "esta corrida arrancó sobre filas que dejó la anterior, así que su veredicto "
        f"no es solo suyo (T-2.122): {con_filas}"
    )


def test_las_tablas_que_sobrevivian_entran_en_el_vaciado(
    _base_sin_herencia: dict[str, int],
) -> None:
    """Las seis que costaron la sesión, nombradas: exentar una tiene que ser un rojo."""
    faltan = TABLAS_QUE_SOBREVIVIAN - set(_base_sin_herencia)
    assert not faltan, (
        f"{sorted(faltan)} volvió a quedar fuera del vaciado de arranque. Son las "
        "tablas que sobrevivían a la corrida entera y hacían que el veredicto "
        "dependiera de lo que dejó la anterior (T-2.122)."
    )
