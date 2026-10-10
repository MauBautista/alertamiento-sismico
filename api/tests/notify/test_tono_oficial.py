"""[T-9.70 · D-50] El push que AUTORIZA evacuar suena con el sonido oficial del SASMEX.

Mauricio decidió el 2026-10-01 que el oficial suene con SASMEX y con el cuórum de red;
con el umbral local sigue el tono propio. En Android el sonido lo decide el CANAL, que
es inmutable: el oficial va por uno propio, `alerta_oficial_v1`. iOS no cambia (sonido
de notificación ≤ 30 s, y APNs aún no está vivo: GATE-STORE).

La decisión se toma con `target.autoriza`, que todo push de incidente ya persiste, y NO
con el `trigger` literal: el cuórum REAL deja el incidente en `local_threshold` con 3 o
más nodos (`incident/autoridad.py`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from takab_api.notify.push import (
    CANAL_TONO_OFICIAL,
    PUSH_CLASS_CRISIS,
    PUSH_CLASS_OPS,
    build_push_payload,
)
from takab_api.settings import Settings
from tests.notify.test_escalada_avisa_a_todos import _Escena
from tests.notify.test_orchestrator import _Scenario, scenario  # noqa: F401


def _canal(payload: dict) -> str:
    gcm = json.loads(payload["GCM"])
    return gcm["fcmV1Message"]["message"]["android"]["notification"]["channel_id"]


def _sonido_ios(payload: dict) -> object:
    return json.loads(payload["APNS"])["aps"]["sound"]


def _payload(push_class: str, tono_oficial: bool) -> dict:
    return build_push_payload(
        push_class=push_class,
        site_id="s-1",
        incident_id="i-1",
        phase="alert_active",
        tono_oficial=tono_oficial,
    )


def test_la_crisis_con_tono_oficial_va_por_su_canal_y_lo_demas_no_cambia() -> None:
    oficial = _payload(PUSH_CLASS_CRISIS, True)
    propio = _payload(PUSH_CLASS_CRISIS, False)
    assert _canal(oficial) == CANAL_TONO_OFICIAL
    assert _canal(propio) == "seismic_alert_v3"
    assert _sonido_ios(oficial) == _sonido_ios(propio), "iOS sigue con el tono propio"
    assert json.loads(oficial["default"]) == json.loads(propio["default"]), "mismos datos"


def test_el_tono_oficial_solo_existe_para_la_crisis() -> None:
    """Un OPS (pase de lista, informe) nunca suena a SASMEX."""
    assert _canal(_payload(PUSH_CLASS_OPS, True)) == _canal(_payload(PUSH_CLASS_OPS, False))


# --- el orquestador decide por `autoriza` ---------------------------------------


@pytest.fixture
def esc(scenario: _Scenario) -> Iterator[_Escena]:  # noqa: F811
    e = _Escena(scenario)
    scenario.seed_config()
    yield e


def _canales(esc: _Escena) -> list[str]:
    return [_canal(payload) for _dispositivos, payload in esc.push.entregas]


def test_sasmex_despierta_con_el_tono_oficial(esc: _Escena) -> None:
    esc.incidente(trigger="sasmex")
    esc.pasada()
    assert _canales(esc) == [CANAL_TONO_OFICIAL]


def test_el_cuorum_REAL_que_escala_despierta_con_el_tono_oficial(esc: _Escena) -> None:
    """El umbral local despierta a la brigada con el MOVIMIENTO (su canal, su voz); cuando
    la red llega al mínimo, la escalada despierta a todos con el oficial. El incidente
    sigue siendo `local_threshold`: lo que cambia es `node_count`."""
    incidente = esc.incidente(trigger="local_threshold")
    evento = esc.enlazar_evento(incidente, node_count=1)
    esc.pasada()
    assert _canales(esc) == ["building_movement_v2"], "el umbral local sigue con lo suyo"

    esc.conn.execute(
        "UPDATE seismic_events SET meta = %s::jsonb WHERE event_id = %s",
        (json.dumps({"node_count": Settings().quorum_min_nodes}), evento),
    )
    esc.conn.commit()
    esc.pasada(5)
    assert _canales(esc)[-1] == CANAL_TONO_OFICIAL


@pytest.mark.parametrize(
    ("push_class", "target", "oficial"),
    [
        (PUSH_CLASS_CRISIS, {"autoriza": True}, True),
        # El respaldo de `circulo.py` (CRISIS para no callar ante un disparo que no
        # reconoce) no autoriza evacuar: no suena a SASMEX.
        (PUSH_CLASS_CRISIS, {"autoriza": False}, False),
        # Un job anterior a `autoriza` no se adivina (como `:401-404`): tono propio.
        (PUSH_CLASS_CRISIS, {}, False),
        (PUSH_CLASS_OPS, {"autoriza": True}, False),
    ],
)
def test_la_regla_del_tono_oficial(push_class: str, target: dict, oficial: bool) -> None:
    from takab_api.notify.orchestrator import _tono_oficial

    assert _tono_oficial(push_class, target) is oficial
