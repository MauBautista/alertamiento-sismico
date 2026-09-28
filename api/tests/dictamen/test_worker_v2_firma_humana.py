"""[F3·r3 · D-43] El worker frente a una firma HUMANA y a una escalada pendiente.

* **La firma humana no se deshace sola.** Medido en la ronda 2: el inspector firma
  HABITABLE tras inspeccionar y la pasada siguiente vuelve a insertar el ROJO (o el
  AMARILLO) sin firmar encima de su firma, y así cada vez que firme durante 72 h.
  Con la cabeza firmada por una persona (``inspector`` o ``confirmation``) el worker
  sólo sube por daños que esa persona NO vio: los creados DESPUÉS de su firma (y, en
  una confirmación, cualquier daño ROJO: la API no deja confirmar con uno).
* **Una escalada pendiente frena el VERDE del sistema.** La brigada que escala al
  inspector no puede ver cómo el sistema firma VERDE a los 300 s sin que nadie
  intervenga.
"""

# ruff: noqa: F811  (fixture de pytest importada por nombre)

from __future__ import annotations

import json
from datetime import timedelta

from tests.dictamen.test_service import (  # noqa: F401  (fixture por nombre)
    BASE,
    NOW,
    _Scenario,
    scenario,
)
from tests.dictamen.test_worker_v2 import (
    GRACIA,
    _cadena,
    _caso,
    _dano,
    _firmar_inspector,
    _run,
)


def _solicitar_dictamen(sc: _Scenario, ids: dict) -> None:
    sc.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload, ts) "
        "VALUES (%s,%s,'dictamen_request','user:brigada',%s::jsonb, clock_timestamp())",
        (ids["incident"], sc.tenant, json.dumps({"note": None})),
    )
    sc.conn.commit()


# ---------------------------------------------------- la firma humana manda


def test_el_inspector_firma_HABITABLE_con_PGA_roja_y_el_worker_NO_la_resube(
    scenario: _Scenario,
) -> None:
    """PGA ≥ 0,10 g ⇒ ROJO preliminar. El inspector inspecciona y firma VERDE: la PGA
    ya la vio él. Ninguna pasada posterior (72 h) puede volver a subirlo por la PGA.
    Con un daño amarillo reportado ANTES de la firma el incidente sigue siendo
    candidato en cada pasada: es el caso en el que la evaluación completa resubía."""
    ids = _caso(scenario, pga=0.12)
    _run(scenario.conn, NOW)
    _dano(scenario, ids, "water_leak")
    [pre] = _cadena(scenario, ids["incident"])
    assert pre["band"] == "rojo"
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    for horas in (1, 2, 30):
        assert _run(scenario.conn, BASE + timedelta(hours=horas)) == []
    cadena = _cadena(scenario, ids["incident"])
    assert [(f["band"], f["signature_kind"]) for f in cadena] == [
        ("rojo", None),
        ("verde", "inspector"),
    ]


def test_un_dano_VISTO_por_el_inspector_no_se_resube_sobre_su_firma(
    scenario: _Scenario,
) -> None:
    """La cadena medida en la ronda 2: VERDE → daño estructural → ROJO → el inspector
    firma VERDE → el worker insertaba OTRO ROJO. Ahora no."""
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _dano(scenario, ids, "structural")
    _run(scenario.conn, BASE + timedelta(minutes=30))
    cadena = _cadena(scenario, ids["incident"])
    assert cadena[-1]["band"] == "rojo" and cadena[-1]["signed_by"] is None
    _firmar_inspector(
        scenario, ids["incident"], cadena[-1]["dictamen_id"], "normal_operation", "verde"
    )
    assert _run(scenario.conn, BASE + timedelta(hours=1)) == []
    assert _run(scenario.conn, BASE + timedelta(hours=2)) == []
    assert _cadena(scenario, ids["incident"])[-1]["signature_kind"] == "inspector"


def test_un_dano_ESTRUCTURAL_posterior_a_la_firma_del_inspector_SI_sube(
    scenario: _Scenario,
) -> None:
    ids = _caso(scenario, pga=0.12)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    assert _run(scenario.conn, BASE + timedelta(hours=1)) == []
    _dano(scenario, ids, "structural")
    assert len(_run(scenario.conn, BASE + timedelta(hours=2))) == 1
    ultimo = _cadena(scenario, ids["incident"])[-1]
    assert ultimo["band"] == "rojo" and ultimo["status"] == "no_inhabit_inspect"
    assert ultimo["signed_by"] is None
    assert "dano:structural" in ultimo["basis"]["motivos"]
    # idempotente: la misma evidencia no sube dos veces
    assert _run(scenario.conn, BASE + timedelta(hours=3)) == []


def test_un_dano_NO_estructural_posterior_a_la_firma_sube_a_AMARILLO_no_a_ROJO(
    scenario: _Scenario,
) -> None:
    """La PGA roja ya la vio el inspector: lo nuevo es sólo un daño amarillo."""
    ids = _caso(scenario, pga=0.12)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    _dano(scenario, ids, "water_leak")
    assert len(_run(scenario.conn, BASE + timedelta(hours=2))) == 1
    ultimo = _cadena(scenario, ids["incident"])[-1]
    assert ultimo["band"] == "amarillo" and ultimo["status"] == "inhabit_monitor"
    assert ultimo["basis"]["band"] == "amarillo"


# ---------------------------------------------------- la escalada pendiente


def test_con_una_ESCALADA_pendiente_el_sistema_NO_firma_el_VERDE(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _solicitar_dictamen(scenario, ids)
    assert _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 1)) == []
    assert _run(scenario.conn, BASE + timedelta(hours=1)) == []
    cadena = _cadena(scenario, ids["incident"])
    assert all(f["signature_kind"] != "system" for f in cadena)


def test_la_escalada_la_atiende_el_INSPECTOR_y_luego_el_sistema_ya_no_hace_falta(
    scenario: _Scenario,
) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _solicitar_dictamen(scenario, ids)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    assert _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 1)) == []
    assert _cadena(scenario, ids["incident"])[-1]["signature_kind"] == "inspector"
