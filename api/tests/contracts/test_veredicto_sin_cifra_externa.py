"""T-5.27 · La cifra externa se queda FUERA del veredicto, y ahora hay quien lo vigile.

El desacoplamiento es genuino y estructural: la entrada del motor tiene siete
campos y **ninguno admite** una magnitud ni una línea de catálogo, y ni el motor
ni el pase que lo alimenta importan nada forense. Pero los catorce tests del
motor afirman lo que la regla **sí** hace; **ninguno afirmaba que el catálogo no
la mueve**. Añadir el campo mañana no ponía nada en rojo.

Por qué importa más que la mayoría de las guardas: el dictamen decide si un
edificio se habita. Que esa decisión dependa SOLO de lo que midió el sensor de
ese inmueble —y no de una magnitud publicada por un tercero para un epicentro a
300 km— es la diferencia entre un peritaje y una opinión. La magnitud del SSN
describe el SISMO; el dictamen describe el EDIFICIO, y un M7 lejano puede dejar
una nave intacta mientras un M5 debajo la parte.

Con `T-5.10` y `T-5.11` en la cola —las dos traen cifra externa al documento—
esta guarda deja de ser opcional: son justo las fichas que tendrán el dato a mano
en el mismo módulo.

Las dos mitades, y por qué hacen falta las dos:

1. **Por igualdad, no por pertenencia.** `set(campos) == LOS_SIETE` se pone rojo
   al AÑADIR un campo. Un `assert "magnitude" not in campos` solo cazaría ese
   nombre exacto, y `catalog_magnitude`, `mag_ssn` o `magnitud_externa` pasarían.
2. **Por barrido del árbol de sintaxis.** Un campo no es la única forma de meter
   la cifra: el motor podría importarla y consultarla por su cuenta. Se prohíbe
   el import en los DOS módulos que producen el veredicto.
"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from takab_api.dictamen.rules import EvalInput

_SRC = Path(__file__).resolve().parents[2] / "src/takab_api"

#: La entrada del veredicto, campo a campo. Cada uno es una medición del PROPIO
#: inmueble o un umbral de su rule_set; ninguno viene de un catálogo externo.
LOS_SIETE = {
    "severity",
    "pga_g",
    "node_count",
    "quorum_min_nodes",
    "trigger",
    "event_id",
    "pga_source",
}

#: Los módulos que PRODUCEN el veredicto: el motor y el pase que lo alimenta.
#:
#: `dictamen/builder.py` NO está, y no es un olvido: ése arma el DOCUMENTO y sí
#: importa forense a propósito —el informe enseña los hechos medidos junto al
#: dictamen—. Lo que no puede pasar es que esos hechos entren en la decisión, y
#: la decisión se toma en estos dos ficheros.
PRODUCTORES_DEL_VEREDICTO = ("dictamen/rules.py", "dictamen/service.py")

#: Lo que no puede cruzar esa puerta. `forensics` trae la magnitud y el delta de
#: catálogo; `schemas/catalog` y `queries/catalog`, el catálogo de referencia.
FUENTES_EXTERNAS = (
    "takab_api.forensics",
    "takab_api.schemas.forensics",
    "takab_api.schemas.catalog",
    "takab_api.queries.forensics",
    "takab_api.queries.catalog",
)


def _importa(ruta: Path) -> set[str]:
    """Módulos que ese fichero importa, sea `import x` o `from x import y`."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fuera: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            fuera |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            fuera.add(nodo.module)
            fuera |= {f"{nodo.module}.{a.name}" for a in nodo.names}
    return fuera


def test_la_entrada_del_veredicto_es_EXACTAMENTE_estos_siete_campos() -> None:
    """Por igualdad: añadir un campo pone esto rojo y obliga a decidirlo a la vista.

    No prohíbe el cambio — lo hace visible. Si mañana se decide que la magnitud
    entra, se cambia esta lista Y se explica por qué en la misma revisión, que es
    exactamente lo que hoy podía pasar sin que nadie se enterara.
    """
    campos = {f.name for f in fields(EvalInput)}

    assert campos == LOS_SIETE, (
        "la entrada del veredicto cambió. Si es una medición del propio inmueble, "
        "añádela a `LOS_SIETE`; si viene de un catálogo externo, NO puede entrar: "
        f"el dictamen describe el edificio, no el sismo. Diferencia: {campos ^ LOS_SIETE}"
    )


def test_ningun_productor_del_veredicto_importa_la_cifra_externa() -> None:
    """Un campo no es la única puerta: el motor podría ir a buscarla él mismo."""
    for relativo in PRODUCTORES_DEL_VEREDICTO:
        ruta = _SRC / relativo
        assert ruta.exists(), f"el barrido apunta a un fichero que ya no existe: {relativo}"
        importados = _importa(ruta)
        colados = {m for m in importados if any(m.startswith(f) for f in FUENTES_EXTERNAS)}
        assert not colados, (
            f"`{relativo}` importa una fuente de cifra EXTERNA: {sorted(colados)}. "
            "El dictamen decide sobre el edificio con lo que midió su sensor; una "
            "magnitud publicada para un epicentro a 300 km no puede moverlo."
        )


def test_el_barrido_NO_esta_vacio() -> None:
    """Guarda de no-vacuidad: los dos censos declaran su tamaño en voz alta.

    Sin esto, un `_importa` que devolviera siempre el conjunto vacío —o una ruta
    mal escrita— dejaría el test anterior en verde para siempre sobre un módulo
    que ya no vigila nada. Es el fallo que este repo ya se ha hecho a sí mismo
    dos veces con censos derivados.
    """
    assert len(LOS_SIETE) == 7
    assert len(PRODUCTORES_DEL_VEREDICTO) == 2
    assert len(FUENTES_EXTERNAS) == 5

    # Y el lector de imports funciona: los dos productores importan ALGO.
    for relativo in PRODUCTORES_DEL_VEREDICTO:
        importados = _importa(_SRC / relativo)
        assert importados, f"`{relativo}`: el lector de imports no encontró nada"


def test_el_barrido_CAZA_el_import_que_existe_a_dos_pasos() -> None:
    """Prueba el barrido contra un caso real: `dictamen/builder.py` SÍ importa forense.

    Es la contraprueba que convierte al test de arriba en una comprobación y no en
    una frase optimista: si `_importa` no viera el import de `builder.py` —que
    está ahí, en la línea 40— tampoco vería el día que apareciera en `rules.py`.
    """
    importados = _importa(_SRC / "dictamen/builder.py")
    colados = {m for m in importados if any(m.startswith(f) for f in FUENTES_EXTERNAS)}

    assert colados, (
        "el barrido no ve el import forense de `builder.py`, que existe: entonces "
        "tampoco vería uno nuevo en el motor del veredicto"
    )
