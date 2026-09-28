"""[D-49 · R4] El worker: la firma humana vale para la evidencia que VIO.

Después de la última firma humana de la cadena (inspector o confirmación) la banda
sólo la sube un reporte de daño cuyo id NO esté en ``basis.danos_vistos`` de esa
firma —la PGA ya la vio y no vuelve a subir nada—, **también cuando encima de la
firma hay una fila sin firmar**. Filas humanas viejas sin ``danos_vistos``: se usa
``created_at`` como antes.
"""

# ruff: noqa: F811  (fixture de pytest importada por nombre)

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from tests.dictamen.test_service import (  # noqa: F401  (fixture por nombre)
    BASE,
    NOW,
    _Scenario,
    scenario,
)
from tests.dictamen.test_worker_v2 import _cadena, _caso, _dano, _firmar_inspector, _run


def _firmar_con_vistos(sc: _Scenario, incident: str, head: str, vistos: list[str]) -> None:
    sc.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
        "supersedes_dictamen_id, signature_kind, band, created_at) "
        "VALUES (%s,%s,'normal_operation',%s::jsonb,%s,%s,'inspector','verde', "
        "clock_timestamp())",
        (sc.tenant, incident, json.dumps({"danos_vistos": vistos}), str(uuid.uuid4()), head),
    )
    sc.conn.commit()


def _reportes(sc: _Scenario, incident: str) -> list[str]:
    return [
        str(r["report_id"])
        for r in sc.conn.execute(
            "SELECT report_id FROM damage_reports WHERE incident_id = %s", (incident,)
        ).fetchall()
    ]


def test_una_fila_SIN_FIRMAR_encima_de_la_firma_humana_no_deja_resubir_la_PGA(
    scenario: _Scenario,
) -> None:
    """PGA roja ⇒ ROJO ⇒ el inspector firma VERDE ⇒ fuga de agua ⇒ AMARILLO sin firmar.
    Antes la pasada siguiente comparaba la evaluación COMPLETA (ROJO por la PGA que el
    inspector ya vio) contra ese AMARILLO e insertaba otro ROJO."""
    ids = _caso(scenario, pga=0.12)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    _dano(scenario, ids, "water_leak")
    assert len(_run(scenario.conn, BASE + timedelta(hours=2))) == 1
    assert _cadena(scenario, ids["incident"])[-1]["band"] == "amarillo"
    for horas in (3, 4, 30):
        assert _run(scenario.conn, BASE + timedelta(hours=horas)) == []
    assert _cadena(scenario, ids["incident"])[-1]["band"] == "amarillo"


def test_un_dano_ROJO_nuevo_encima_de_la_fila_sin_firmar_SI_sube(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.12)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    _dano(scenario, ids, "water_leak")
    _run(scenario.conn, BASE + timedelta(hours=2))
    _dano(scenario, ids, "gas_leak")
    assert len(_run(scenario.conn, BASE + timedelta(hours=3))) == 1
    ultimo = _cadena(scenario, ids["incident"])[-1]
    assert ultimo["band"] == "rojo" and ultimo["signed_by"] is None
    # sólo daños no vistos: ni rastro de la PGA que el inspector ya juzgó
    assert "dano:gas_leak" in ultimo["basis"]["motivos"]
    assert all(m.startswith("dano:") for m in ultimo["basis"]["motivos"])


def test_se_compara_por_ID_un_dano_anterior_que_la_firma_NO_vio_SI_sube(
    scenario: _Scenario,
) -> None:
    """El reporte entró antes de la firma pero no estaba en la lista que el inspector
    vio (la leyó dentro del lock): por ``created_at`` quedaba «visto» para siempre."""
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _dano(scenario, ids, "structural")
    _firmar_con_vistos(scenario, ids["incident"], pre["dictamen_id"], [])
    assert len(_run(scenario.conn, BASE + timedelta(hours=1))) == 1
    ultimo = _cadena(scenario, ids["incident"])[-1]
    assert ultimo["band"] == "rojo" and ultimo["signed_by"] is None


def test_un_dano_en_danos_vistos_no_sube(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _dano(scenario, ids, "structural")
    _firmar_con_vistos(
        scenario, ids["incident"], pre["dictamen_id"], _reportes(scenario, ids["incident"])
    )
    assert _run(scenario.conn, BASE + timedelta(hours=1)) == []
