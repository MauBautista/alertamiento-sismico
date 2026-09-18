"""Los dos techos del freno de exportación cuentan la MISMA población (T-7.45).

EL DEFECTO QUE CIERRA
---------------------
El freno de `T-5.18` tiene dos techos sobre `audit_log`: uno por USUARIO (sale
del `actor`) y otro por EDIFICIO (sale de `meta->>'site_id'`). Los dos filtran
por `verb = 'export_pdf'`.

Y `routers/exports.py` escribía **ese mismo verbo al DESCARGAR**, sin `meta`. O
sea que una descarga gastaba el techo del usuario y era invisible para el del
edificio. El daño no era un techo laxo —así lo contaba la ficha y está al
revés—: con un solo operador el techo que ata es el de usuario, así que seis
descargas baratas en Triage devolvían **429 a la primera generación de
dictamen**. Un tope de gasto convertido en negación de evidencia, sobre el
documento del que depende decidir si un edificio se ocupa.

POR QUÉ ESTO ES UN CENSO Y NO UN TEST DEL FRENO
-----------------------------------------------
Arreglar el verbo tarda un minuto y deja el hueco abierto para el siguiente
escritor. Lo que hace contables esos dos números es un invariante que nadie
estaba vigilando: **el verbo del freno tiene un solo escritor**. Mientras se
cumpla, las dos consultas cuentan las generaciones y nada más; en cuanto un
segundo sitio escribe el verbo, el techo estrecho se puede rebasar con actos que
el ancho no ve.

Las tres poblaciones se **derivan del fuente**, ninguna se teclea aquí:

1. **El verbo** sale de las dos constantes SQL del propio freno.
2. **La clave del `meta`** sale del `meta->>'…'` de la consulta del edificio.
3. **Los escritores** salen del árbol de sintaxis de todo `api/src/takab_api`.

Así que renombrar el verbo, mover el freno o añadir un escritor nuevo se ven
solos, sin que haya que acordarse de venir aquí.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]
_SRC = _RAIZ / "api" / "src" / "takab_api"
_FRENO = _SRC / "routers" / "reports.py"

#: Las dos constantes del freno, por nombre. Si alguna se renombra, el test dice
#: que no la encuentra en vez de aprobar sobre el vacío.
_CONSTANTES = ("_CUENTA_USUARIO", "_CUENTA_SITIO")

#: Los ayudantes que escriben en la bitácora. `audit_log` tiene escritor único
#: (`test_audit_single_writer.py`), así que estos dos nombres son la única forma
#: legítima de dejar un verbo.
_AUDITORES = {"audit_async", "audit_sync"}


def _sql_de_las_constantes() -> dict[str, str]:
    """El SQL literal de cada constante del freno, por AST.

    Por AST y no por `grep` a propósito: las cadenas están partidas en varios
    trozos con concatenación implícita, y un comentario del módulo que mencione
    `verb = '…'` no debe contar. `ast.literal_eval` junta los trozos y no ve los
    comentarios.
    """
    arbol = ast.parse(_FRENO.read_text(encoding="utf-8"))
    fuera: dict[str, str] = {}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Assign):
            continue
        nombres = {t.id for t in nodo.targets if isinstance(t, ast.Name)}
        objetivo = nombres & set(_CONSTANTES)
        if not objetivo:
            continue
        valor = nodo.value
        # `text("…")` de SQLAlchemy: interesa su único argumento.
        if isinstance(valor, ast.Call) and valor.args:
            valor = valor.args[0]
        try:
            fuera[objetivo.pop()] = ast.literal_eval(valor)
        except ValueError:  # pragma: no cover — sólo si dejara de ser literal
            pass
    return fuera


def _verbo_de(sql: str) -> str | None:
    m = re.search(r"verb\s*=\s*'([^']+)'", sql)
    return m.group(1) if m else None


def _clave_del_meta(sql: str) -> str | None:
    m = re.search(r"meta->>'([^']+)'", sql)
    return m.group(1) if m else None


def _constantes_posibles(expr: ast.expr, funcion: ast.AST) -> set[str]:
    """Las cadenas que esta expresión PUEDE valer, resolviendo un nivel de variable.

    ⚠️ Esto no es un refinamiento: sin ello el censo es CIEGO al defecto que
    existe para cazar. El escritor de más no ponía `verb="export_pdf"` en la
    llamada — asignaba el verbo a una local con un ternario y pasaba `verb=verb`,
    o sea un `ast.Name`. Mirando sólo `ast.Constant` las tres pruebas seguían en
    verde con el defecto repuesto, que es la tercera vez que un censo de este
    repo se queda ciego sobre su propio defecto (lo dice por escrito
    `test_evidencia_deja_verbo.py`). Medido: mutación repuesta ⇒ 3 passed.

    Un `f"download_{row.kind}"` (`ast.JoinedStr`) se queda deliberadamente sin
    resolver: es derivado, no puede casar con un verbo constante, y perseguirlo
    convertiría el censo en un intérprete.
    """
    if isinstance(expr, ast.Constant):
        return {expr.value} if isinstance(expr.value, str) else set()
    if isinstance(expr, ast.IfExp):  # el ternario: cuentan las DOS ramas
        return _constantes_posibles(expr.body, funcion) | _constantes_posibles(expr.orelse, funcion)
    if isinstance(expr, ast.Name):
        fuera: set[str] = set()
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == expr.id for t in nodo.targets
            ):
                fuera |= _constantes_posibles(nodo.value, funcion)
        return fuera
    return set()


def _escritores_del_verbo(verbo: str) -> dict[str, ast.Call]:
    """`{'routers/reports.py::generate_report': <call>}` para TODO `api/src`.

    Cuenta un escritor si el verbo PUEDE valer el del freno — incluida la vía por
    variable local y las dos ramas de un ternario (ver `_constantes_posibles`).
    """
    fuera: dict[str, ast.Call] = {}
    for fichero in sorted(_SRC.rglob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for llamada in ast.walk(nodo):
                if not isinstance(llamada, ast.Call):
                    continue
                nombre = (
                    llamada.func.id
                    if isinstance(llamada.func, ast.Name)
                    else getattr(llamada.func, "attr", "")
                )
                if nombre not in _AUDITORES:
                    continue
                for kw in llamada.keywords:
                    if kw.arg == "verb" and verbo in _constantes_posibles(kw.value, nodo):
                        rel = fichero.relative_to(_SRC).as_posix()
                        fuera[f"{rel}::{nodo.name}"] = llamada
    return fuera


# ───────────────────────────────────────────── las tres afirmaciones


def test_los_dos_techos_cuentan_el_MISMO_verbo() -> None:
    """Si contaran verbos distintos, el techo del edificio no protegería nada.

    Los dos literales se leen del fuente del freno; ninguno se teclea aquí.
    """
    sqls = _sql_de_las_constantes()
    assert set(sqls) == set(_CONSTANTES), (
        f"no se encontraron las constantes del freno en {_FRENO.name}: {sorted(sqls)}. "
        "Si se renombraron, este censo estaría aprobando sobre el vacío"
    )
    verbos = {n: _verbo_de(s) for n, s in sqls.items()}
    assert all(verbos.values()), f"alguna consulta del freno no filtra por `verb`: {verbos}"
    assert len(set(verbos.values())) == 1, (
        f"los dos techos del freno cuentan verbos DISTINTOS: {verbos}. Entonces uno de los dos "
        "no puede contar lo que el otro cuenta, y el edificio deja de estar protegido"
    )


def test_el_verbo_del_freno_lo_escribe_UN_solo_acto() -> None:
    """⚠️ **El invariante que hace contables los dos números.**

    Es el test que habría cazado `T-7.45`: con un segundo escritor, el techo
    estrecho se gasta con actos que el ancho no ve — y aquí el segundo escritor
    era una DESCARGA, que no renderiza nada, no sube nada a S3 y no llama a la
    IA de pago que el freno existe para proteger.
    """
    sqls = _sql_de_las_constantes()
    verbo = _verbo_de(sqls["_CUENTA_USUARIO"])
    assert verbo
    escritores = set(_escritores_del_verbo(verbo))
    assert escritores == {"routers/reports.py::generate_report"}, (
        f"el verbo `{verbo}` que cuenta el freno lo escribe más de un acto: {sorted(escritores)}. "
        "Cada escritor de más gasta el techo sin ser lo que el techo protege (renderizar un PDF, "
        "subirlo y pagar una llamada de IA). Si el acto nuevo es legítimo, dale verbo propio"
    )


def test_quien_escribe_el_verbo_lleva_la_clave_que_el_freno_lee() -> None:
    """La otra punta del mismo cable: sin esa clave, el techo del edificio cuenta cero.

    Las dos puntas se leen del fuente —la clave, de la consulta; el `meta`, de la
    llamada—, así que renombrar una sin la otra se ve aquí.
    """
    sqls = _sql_de_las_constantes()
    verbo = _verbo_de(sqls["_CUENTA_USUARIO"])
    clave = _clave_del_meta(sqls["_CUENTA_SITIO"])
    assert verbo and clave, f"no se pudo derivar verbo/clave del freno: {verbo!r}/{clave!r}"

    sin_clave = []
    for donde, llamada in _escritores_del_verbo(verbo).items():
        metas = [kw.value for kw in llamada.keywords if kw.arg == "meta"]
        claves: set[str] = set()
        for m in metas:
            if isinstance(m, ast.Dict):
                claves |= {k.value for k in m.keys if isinstance(k, ast.Constant)}
        if clave not in claves:
            sin_clave.append(f"{donde} (lleva {sorted(claves)})")
    assert not sin_clave, (
        f"escritor(es) de `{verbo}` sin la clave `{clave}` en su `meta`: {sin_clave}. "
        f"El techo del edificio filtra por `meta->>'{clave}'`, así que esas filas gastan el "
        "techo del usuario y son invisibles para el del sitio — exactamente el defecto de T-7.45"
    )
