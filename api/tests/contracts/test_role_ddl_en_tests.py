"""T-2.142 · Ningún test toca un rol del CLÚSTER.

`tests/ops/test_restore_check.py` hacía `ALTER ROLE takab_app RENAME TO
takab_app_probe` para provocar la comprobación de roles ausentes. Funcionaba —y
revertía, porque el DDL de PostgreSQL es transaccional— pero **los roles no son
de la base: son del clúster**. Mientras esa transacción vivía, NINGUNA otra base
del mismo Postgres tenía un rol `takab_app`.

**Medido:** no se podía verificar una migración contra base limpia mientras la
suite corría, aunque fuera otra base. Es la familia de `T-2.115` y `T-2.122` —el
veredicto depende de algo que no está en el test— pero cruzando la frontera de la
base, que es justo la que todo el aislamiento de la suite da por buena. Hoy la
suite es secuencial y no rompe nada; el día que alguien la paralelice, sí.

Este contract-test es la mitad que impide que vuelva. Dos capas, porque ninguna
sola alcanza:

1. **Estática** — el DDL de rol se caza en el ÁRBOL, antes de correr nada, así
   que también caza al que se escribe hoy y se ejecuta dentro de un `if` que
   nadie recorre. Su punto ciego está declarado abajo y se NOMBRA en el fallo.
2. **En caliente** — los roles que declara la migración 0001 tienen que existir
   AHORA. Caza al renombrado que sobreviva a su transacción, que es el daño de
   verdad, venga del árbol de tests o de fuera.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import psycopg

from takab_api.ops.restore_check import declared_roles

_TESTS = Path(__file__).resolve().parents[1]

#: DDL que cambia el catálogo de roles, que es GLOBAL al clúster. `SET ROLE` NO
#: entra a propósito: es local a la sesión y es como la suite emula cada rol.
_DDL_DE_ROL = re.compile(r"\b(?:CREATE|ALTER|DROP)\s+(?:ROLE|USER|GROUP)\b", re.IGNORECASE)

#: Nombre de rol que la sentencia toca, cuando se puede leer. Si no se puede, el
#: censo lo dice en vez de callarlo (lección de `incidentActionKinds`).
_OBJETIVO = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+(?:ROLE|USER|GROUP)\s+\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?",
    re.IGNORECASE,
)

#: Excepciones, con su razón. Una sola, y es este mismo fichero: sus sentencias
#: viven en cadenas que se escriben en `tmp_path` para el control positivo —el
#: detector tiene que llevar encima una muestra de lo que caza— y NINGUNA toca
#: una conexión. Ningún otro test necesita un rol propio; el que lo necesite
#: tendrá que escribir aquí por qué el clúster entero puede vivir con él mientras
#: corre, que es exactamente la fricción que busca `T-2.142`.
PERMITIDO: dict[str, str] = {
    "contracts/test_role_ddl_en_tests.py": (
        "el detector mismo: sus muestras se escriben en ficheros temporales y no se ejecutan "
        "contra ninguna base"
    ),
}


def _literales_de_sql(ruta: Path) -> list[str]:
    """Cadenas del módulo SIN docstrings (y sin comentarios, que no están en el
    AST). Es lo que separa una sentencia de la PROSA que la describe: esta misma
    cabecera cita `ALTER ROLE ... RENAME` y no debe delatarse a sí misma."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    docs: set[int] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            cuerpo = getattr(nodo, "body", [])
            if (
                cuerpo
                and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Constant)
                and isinstance(cuerpo[0].value.value, str)
            ):
                docs.add(id(cuerpo[0].value))
    return [
        n.value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]


def _delatores(ruta: Path) -> list[tuple[str, str]]:
    """(sentencia, rol objetivo o `?`) por cada DDL de rol del fichero."""
    hallazgos: list[tuple[str, str]] = []
    for literal in _literales_de_sql(ruta):
        for trozo in literal.split(";"):
            if not _DDL_DE_ROL.search(trozo):
                continue
            objetivo = _OBJETIVO.search(trozo)
            sentencia = " ".join(trozo.split())[:120]
            hallazgos.append((sentencia, objetivo.group(1) if objetivo else "?"))
    return hallazgos


def _modulos() -> list[Path]:
    return sorted(p for p in _TESTS.rglob("*.py") if "__pycache__" not in p.parts)


# ------------------------------------------------------------------ 1 · estática


def test_ningun_test_hace_ddl_sobre_un_rol_del_cluster() -> None:
    """El criterio de la ficha. Un `ALTER ROLE` en un test cambia el clúster
    entero: mientras corre, las OTRAS bases del mismo Postgres se quedan sin ese
    rol y cualquier cosa que dependa de él —una migración contra base limpia, otra
    suite en paralelo— falla por un motivo que no está escrito en ningún sitio."""
    modulos = _modulos()
    assert len(modulos) >= 100, (
        f"solo se recorrieron {len(modulos)} módulos bajo {_TESTS}: el censo estaría midiendo "
        "casi nada y este verde no significaría 'no hay DDL de rol'"
    )

    ofensores: list[str] = []
    for ruta in modulos:
        relativa = str(ruta.relative_to(_TESTS))
        if relativa in PERMITIDO:
            continue
        for sentencia, objetivo in _delatores(ruta):
            compartido = objetivo in declared_roles()
            ofensores.append(
                f"{relativa}: {sentencia!r} → rol {objetivo!r}"
                + (" (COMPARTIDO: lo declara la migración 0001)" if compartido else "")
                + (" (el censo no sabe a qué rol apunta)" if objetivo == "?" else "")
            )

    assert ofensores == [], (
        "DDL de rol dentro de la suite: los roles son objetos de CLÚSTER, no de la base, así que "
        "esto se ve desde TODAS las bases del mismo Postgres mientras el test corre (T-2.142).\n"
        + "\n".join(ofensores)
        + "\nAcredita lo mismo inyectando `Expectations` (verify(conn, expectations=…)) en vez de "
        "mutar el catálogo, o declara la excepción en PERMITIDO con su razón."
    )


def test_el_detector_distingue_una_sentencia_de_la_prosa_que_la_describe(tmp_path: Path) -> None:
    """**Control positivo y negativo: sin esto, el verde de arriba podría querer
    decir «el detector no detecta».** Es el defecto que esta sesión lleva diez
    lotes cerrando — un test que compara conjuntos y pasa por vacuidad."""
    real = tmp_path / "con_ddl.py"
    real.write_text(
        '"""Un módulo cualquiera."""\n'
        'def t(conn):\n    conn.execute("ALTER ROLE takab_app RENAME TO takab_app_probe")\n',
        encoding="utf-8",
    )
    assert _delatores(real) == [("ALTER ROLE takab_app RENAME TO takab_app_probe", "takab_app")]

    prosa = tmp_path / "solo_prosa.py"
    prosa.write_text(
        '"""Este módulo CITA `ALTER ROLE takab_app RENAME TO x` y no lo ejecuta."""\n'
        "def t():\n    # DROP ROLE takab_app  <- en un comentario tampoco cuenta\n    return 1\n",
        encoding="utf-8",
    )
    assert _delatores(prosa) == []

    opaco = tmp_path / "opaco.py"
    opaco.write_text(
        "def t(conn, rol):\n    conn.execute(f'DROP ROLE {rol}')\n",
        encoding="utf-8",
    )
    assert _delatores(opaco) == [("DROP ROLE", "?")], (
        "una sentencia cuyo objetivo no se puede leer tiene que NOMBRARSE, no colarse"
    )


# ---------------------------------------------------------------- 2 · en caliente


def test_los_roles_compartidos_siguen_existiendo_en_el_cluster(conn: psycopg.Connection) -> None:
    """La otra mitad: la estática no ve un rename que llegue por SQL construido en
    caliente, ni uno hecho fuera de la suite. Esto sí — y es el daño que importa:
    un renombrado que sobreviva a su transacción deja a TODAS las bases del
    clúster sin el rol, incluida la de producción del vecino de escritorio."""
    esperados = declared_roles()
    assert esperados, "no se pudieron derivar los roles de la migración 0001: esto no medía nada"
    presentes = {fila[0] for fila in conn.execute("SELECT rolname FROM pg_roles").fetchall()}
    faltan = sorted(esperados - presentes)
    assert not faltan, (
        f"roles de conexión ausentes del clúster: {faltan}. O alguien los renombró y no lo "
        "deshizo, o esta base se creó sin la migración 0001 (T-2.142)."
    )
