"""T-7.24 · La pasada del ShakeMap está ENGANCHADA al bucle, y en su sitio.

Una pasada perfecta que nadie llama no calcula nada. El enganche se comprueba
sobre el **AST** de `IncidentEngine.run` y no sobre su texto: una guarda textual
se pone verde con sólo nombrar la función en un comentario, que es un fallo que
este repositorio ya midió.

Y se comprueba el ORDEN, que no es cosmético:

* **Después de `_lifecycle_pass`**, que es quien mete al incidente en revisión —
  la huella que esta pasada mira para saber que ya hay algo que mapear. Antes, el
  primer ciclo tras la promoción no lo vería y el mapa se retrasaría una vuelta.
* **Antes de `_consulta_catalogo_pass`**, y esto parece al revés: el epicentro
  que trae USGS es justo lo que le falta a la capa modelada. Pero el orden lo fija
  un invariante que ya está probado en `tests/catalogo/test_enganche_al_worker.py`
  —*la única pasada que habla con un tercero tiene que ir la última*, porque su
  lentitud no puede retrasar a nadie— y esta pasada no habla con ningún tercero.
  El epicentro que llegue entra en el mapa en la vuelta siguiente, por el
  mecanismo normal de refresco: un mapa que no está `completo` se rehace.
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


def test_el_bucle_llama_a_la_pasada_del_shakemap() -> None:
    assert "_shakemap_pass" in _pasadas_del_bucle(), (
        "la pasada de T-7.24 no está enganchada: ningún incidente estrenaría mapa"
    )


def test_va_despues_de_las_fases_y_antes_de_la_que_sale_a_la_red() -> None:
    pasadas = _pasadas_del_bucle()
    assert pasadas.index("_shakemap_pass") > pasadas.index("_lifecycle_pass")
    assert pasadas.index("_shakemap_pass") < pasadas.index("_consulta_catalogo_pass")
    assert pasadas[-1] == "_consulta_catalogo_pass", (
        "la única pasada que habla con un tercero sigue teniendo que ir la última"
    )


def test_el_metodo_delega_en_la_pasada_de_verdad(monkeypatch) -> None:
    """Y no en otra cosa: el método existe, importa perezosamente y llama."""
    llamadas: list[object] = []

    import takab_api.shakemap.servicio as S

    monkeypatch.setattr(S, "run_shakemap_pass", lambda conn, settings: llamadas.append(conn))
    motor = IncidentEngine(lambda: None, Settings())
    motor._shakemap_pass("conexión-de-mentira")  # noqa: SLF001
    assert llamadas == ["conexión-de-mentira"]
