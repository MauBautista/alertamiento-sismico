"""Todo acto que ESCRIBE evidencia deja verbo en la bitácora (T-5.20).

EL DEFECTO QUE CIERRA
---------------------
Firmar un dictamen escribía la fila del dictamen —con quién firmó, en una tabla
que no admite reescritura— y, **solo si el veredicto era habitable**, una acción
en el timeline. **No escribía en `audit_log`.** El hecho no se perdía; pero el
sitio donde un perito, un seguro o una auditoría van a buscar *«quién firmó qué y
cuándo»* es la bitácora, y **el acto de mayor peso legal del sistema no estaba
ahí**. Con un veredicto no habitable, además, tampoco dejaba acción.

POR QUÉ ESTO ES UN CENSO Y NO UN TEST DEL DICTAMEN
--------------------------------------------------
Arreglar la firma habría tardado diez minutos y habría dejado el hueco abierto
para el siguiente acto. Las dos poblaciones se **derivan**:

1. **Las tablas append-only** salen de `db/schema.sql`, contando los triggers
   cuya función es `forbid_update_delete()`. Es el propio esquema el que declara
   qué es evidencia; una tabla nueva protegida así entra en el censo sola.
2. **Los manejadores** salen del árbol de sintaxis de `api/.../routers`: los que
   están decorados con `post`/`put`/`patch`/`delete` y que escriben en una de
   esas tablas, directamente o por una constante SQL de su módulo o del módulo de
   `queries` que importan.

Y la exigencia se comprueba **dentro de la función**, no en el módulo: un
`audit_async` en el manejador de al lado no audita este acto.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]
_SRC = _RAIZ / "api" / "src" / "takab_api"
_SCHEMA = _RAIZ / "db" / "schema.sql"

#: Métodos HTTP que cambian algo. `get` no escribe evidencia.
_ESCRIBEN = {"post", "put", "patch", "delete"}

#: Los ayudantes que SÍ cuentan como dejar verbo. `audit_log` tiene escritor
#: único (`test_audit_single_writer.py`), así que estos nombres son la única
#: forma legítima de escribir en la bitácora.
_AUDITORES = {"audit_async", "audit_sync"}


def tablas_append_only() -> set[str]:
    """Las que el ESQUEMA declara evidencia, por su trigger. No una lista."""
    sql = _SCHEMA.read_text(encoding="utf-8")
    tablas = set(
        re.findall(
            r"CREATE TRIGGER\s+\S+\s+BEFORE\s+(?:UPDATE\s+OR\s+DELETE|DELETE\s+OR\s+UPDATE"
            r"|UPDATE|DELETE)\s+ON\s+(\w+)[^;]*?forbid_update_delete\(\)",
            sql,
            re.S | re.I,
        )
    )
    # `audit_log` es el destino, no un acto que auditar: exigirle verbo propio
    # sería pedir que la bitácora se auditara a sí misma.
    return tablas - {"audit_log"}


def _cadenas(nodo: ast.AST) -> str:
    return " ".join(
        n.value for n in ast.walk(nodo) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def _sql_por_nombre(fichero: Path) -> dict[str, str]:
    """Nombre de módulo → SQL que produce, de las DOS formas que usa el repo.

    `NOMBRE = "INSERT INTO …"` **y** `def insert_algo(...) -> text(...)`. La
    segunda es la que se me escapó al escribir este censo: los módulos de
    `queries` construyen la mayoría de sus sentencias en funciones, así que un
    censo que solo mirara asignaciones veía **cuatro** manejadores de los que hay
    —y pasaba en verde justo sobre el defecto que venía a cazar.
    """
    fuera: dict[str, str] = {}
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name):
            fuera[nodo.targets[0].id] = _cadenas(nodo.value)
        elif isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            fuera[nodo.name] = _cadenas(nodo)
    return fuera


def _modulos_de_queries(texto: str) -> list[Path]:
    nombres = re.findall(r"from takab_api\.queries import (\w+)", texto)
    nombres += re.findall(r"from takab_api\.queries\.(\w+) import", texto)
    nombres += re.findall(r"from takab_api\.queries import \w+ as (\w+)", texto)
    return [p for n in nombres if (p := _SRC / "queries" / f"{n}.py").exists()]


def _tablas_de(texto: str, tablas: set[str]) -> set[str]:
    return {t for t in tablas if re.search(rf"INSERT\s+INTO\s+{t}\b", texto, re.I)}


def _manejadores_que_escriben_evidencia() -> dict[str, set[str]]:
    """`fichero::funcion` → tablas de evidencia que escribe."""
    tablas = tablas_append_only()
    fuera: dict[str, set[str]] = {}
    for fichero in sorted((_SRC / "routers").glob("*.py")):
        texto = fichero.read_text(encoding="utf-8")
        arbol = ast.parse(texto)
        sqls = _sql_por_nombre(fichero)
        for q in _modulos_de_queries(texto):
            sqls |= {f"{q.stem}.{k}": v for k, v in _sql_por_nombre(q).items()}
            sqls |= _sql_por_nombre(q)

        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            metodos = {
                d.func.attr
                for d in nodo.decorator_list
                if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr in _ESCRIBEN
            }
            if not metodos:
                continue
            cuerpo = ast.unparse(nodo)
            tocadas = _tablas_de(cuerpo, tablas)
            # …y por los nombres de SQL que la función referencia.
            # El nombre SIMPLE del atributo, no `alias.nombre`: los módulos de
            # `queries` se importan con alias (`from … import dictamens as q`) y
            # buscar `q.insert_dictamen` no encontraba nada. Fue la segunda vez
            # que este censo se quedó ciego sobre el defecto que venía a cazar.
            referencias = {n.id for n in ast.walk(nodo) if isinstance(n, ast.Name)}
            referencias |= {n.attr for n in ast.walk(nodo) if isinstance(n, ast.Attribute)}
            for nombre in referencias:
                if nombre in sqls:
                    tocadas |= _tablas_de(sqls[nombre], tablas)
            if tocadas:
                fuera[f"{fichero.name}::{nodo.name}"] = tocadas
    return fuera


def _audita(fichero: str, funcion: str) -> bool:
    """¿Deja verbo DENTRO de la función? Un `audit_async` en el manejador de al
    lado no audita este acto, y por eso se mira la función y no el módulo."""
    arbol = ast.parse((_SRC / "routers" / fichero).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and nodo.name == funcion:
            llamadas = {
                n.func.id
                for n in ast.walk(nodo)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            if llamadas & _AUDITORES:
                return True
            # Un nivel de indirección: el manejador puede delegar en un ayudante
            # del mismo módulo que audita. Más niveles no se siguen a propósito:
            # un censo que persigue llamadas acaba encontrando cualquier cosa.
            for otro in llamadas:
                for n2 in ast.walk(arbol):
                    if (
                        isinstance(n2, ast.FunctionDef | ast.AsyncFunctionDef)
                        and n2.name == otro
                        and _AUDITORES
                        & {
                            c.func.id
                            for c in ast.walk(n2)
                            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                        }
                    ):
                        return True
    return False


#: Manejadores que escriben evidencia y NO dejan verbo, **con su razón**. La
#: lista se compara por IGUALDAD: uno que se arregle tiene que borrar su línea, y
#: uno nuevo no puede colarse. Una excepción que puede crecer sola es un agujero.
SIN_VERBO: dict[str, str] = {}
"""**Vacía, y a propósito.** Los doce manejadores que escriben evidencia dejan
verbo; el único que no lo hacía —`sign_dictamen`— se arregló en esta misma ficha
en vez de declararse excepción.

Se conserva la puerta porque puede haber un caso legítimo mañana: un acto de
volumen por-persona-y-por-incidente (miles en un macrosimulacro) contra una
bitácora exenta de poda sería una razón de verdad. Lo que la puerta exige es
**escribirla**. Y el vacío tiene su propio test: una lista de excepciones que
puede crecer sola no es una excepción, es un agujero.
"""

# ─────────────────────────────────────────────────── las afirmaciones


def test_el_censo_ve_ALGO():
    """Sin esto, un analizador ciego pasaría en verde con cero manejadores."""
    tablas = tablas_append_only()
    assert len(tablas) >= 12, f"el censo de tablas se quedó ciego: {sorted(tablas)}"
    manejadores = _manejadores_que_escriben_evidencia()
    # DOCE hoy. El número va escrito porque este censo se quedó ciego DOS veces
    # mientras se escribía —una por no leer el SQL que se construye en funciones,
    # otra por no resolver el alias de los módulos de `queries`— y en las dos
    # pasó en verde sobre el defecto que venía a cazar.
    assert len(manejadores) >= 12, f"el censo de manejadores se quedó ciego: {manejadores}"


def test_todo_acto_que_escribe_evidencia_deja_VERBO():
    manejadores = _manejadores_que_escriben_evidencia()
    mudos = sorted(k for k in manejadores if not _audita(*k.split("::")))
    detalle = "\n".join(f"  · {k} → escribe {sorted(manejadores[k])}" for k in mudos)
    assert mudos == sorted(SIN_VERBO), (
        "ACTOS QUE ESCRIBEN EVIDENCIA Y NO DEJAN VERBO EN LA BITÁCORA. El hecho no "
        "se pierde —su tabla es append-only— pero el sitio donde un perito, un "
        "seguro o una auditoría van a buscar «quién hizo qué y cuándo» es "
        "`audit_log`. Llama a `audit_async` dentro del manejador, o declara la "
        f"excepción en `SIN_VERBO` CON SU RAZÓN:\n{detalle}"
    )


def test_la_lista_de_excepciones_esta_VACIA_y_lo_declara():
    """Hoy no hay ninguna. Si aparece una, tiene que traer su razón escrita."""
    assert SIN_VERBO == {}, (
        "apareció una excepción: comprueba que su razón está escrita y que de "
        f"verdad no puede dejar verbo — {sorted(SIN_VERBO)}"
    )
    for clave, razon in SIN_VERBO.items():
        assert len(razon) > 120, f"{clave}: la razón es demasiado corta para ser una razón"


def test_ninguna_excepcion_esta_de_mas():
    """Una excepción que ya no aplica es una puerta abierta que nadie vigila."""
    manejadores = _manejadores_que_escriben_evidencia()
    sobran = sorted(set(SIN_VERBO) - set(manejadores))
    assert not sobran, f"declarados sin verbo y ya no escriben evidencia: {sobran}"
