"""T-2.42 · Los tres contratos que impiden que la prosa toque el veredicto.

La regla de oro 1 dice que la IA "solo asesora/prioriza/filtra, jamás veta ni dispara".
Escribirlo en un README no lo hace cierto. Estos tres tests lo hacen cierto: rompen el
build antes de que un cambio pueda llegar a un dictamen.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

from takab_api.dictamen.pdf import render
from takab_api.narrative.base import Narrative

_SRC = Path(__file__).resolve().parents[2] / "src" / "takab_api" / "narrative"

#: Nada de lo que un proveedor devuelve puede llamarse así.
_PROHIBIDO = re.compile(r"status|verdict|dictamen|priority|severity", re.IGNORECASE)


def test_narrative_no_tiene_donde_poner_un_veredicto() -> None:
    """(a) Un proveedor no puede emitir un veredicto porque no hay campo para él.

    Es la defensa estructural: no depende de que nadie recuerde una regla.
    """
    campos = [f.name for f in dataclasses.fields(Narrative)]
    infractores = [c for c in campos if _PROHIBIDO.search(c)]
    assert not infractores, f"Narrative no puede llevar {infractores}: sería un veredicto"


def test_la_capa_narrativa_no_puede_invocar_al_motor_de_reglas() -> None:
    """(b) `narrative/` no importa `dictamen.rules` ni `dictamen.service`.

    Sin el import no puede ni llamar al que dictamina, ni escribir un dictamen. Se
    permite `dictamen.model`, que es la estructura de datos pura del documento.
    """
    prohibidos = ("takab_api.dictamen.rules", "takab_api.dictamen.service")
    fugas: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(p) for p in prohibidos):
                    fugas.append(f"{path.name}: from {node.module}")
            elif isinstance(node, ast.Import):
                fugas += [
                    f"{path.name}: import {a.name}"
                    for a in node.names
                    if any(a.name.startswith(p) for p in prohibidos)
                ]
    assert not fugas, f"la capa narrativa no puede tocar el motor del dictamen: {fugas}"


def test_el_veredicto_del_pdf_no_depende_de_la_prosa() -> None:
    """(c) Con prosa y sin prosa, el documento afirma exactamente el mismo veredicto.

    Se comprueba sobre el modelo (que es lo que el render imprime) y se verifica que
    ambos PDF se generan: la narrativa cambia el documento, nunca el dictamen.
    """
    from tests.dictamen.test_pdf import model  # noqa: PLC0415 - fixture del render

    sin = model()
    con = model(
        narrative=[(t, f"prosa {t}") for t in ("Resumen ejecutivo", "Qué pasó")],
        narrative_provider="openrouter",
    )
    assert con.verdict_status == sin.verdict_status
    assert con.verdict_label == sin.verdict_label
    assert con.rule_set_version == sin.rule_set_version
    assert render(sin).startswith(b"%PDF")
    assert render(con).startswith(b"%PDF")
