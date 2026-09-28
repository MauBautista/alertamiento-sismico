"""[T-9.33 · D-43] El worker pide confirmación de cada AMARILLO sin firmar, UNA vez.

La acción ``dictamen_confirm_requested`` es el ancla del push DICTAMEN_CONFIRM
(``tests/notify/test_aviso_confirmar_dictamen.py``). Aquí se mide el productor: sale
con un AMARILLO sin firmar, no con un VERDE ni con un ROJO, y una pasada repetida no
la duplica.
"""

# ruff: noqa: F811  (fixture de pytest importada por nombre)

from __future__ import annotations

from datetime import timedelta

from tests.dictamen.test_service import NOW, _Scenario, scenario  # noqa: F401
from tests.dictamen.test_worker_v2 import _cadena, _caso, _run


def _peticiones(sc: _Scenario, incident: str) -> list[dict]:
    return sc.conn.execute(
        "SELECT actor, payload FROM incident_actions "
        "WHERE incident_id = %s AND kind = 'dictamen_confirm_requested'",
        (incident,),
    ).fetchall()


def test_un_AMARILLO_sin_firmar_pide_confirmacion_una_vez(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.07)
    _run(scenario.conn, NOW)
    [fila] = _cadena(scenario, ids["incident"])
    assert fila["band"] == "amarillo" and fila["signed_by"] is None

    [peticion] = _peticiones(scenario, ids["incident"])
    assert peticion["actor"] == "system:dictamen"
    assert peticion["payload"]["dictamen_id"] == str(fila["dictamen_id"])
    assert peticion["payload"]["band"] == "amarillo"

    _run(scenario.conn, NOW + timedelta(seconds=30))
    assert len(_peticiones(scenario, ids["incident"])) == 1


def test_un_VERDE_o_un_ROJO_no_piden_confirmacion(scenario: _Scenario) -> None:
    verde = _caso(scenario, pga=0.01)
    rojo = _caso(scenario, pga=0.3)
    _run(scenario.conn, NOW)

    assert _cadena(scenario, verde["incident"])[0]["band"] == "verde"
    assert _cadena(scenario, rojo["incident"])[0]["band"] == "rojo"
    assert _peticiones(scenario, verde["incident"]) == []
    assert _peticiones(scenario, rojo["incident"]) == []
