"""Lo que la API exige de un catálogo tiene que ser lo que el GABINETE exige.

`routers/commands.py::_validar_catalogo` rechaza en la nube lo que
`edge/takab_edge/catalog.py::normalize_catalog` rechazaría en el gabinete. Son dos
listas de claves obligatorias en dos paquetes distintos, y **divergen en la dirección
peor**: si la API se relaja, un catálogo se firma, se publica por IoT —quemando
versión, despertando al gabinete y dejando su renglón PERMANENTE en `audit_log`, que
no se poda (regla de oro 11)— y el gabinete lo tira **entero**, sin escribir un byte.
El fallo aterriza a un salto de su causa y en la máquina equivocada.

El edge no valida con una lista: **subscribe** (`e["m"]`, `r["n"]`…), así que sus
claves obligatorias son literalmente las que aparecen entre corchetes. Este censo las
lee de ahí en vez de repetirlas a mano — *un censo que enumera a mano acaba
divergiendo*. Mismo idioma que `tests/commands/test_sync_mirror.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from takab_api.routers.commands import _EVENTO_OBLIGATORIO, _REFERENCIA_OBLIGATORIA

REPO_ROOT = Path(__file__).resolve().parents[3]
EDGE_CATALOG = REPO_ROOT / "edge/takab_edge/catalog.py"


def _normalize_catalog() -> str:
    fuente = EDGE_CATALOG.read_text(encoding="utf-8")
    m = re.search(r"def normalize_catalog\(.*?\n(?=\n\nclass |\n\ndef )", fuente, re.S)
    assert m is not None, (
        f"no se encontró `normalize_catalog` en {EDGE_CATALOG.relative_to(REPO_ROOT)}: o se "
        "renombró, o este censo dejó de mirar donde debe. Un censo que no encuentra su otra "
        "mitad NO puede pasar en verde."
    )
    return m.group(0)


def _subscripts(cuerpo: str, variable: str) -> set[str]:
    """Claves OBLIGATORIAS del gabinete: subscritas y **no** guardadas por un `.get()`.

    El matiz no es teórico y este censo ya lo cazó: `prof` aparece subscrito
    (`float(e["prof"])`) pero **dentro** de un `if e.get("prof") is not None`, así que
    su ausencia no levanta `KeyError` — es opcional. Contar todo subscript como
    obligatorio haría que la API rechazara catálogos que el gabinete acepta
    perfectamente, que es el error simétrico y también cuesta.
    """
    subscritas = set(re.findall(rf"""\b{variable}\[["']([^"']+)["']\]""", cuerpo))
    guardadas = set(re.findall(rf"""\b{variable}\.get\(["']([^"']+)["']""", cuerpo))
    return subscritas - guardadas


def test_las_claves_obligatorias_del_evento_son_las_del_gabinete() -> None:
    exigidas = _subscripts(_normalize_catalog(), "e")
    assert exigidas, "no se reconoció ni un subscript de evento: el parser se rompió"
    assert set(_EVENTO_OBLIGATORIO) == exigidas, (
        f"la API exige {sorted(_EVENTO_OBLIGATORIO)} y el gabinete {sorted(exigidas)}. "
        "Si la API pide de MENOS, publica catálogos que el gabinete tirará entero; si pide "
        "de MÁS, rechaza catálogos que el gabinete aceptaría. Mover las dos a la vez."
    )


def test_las_claves_obligatorias_de_la_referencia_son_las_del_gabinete() -> None:
    exigidas = _subscripts(_normalize_catalog(), "r")
    assert exigidas, "no se reconoció ni un subscript de referencia: el parser se rompió"
    assert set(_REFERENCIA_OBLIGATORIA) == exigidas, (
        f"la API exige {sorted(_REFERENCIA_OBLIGATORIA)} y el gabinete {sorted(exigidas)}"
    )
