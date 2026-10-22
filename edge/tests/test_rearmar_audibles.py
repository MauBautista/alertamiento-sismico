"""[T-9.74] Re-armar los audibles desde el panel.

Encontrado en el gabinete el 2026-10-21: un SILENCIAR pulsado durante una prueba de
sirena dejó `audible_silenced` en `true` sin alerta viva, y el panel no ofrecía cómo
quitarlo. CERRAR ALERTA sólo aparece con una alerta y SILENCIAR sólo con la sirena
sonando. Mientras tanto el simulacro y la música callaban, y sólo lo decía la fila
de la sirena («SILENCIADA»). Hubo que llamar a `api/reset` con el PIN desde una
terminal.

El re-armado usa la acción `silence` que ya existe en la costura, con
`silenced=False`: es lo que hace el botón físico al alternar. Así el dueño de los
pines (otro proceso en un gabinete D3) no necesita un reinicio para admitirlo. La
bitácora lo distingue por su `action`: un re-armado no puede quedar escrito como
un silencio.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest
from takab_edge.contracts import ActuationCause, ActuatorChannel


def _post(dashboard, path: str, pin: str | None = None) -> int:  # noqa: ANN001
    _host, port = dashboard.address  # bindea 0.0.0.0; se entra por loopback
    headers = {"X-Takab-Pin": pin} if pin is not None else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.fixture
def pinned(supervisor):  # noqa: ANN001, ANN201
    """Panel con PIN, como el de `test_local_api.py` (modo producción de las acciones)."""
    from takab_edge.local_api import LocalDashboard

    dash = LocalDashboard(
        supervisor.gpio,
        supervisor.rules,
        supervisor.health,
        host="127.0.0.1",
        port=0,
        pin="424242",
        dev_mode=False,
    )
    dash.start()
    try:
        yield dash
    finally:
        dash.stop()


def test_rearmar_quita_el_silencio_sin_alerta(supervisor) -> None:  # noqa: ANN001
    supervisor.gpio.silence_audibles(True)
    assert supervisor.gpio.audible_silenced is True
    assert _post(supervisor.local_api, "/api/rearm-audibles") == 200
    assert supervisor.gpio.audible_silenced is False
    assert supervisor.gpio.siren_sounding is False, "sin alerta, re-armar no hace sonar nada"


def test_rearmar_con_la_alerta_viva_la_vuelve_a_hacer_sonar(supervisor) -> None:  # noqa: ANN001
    """Lo mismo que el botón físico: el re-armado vuelve a sonar si la alerta sigue."""
    supervisor.gpio.simulate_sasmex(active=True)
    supervisor.local_api.silence()
    assert supervisor.gpio.siren_sounding is False
    supervisor.local_api.rearm_audibles()
    assert supervisor.gpio.siren_sounding is True
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_la_bitacora_distingue_el_rearmado_del_silencio(supervisor) -> None:  # noqa: ANN001
    supervisor.local_api.silence()
    supervisor.local_api.rearm_audibles()
    filas = [
        (r["action"], r["cause"])
        for r in supervisor.ledger.read_all()
        if r["cause"] == ActuationCause.LAN_SILENCE.value
    ]
    assert filas[-2:] == [
        ("silence", ActuationCause.LAN_SILENCE.value),
        ("rearm_audibles", ActuationCause.LAN_SILENCE.value),
    ]


def test_rearmar_exige_el_pin(pinned, supervisor) -> None:  # noqa: ANN001
    supervisor.gpio.silence_audibles(True)
    assert _post(pinned, "/api/rearm-audibles") == 401
    assert _post(pinned, "/api/rearm-audibles", pin="000000") == 401
    assert supervisor.gpio.audible_silenced is True
    assert _post(pinned, "/api/rearm-audibles", pin="424242") == 200
    assert supervisor.gpio.audible_silenced is False
