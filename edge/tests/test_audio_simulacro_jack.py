"""[T-9.71 · D-41] El simulacro hablado suena POR EL JACK, sin voceo.

Mauricio decidió el 2026-10-10: un simulacro reproduce por el jack el simulacro hablado
que aprobó al escucharlo, sin exigir la grabación de «sismo» del voceo (que no existe).
La propia grabación dice «Esto es un simulacro», así que no se confunde con una alerta.

Lo que NO puede pasar nunca: que el jack diga «Esto es un simulacro» durante una alerta
real. El vigilante del jack corta la voz del simulacro ante cualquier alerta, prueba de
sirena, silencio o estado ilegible, y una actuación del cuórum aborta el simulacro.
"""

from __future__ import annotations

import logging
import wave
from pathlib import Path

import pytest
from takab_edge.audio import AudioNotifier, SimulatedAudioBackend, catalog
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController

HABLADO = catalog.resolve("takab-simulacro-v2")


def _wav(ruta: Path, segundos: float = 1.0, rate: int = 22050) -> Path:
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(segundos * rate))
    return ruta


@pytest.fixture
def jack(settings, tmp_path: Path):  # noqa: ANN001 — fixture del conftest
    """El gabinete real: sirena por el jack encendida, voceo APAGADO, sin grabaciones."""
    return settings.model_copy(
        update={
            "audio_enabled": False,
            "audio_siren_enabled": True,
            "audio_siren_path": str(_wav(tmp_path / "siren.wav")),
            "audio_test_path": str(_wav(tmp_path / "prueba.wav")),
            "audio_simulacro_path": "",
            "audio_sismo_path": "",
        }
    )


@pytest.fixture
def gpio(jack):  # noqa: ANN001
    controller = GpioController(jack)
    controller.start()
    yield controller
    controller.stop()


def _notifier(cfg, gpio):  # noqa: ANN001
    voz = SimulatedAudioBackend()
    sirena = SimulatedAudioBackend()
    notifier = AudioNotifier(cfg, gpio=gpio, backend=voz, siren_backend=sirena)
    notifier.start()
    return notifier, voz, sirena


# --- qué suena y cuándo ------------------------------------------------------------


def test_por_defecto_el_simulacro_es_el_hablado_aprobado(jack, gpio) -> None:  # noqa: ANN001
    notifier, _voz, _sirena = _notifier(jack, gpio)
    try:
        assert HABLADO is not None
        assert notifier.simulacro_path == str(HABLADO)
        ev = notifier.simulacro_evidence()
        assert ev["asset_id"] == "takab-simulacro-v2"
        assert ev["will_sound"] is True, "con el jack encendido suena, aunque no haya voceo"
    finally:
        notifier.stop()


def test_con_el_jack_y_sin_voceo_el_simulacro_SUENA(jack, gpio) -> None:  # noqa: ANN001
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()
        assert voz.playing == str(HABLADO)
    finally:
        notifier.stop()


def test_el_voceo_de_SISMO_sigue_exigiendo_el_voceo(jack, gpio) -> None:  # noqa: ANN001
    """Lo decidido es el simulacro: una alerta real no gana voz por esto."""
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_sismo()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_sin_jack_ni_voceo_no_suena_y_la_evidencia_dice_por_que(jack, gpio) -> None:  # noqa: ANN001
    mudo = jack.model_copy(update={"audio_siren_enabled": False})
    notifier, voz, _sirena = _notifier(mudo, gpio)
    try:
        notifier.play_simulacro()
        assert voz.playing is None
        ev = notifier.simulacro_evidence()
        assert ev["will_sound"] is False
        assert "jack" in ev["reason"]
    finally:
        notifier.stop()


def test_con_los_audibles_silenciados_no_arranca(jack, gpio) -> None:  # noqa: ANN001
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        gpio.silence_audibles(True)
        notifier.play_simulacro()
        assert voz.playing is None
    finally:
        notifier.stop()


# --- lo real gana: el jack jamás dice «simulacro» con una alerta viva ----------------


def test_una_alerta_a_mitad_del_simulacro_CALLA_la_voz(jack, gpio) -> None:  # noqa: ANN001
    """El cuórum (o el umbral con actuación) pide sirena sin pasar por el drill: el
    vigilante corta la voz en la misma vuelta en que arranca la sirena."""
    notifier, voz, sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()
        gpio.activate(ActuatorChannel.SIREN)
        notifier._tick()
        assert voz.playing is None
        assert sirena.playing == jack.audio_siren_path
    finally:
        notifier.stop()


def test_un_SASMEX_a_mitad_del_simulacro_CALLA_la_voz(jack, gpio) -> None:  # noqa: ANN001
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()
        gpio.simulate_sasmex(active=True)
        notifier._tick()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_una_prueba_de_sirena_a_mitad_del_simulacro_CALLA_la_voz(jack, gpio) -> None:  # noqa: ANN001
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()
        gpio.run_siren_test(duration_s=5.0)
        notifier._tick()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_el_silencio_CALLA_la_voz_aunque_no_haya_voceo(jack, gpio) -> None:  # noqa: ANN001
    """El voceo se suscribe al silencio al arrancar; con el voceo apagado nadie lo
    hacía, y el botón de silencio no callaba el simulacro."""
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()
        gpio.silence_audibles(True)
        notifier._tick()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_sin_poder_leer_el_gabinete_se_CALLA(jack, gpio, monkeypatch) -> None:  # noqa: ANN001
    """Fail-cerrado: sin saber si hay una alerta, el jack no dice «simulacro»."""
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        notifier.play_simulacro()

        class _Roto:
            def snapshot(self):  # noqa: ANN202
                raise OSError("pinlink caído")

        monkeypatch.setattr(notifier, "_link", _Roto())
        notifier._tick()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_el_vigilante_NO_corta_la_voz_de_SISMO(jack, gpio, tmp_path) -> None:  # noqa: ANN001
    """Con el voceo completo, la voz de sismo suena DURANTE la alerta: el corte es
    sólo para la del simulacro."""
    completo = jack.model_copy(
        update={
            "audio_enabled": True,
            "audio_sismo_path": str(_wav(tmp_path / "sismo.wav")),
        }
    )
    notifier, voz, _sirena = _notifier(completo, gpio)
    try:
        gpio.activate(ActuatorChannel.SIREN)
        notifier.play_sismo()
        notifier._tick()
        assert voz.playing == completo.audio_sismo_path
    finally:
        notifier.stop()


def test_con_voceo_y_SIN_jack_el_vigilante_tambien_vigila(jack, gpio, tmp_path) -> None:  # noqa: ANN001
    """Sin sirena por el jack el vigilante no arrancaba, y nadie cortaba la voz del
    simulacro ante una alerta. Ahora arranca si hay voz o sirena que vigilar."""
    solo_voz = jack.model_copy(
        update={
            "audio_enabled": True,
            "audio_siren_enabled": False,
            "audio_sismo_path": str(_wav(tmp_path / "sismo.wav")),
        }
    )
    notifier, voz, _sirena = _notifier(solo_voz, gpio)
    try:
        assert notifier._siren_thread is not None and notifier._siren_thread.is_alive()
        notifier.play_simulacro()
        gpio.activate(ActuatorChannel.SIREN)
        notifier._tick()
        assert voz.playing is None
    finally:
        notifier.stop()


# --- la revisión adversarial (2026-10-10) -------------------------------------------


def test_con_una_alerta_viva_el_simulacro_NI_ARRANCA(jack, gpio) -> None:  # noqa: ANN001
    """El botón del panel (con PIN) llama a play_simulacro sin pasar por el drill: no
    puede decir «simulacro» ni una vuelta del vigilante con una alerta viva."""
    notifier, voz, _sirena = _notifier(jack, gpio)
    try:
        gpio.activate(ActuatorChannel.SIREN)
        notifier.play_simulacro()
        assert voz.plays == []
    finally:
        notifier.stop()


def test_sin_el_vigilante_el_simulacro_no_suena_y_se_declara(jack, gpio) -> None:  # noqa: ANN001
    """La única guarda del jack es el vigilante: un módulo que no arrancó (p. ej. con la
    ruta de la sirena rota) no puede sonar un simulacro que nadie callaría."""
    voz = SimulatedAudioBackend()
    notifier = AudioNotifier(jack, gpio=gpio, backend=voz, siren_backend=SimulatedAudioBackend())
    notifier.play_simulacro()  # sin start(): no hay vigilante
    assert voz.plays == []
    ev = notifier.simulacro_evidence()
    assert ev["will_sound"] is False
    assert "vigilante" in ev["reason"]


@pytest.mark.parametrize(
    ("preparar", "razon"),
    [
        (lambda g: g.silence_audibles(True), "silenciados"),
        (lambda g: g.activate(ActuatorChannel.SIREN), "alerta"),
    ],
)
def test_la_evidencia_no_promete_lo_que_no_va_a_sonar(jack, gpio, preparar, razon) -> None:  # noqa: ANN001
    """El acuse a la nube y el PDF imprimían el asset y su huella como lo que sonó."""
    notifier, _voz, _sirena = _notifier(jack, gpio)
    try:
        preparar(gpio)
        ev = notifier.simulacro_evidence()
        assert ev["will_sound"] is False
        assert razon in ev["reason"]
    finally:
        notifier.stop()


def test_parar_el_simulacro_no_calla_la_voz_de_SISMO(jack, gpio, tmp_path) -> None:  # noqa: ANN001
    completo = jack.model_copy(
        update={"audio_enabled": True, "audio_sismo_path": str(_wav(tmp_path / "sismo.wav"))}
    )
    notifier, voz, _sirena = _notifier(completo, gpio)
    try:
        notifier.play_sismo()
        notifier.stop_simulacro()
        assert voz.playing == completo.audio_sismo_path
        notifier.play_simulacro()
        notifier.stop_simulacro()
        assert voz.playing is None
    finally:
        notifier.stop()


def test_la_voz_se_corta_ANTES_de_que_arranque_la_sirena(jack, gpio) -> None:  # noqa: ANN001
    """En la vuelta en que llega la alerta, el jack no puede llevar las dos a la vez."""
    voz = SimulatedAudioBackend()

    class _Sirena(SimulatedAudioBackend):
        def play(self, path: str) -> None:
            self.voz_al_arrancar = voz.playing
            super().play(path)

    sirena = _Sirena()
    notifier = AudioNotifier(jack, gpio=gpio, backend=voz, siren_backend=sirena)
    notifier.start()
    try:
        notifier.play_simulacro()
        gpio.activate(ActuatorChannel.SIREN)
        notifier._tick()
        assert sirena.playing == jack.audio_siren_path
        assert sirena.voz_al_arrancar is None
    finally:
        notifier.stop()


def test_un_simulacro_que_arranca_mientras_el_vigilante_mira_no_se_pierde(jack, gpio) -> None:  # noqa: ANN001
    """Carrera: el vigilante lee «sin voz» justo cuando otro hilo arranca un simulacro
    nuevo. Si después borrara la marca, ese simulacro quedaría sin vigilar."""
    notifier = None

    class _Voz(SimulatedAudioBackend):
        def __init__(self) -> None:
            super().__init__()
            self.interferir = False

        @property
        def playing(self):  # noqa: ANN202
            if self.interferir:
                self.interferir = False
                notifier.play_simulacro()  # otro hilo, entre la lectura y la decisión
                return None
            return self._playing

    voz = _Voz()
    notifier = AudioNotifier(jack, gpio=gpio, backend=voz, siren_backend=SimulatedAudioBackend())
    notifier.start()
    try:
        notifier.play_simulacro()
        voz.interferir = True
        notifier._tick()
        assert notifier._voz_actual == "simulacro", "el simulacro nuevo quedó sin vigilar"
        gpio.activate(ActuatorChannel.SIREN)
        notifier._tick()
        assert voz._playing is None
    finally:
        notifier.stop()


def test_un_corte_que_falla_no_inunda_el_registro(jack, gpio, caplog) -> None:  # noqa: ANN001
    """Regla de oro 10: si `stop()` falla, se reintenta cada vuelta pero sin una traza
    por vuelta (20 por segundo durante toda la alerta)."""

    class _VozTerca(SimulatedAudioBackend):
        def stop(self) -> None:
            raise OSError("aplay no muere")

    voz = _VozTerca()
    notifier = AudioNotifier(jack, gpio=gpio, backend=voz, siren_backend=SimulatedAudioBackend())
    notifier.start()
    try:
        voz.play(str(HABLADO))
        notifier._voz_actual = "simulacro"
        gpio.activate(ActuatorChannel.SIREN)
        with caplog.at_level(logging.WARNING, logger="takab_edge.audio"):
            for _ in range(20):
                notifier._tick()
        trazas = [r for r in caplog.records if "no se pudo callar" in r.getMessage()]
        assert 1 <= len(trazas) <= 2
    finally:
        notifier.stop()
