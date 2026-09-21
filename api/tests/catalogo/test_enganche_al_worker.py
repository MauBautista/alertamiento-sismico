"""T-7.25 · La pasada está ENGANCHADA al bucle del worker, y lo está al final.

Una pasada perfecta que nadie llama no consulta nada. El enganche se comprueba
sobre el **AST** de `IncidentEngine.run` y no sobre su texto: una guarda textual
se pone verde con sólo nombrar la función en un comentario, que es un fallo que
este repositorio ya midió.

Y se comprueba el ORDEN, que no es cosmético:

* **Después de `_lifecycle_pass`**, que es quien mete al incidente en revisión.
  Antes, el primer ciclo tras la promoción no lo vería y la consulta se
  retrasaría una vuelta entera.
* **La última.** Es la única pasada que habla con un tercero: si USGS tarda seis
  segundos, lo que se retrasa es la vuelta siguiente del bucle, nunca un
  dictamen, un cierre ni una correlación ya escritos.
"""

from __future__ import annotations

import ast
import inspect

from takab_api.incident.engine import IncidentEngine
from takab_api.settings import Settings


def _pasadas_del_bucle() -> list[str]:
    """Las `self._*_pass(...)` que `run()` encadena, en su orden de llamada."""
    arbol = ast.parse(inspect.getsource(IncidentEngine.run).lstrip())
    return [
        n.func.attr
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "self"
        and n.func.attr.endswith("_pass")
    ]


def test_el_bucle_llama_a_la_consulta_del_catalogo() -> None:
    assert "_consulta_catalogo_pass" in _pasadas_del_bucle(), (
        "la pasada de T-7.25 no está enganchada: nadie preguntaría nunca"
    )


def test_va_despues_de_las_fases_y_la_ultima() -> None:
    pasadas = _pasadas_del_bucle()
    assert pasadas.index("_consulta_catalogo_pass") > pasadas.index("_lifecycle_pass")
    assert pasadas[-1] == "_consulta_catalogo_pass", (
        "la única pasada que habla con un tercero tiene que ir la última"
    )


def test_el_metodo_delega_en_la_pasada_de_verdad(monkeypatch) -> None:
    """Y no en otra cosa: el método existe, importa perezosamente y llama."""
    llamadas: list[object] = []

    import takab_api.catalogo.consulta as C

    monkeypatch.setattr(
        C, "run_consulta_catalogo_pass", lambda conn, settings: llamadas.append(conn)
    )
    motor = IncidentEngine(lambda: None, Settings())
    motor._consulta_catalogo_pass("conexión-de-mentira")  # noqa: SLF001
    assert llamadas == ["conexión-de-mentira"]
