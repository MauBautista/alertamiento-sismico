"""[T-7.21] CENSO · todo papel que sale del sistema lleva el membrete.

El criterio de la ficha dice: «toda subclase de `FPDF` en `api/src` deriva de
`MembretePDF`». Se comprueba **derivándolo**, no enumerando: una lista escrita a
mano queda desactualizada el día que alguien añade un documento, que es
exactamente el día en que este censo tendría que saltar.

## Por qué hacen falta DOS barridos y ninguno basta solo

**(a) Por herencia, en tiempo de ejecución.** Se importan todos los módulos de
`takab_api` y se recorre `FPDF.__subclasses__()` transitivamente. Caza una
subclase aunque herede de forma indirecta o se declare en un módulo que el AST no
sabría relacionar.

**(b) Por AST, buscando la INSTANCIACIÓN suelta.** `pdf = FPDF()` no es una
subclase y se escaparía del barrido (a) sin que nada lo notara: un papel sin
membrete, sin folio y sin la franja «EVIDENCIA INMUTABLE», con el censo en verde.
Es el hueco que convierte un censo en una ceremonia.

## La única exención se DERIVA

`MembretePDF` no puede derivar de sí mismo. Eso se expresa comparando la clase
(`cls is MembretePDF`), no escribiendo su nombre en una lista de exentos: una
lista de exentos crece y acaba tapando justo lo que el censo vigila.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

from fpdf import FPDF

import takab_api
from takab_api.documentos.membrete import MembretePDF

SRC = Path(takab_api.__file__).resolve().parent


def _todos_los_modulos() -> list[str]:
    """Importa todo `takab_api` para que las subclases existan de verdad.

    Sin esto el barrido por herencia sólo vería lo que otro test haya importado
    antes, y el resultado dependería del orden de la suite.
    """
    nombres = []
    for info in pkgutil.walk_packages([str(SRC)], prefix="takab_api."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 — un módulo que no importa lo caza otra suite
            continue
        nombres.append(info.name)
    return nombres


def _descendientes(clase: type) -> set[type]:
    salida: set[type] = set()
    pendientes = list(clase.__subclasses__())
    while pendientes:
        c = pendientes.pop()
        if c in salida:
            continue
        salida.add(c)
        pendientes.extend(c.__subclasses__())
    return salida


def test_toda_subclase_de_FPDF_deriva_del_MEMBRETE() -> None:
    """El criterio de la ficha, derivado por herencia real."""
    modulos = _todos_los_modulos()
    assert len(modulos) > 50, f"el barrido sólo importó {len(modulos)} módulos: no mide nada"

    huerfanas = sorted(
        c.__module__ + "." + c.__qualname__
        for c in _descendientes(FPDF)
        if c is not MembretePDF
        and not issubclass(c, MembretePDF)
        and c.__module__.startswith("takab_api.")
    )
    assert not huerfanas, (
        "hay documentos sin membrete —sin folio, sin paginación y sin la franja "
        f"EVIDENCIA INMUTABLE—: {huerfanas}"
    )


def test_el_barrido_por_herencia_NO_esta_ciego() -> None:
    """Guarda de no-vacuidad: si `TakabPDF` dejara de verse, todo pasaría solo."""
    vistas = {c.__qualname__ for c in _descendientes(FPDF)}
    assert "TakabPDF" in vistas, f"el barrido no ve ni el dictamen; vio {sorted(vistas)}"
    assert "MembretePDF" in vistas


def test_NADIE_instancia_FPDF_a_pelo() -> None:
    """La otra mitad: `FPDF(...)` suelto no es una subclase y se escaparía.

    Un módulo nuevo que haga `pdf = FPDF()` produce un papel sin membrete y el
    barrido por herencia lo daría por bueno.
    """
    culpables: list[str] = []
    for ruta in sorted(SRC.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = nodo.func.id if isinstance(nodo.func, ast.Name) else None
            if nombre is None and isinstance(nodo.func, ast.Attribute):
                nombre = nodo.func.attr
            if nombre == "FPDF":
                culpables.append(f"{ruta.relative_to(SRC)}:{nodo.lineno}")
    assert not culpables, "se instancia `FPDF` directamente, sin membrete: " + ", ".join(culpables)


def test_el_barrido_AST_lee_ficheros_de_verdad() -> None:
    """Guarda de no-vacuidad del segundo barrido."""
    ficheros = list(SRC.rglob("*.py"))
    assert len(ficheros) > 100, f"sólo {len(ficheros)} ficheros bajo {SRC}"
    assert (SRC / "documentos" / "membrete.py") in ficheros
