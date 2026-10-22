"""SIMULACRO DE VOCEO del panel: «ORDEN ACEPTADA» sólo si la voz sonó.

Encontrado en la revisión de T-9.74 (2026-10-22): `drill_audio` respondía 200 —y el
panel pintaba «ORDEN ACEPTADA»— aunque el simulacro se omitiera por los audibles
silenciados, una alerta viva o la falta de vigilante. La bitácora, además, anotaba
como éxito lo que el gabinete PREVEÍA (`will_sound`), no lo que pasó. Regla de oro 7:
el panel no puede afirmar un sonido que nadie oyó.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pytest
from takab_edge.audio import AudioNotifier, SimulatedAudioBackend
from takab_edge.audit import ActuationLedger
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController
from takab_edge.local_api import ActionUnavailable, LocalDashboard


def _wav(ruta: Path) -> Path:
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x10\x00" * 22050)
    return ruta


@pytest.fixture
def gabinete(settings, tmp_path):  # noqa: ANN001, ANN201
    """El gabinete real: sirena por el jack, sin voceo, con bitácora propia."""
    cfg = settings.model_copy(
        update={
            "audio_enabled": False,
            "audio_siren_enabled": True,
            "audio_siren_path": str(_wav(tmp_path / "siren.wav")),
            "audio_test_path": str(_wav(tmp_path / "prueba.wav")),
            "audio_simulacro_path": "",
            "cloud_spool_dir": str(tmp_path / "spool"),
        }
    )
    gpio = GpioController(cfg)
    gpio.start()
    voz = SimulatedAudioBackend()
    audio = AudioNotifier(cfg, gpio=gpio, backend=voz, siren_backend=SimulatedAudioBackend())
    audio.start()
    ledger = ActuationLedger(cfg)
    panel = LocalDashboard(gpio, None, None, port=0, dev_mode=True, audio=audio, ledger=ledger)
    panel.start()
    try:
        yield panel, gpio, voz, ledger, audio
    finally:
        panel.stop()
        audio.stop()
        gpio.stop()


def _voceos(ledger: ActuationLedger) -> list[dict]:
    return [f for f in ledger.read_all() if f.get("action") == "drill_audio"]


def test_si_la_voz_suena_la_orden_se_acepta_y_la_fila_dice_exito(gabinete) -> None:  # noqa: ANN001
    panel, _gpio, voz, ledger, _audio = gabinete
    panel.drill_audio()
    assert voz.plays, "la voz no sonó"
    assert [f["success"] for f in _voceos(ledger)] == [True]


@pytest.mark.parametrize(
    ("preparar", "razon"),
    [
        (lambda g: g.silence_audibles(True), "silenciados"),
        (lambda g: g.activate(ActuatorChannel.SIREN), "alerta"),
    ],
)
def test_si_la_voz_NO_suena_la_orden_se_rechaza_con_su_motivo(gabinete, preparar, razon) -> None:  # noqa: ANN001
    panel, gpio, voz, ledger, _audio = gabinete
    preparar(gpio)
    with pytest.raises(ActionUnavailable, match=razon):
        panel.drill_audio()
    assert voz.plays == []
    assert [f["success"] for f in _voceos(ledger)] == [False], "un intento que no sonó es un fallo"


def test_el_panel_recibe_un_409_con_el_motivo_no_un_200(gabinete) -> None:  # noqa: ANN001
    panel, gpio, _voz, _ledger, _audio = gabinete
    gpio.silence_audibles(True)
    _host, port = panel.address
    peticion = urllib.request.Request(f"http://127.0.0.1:{port}/api/drill-audio", method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion, timeout=5)
    assert exc.value.code == 409
    assert "silenciados" in json.loads(exc.value.read())["error"]


def test_play_simulacro_dice_si_sonó(gabinete) -> None:  # noqa: ANN001
    _panel, gpio, _voz, _ledger, audio = gabinete
    assert audio.play_simulacro() is True
    gpio.silence_audibles(True)
    assert audio.play_simulacro() is False


def test_si_se_PREVEIA_sonar_pero_el_reproductor_falla_la_fila_dice_fallo(gabinete) -> None:  # noqa: ANN001
    """La evidencia dice `will_sound: true` (nada lo impide) y aun así aplay revienta:
    la fila registra lo que pasó, no la previsión, y la orden se rechaza."""
    panel, _gpio, voz, ledger, audio = gabinete
    assert audio.simulacro_evidence()["will_sound"] is True

    def _revienta(path: str) -> None:
        raise OSError("aplay no arrancó")

    voz.play = _revienta  # type: ignore[method-assign]
    with pytest.raises(ActionUnavailable, match="NO sonó"):
        panel.drill_audio()
    assert [f["success"] for f in _voceos(ledger)] == [False]
