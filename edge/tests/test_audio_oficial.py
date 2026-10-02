"""[T-9.70 · D-50] El sonido OFICIAL del SASMEX por el jack del gabinete.

Suena con SASMEX (el enclave del WR-1) y con el cuórum de red; con el umbral local, la
prueba de sirena y cualquier otro motivo sigue el tono propio. El fichero viaja FUERA
de git (se inyecta al publicar la release), así que su ausencia es un estado normal: el
gabinete suena el tono propio y lo DECLARA, nunca calla una alerta por no tenerlo.
"""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest
from takab_edge.audio import AudioNotifier, SimulatedAudioBackend, catalog
from takab_edge.contracts import ActuatorChannel, SirenReason
from takab_edge.gpio import GpioController


def _wav(ruta: Path, segundos: float = 2.0, rate: int = 22050) -> Path:
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(segundos * rate))
    return ruta


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def oficial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un WAV válido con la huella que el catálogo da por auditada."""
    ruta = _wav(tmp_path / "sasmex_oficial.wav")
    monkeypatch.setattr(catalog, "OFICIAL_SHA256", _huella(ruta))
    return ruta


@pytest.fixture
def cfg(settings, tmp_path: Path):  # noqa: ANN001 — fixture del conftest
    return settings.model_copy(
        update={
            "audio_siren_enabled": True,
            "audio_siren_path": str(_wav(tmp_path / "siren.wav", 1.0, 48000)),
            "audio_test_path": str(_wav(tmp_path / "prueba.wav", 1.0, 48000)),
        }
    )


@pytest.fixture
def gpio(cfg):  # noqa: ANN001
    controller = GpioController(cfg)
    controller.start()
    yield controller
    controller.stop()


def _notifier(cfg, gpio, reloj=None):  # noqa: ANN001
    siren = SimulatedAudioBackend()
    kwargs = {"reloj": reloj} if reloj is not None else {}
    notifier = AudioNotifier(
        cfg, gpio=gpio, backend=SimulatedAudioBackend(), siren_backend=siren, **kwargs
    )
    notifier.start()
    return notifier, siren


def _con_oficial(cfg, oficial: Path):  # noqa: ANN001
    return cfg.model_copy(update={"audio_oficial_path": str(oficial)})


# --- por qué suena --------------------------------------------------------------


def test_sasmex_suena_con_el_oficial(cfg, gpio, oficial) -> None:  # noqa: ANN001
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio)
    try:
        gpio.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)
    finally:
        notifier.stop()


def test_el_cuorum_suena_con_el_oficial(cfg, gpio, oficial) -> None:  # noqa: ANN001
    reloj = _Reloj()
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: reloj.t)  # el despachador marcó AHORA
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)
    finally:
        notifier.stop()


def test_el_umbral_local_sigue_con_el_tono_propio(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """La misma demanda de sirena por regla, sin cuórum detrás: es el umbral local con
    `instrumental_actuation`. La decisión lo deja con el tono propio."""
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio)
    try:
        notifier.set_quorum_source(lambda: None)
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path
    finally:
        notifier.stop()


def test_una_marca_de_cuorum_de_OTRO_episodio_no_cuenta(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """El despachador sólo olvida el cuórum con CERRAR ALERTA o un DEACTIVATE. Una marca
    de hace una hora no puede hacer sonar el oficial en una alerta local de ahora."""
    reloj = _Reloj()
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: reloj.t - 3600)
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path
    finally:
        notifier.stop()


def test_una_alerta_local_que_ESCALA_a_cuorum_conmuta_al_oficial(cfg, gpio, oficial) -> None:  # noqa: ANN001
    reloj = _Reloj()
    marca: list[float | None] = [None]
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: marca[0])
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path

        reloj.t += 20  # 20 s después confirma la red
        marca[0] = reloj.t
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)
        assert siren.stops >= 1, "se para antes de conmutar: dos WAV a la vez se mezclan"
    finally:
        notifier.stop()


def test_en_el_orden_REAL_la_marca_es_anterior_al_episodio(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """El despachador marca ANTES de energizar y el vigilante abre el episodio DESPUÉS:
    la marca siempre es unos milisegundos más vieja. Con un margen de cero, todo cuórum
    sonaría con el tono propio (revisión adversarial de T-9.70)."""
    reloj = _Reloj()
    marca = reloj.t
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: marca)
        gpio.activate(ActuatorChannel.SIREN)
        reloj.t += 0.05  # el relé tarda; el vigilante concilia después
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)
    finally:
        notifier.stop()


def test_silenciar_y_rearmar_un_cuorum_vivo_no_lo_degrada_al_propio(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """El silencio calla el relé pero NO suelta el enclave: el episodio es el mismo y al
    re-armar sigue siendo el cuórum. Antes el episodio se cerraba con el sonido y el
    re-armado abría uno nuevo, más joven que la marca: sonaba el propio."""
    reloj = _Reloj()
    marca = reloj.t
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: marca)
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)

        reloj.t += 30
        gpio.silence_audibles(True)
        notifier._reconcile_siren()
        assert siren.playing is None

        reloj.t += 60
        gpio.silence_audibles(False)
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)
    finally:
        notifier.stop()


def test_cerrar_la_alerta_cierra_el_episodio(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """Una marca que nadie borró (p. ej. el despachador reiniciado no la conoce, o un
    CERRAR ALERTA que no la alcanzó) no cuenta en la alerta LOCAL siguiente: el
    episodio se cierra cuando se suelta el enclave."""
    reloj = _Reloj()
    marca = reloj.t
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: marca)
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == str(oficial)

        reloj.t += 120
        gpio.reset()
        notifier._reconcile_siren()
        assert siren.playing is None

        reloj.t += 10
        gpio.activate(ActuatorChannel.SIREN)  # el umbral local, ya sin cuórum
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path
    finally:
        notifier.stop()


def test_la_prueba_de_sirena_jamas_suena_el_oficial(cfg, gpio, oficial) -> None:  # noqa: ANN001
    reloj = _Reloj()
    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio, reloj)
    try:
        notifier.set_quorum_source(lambda: reloj.t)
        gpio.run_siren_test(duration_s=5.0)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_test_path
        assert notifier.asset_for(SirenReason.TEST, oficial=True) == cfg.audio_test_path
    finally:
        notifier.stop()


def test_si_la_fuente_del_cuorum_falla_suena_el_tono_propio(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """Advisory: un fallo al preguntar por el cuórum jamás calla la alerta."""

    def rota() -> float:
        raise RuntimeError("despachador caído")

    notifier, siren = _notifier(_con_oficial(cfg, oficial), gpio)
    try:
        notifier.set_quorum_source(rota)
        gpio.activate(ActuatorChannel.SIREN)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path
    finally:
        notifier.stop()


# --- qué fichero ------------------------------------------------------------------


def test_sin_el_oficial_SASMEX_suena_el_propio_y_se_declara(cfg, gpio, tmp_path) -> None:  # noqa: ANN001
    sin = cfg.model_copy(update={"audio_oficial_path": str(tmp_path / "no-esta.wav")})
    notifier, siren = _notifier(sin, gpio)
    try:
        gpio.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path, "una alerta nunca calla por esto"
        oficial = notifier.profile_report["oficial"]
        assert oficial["disponible"] is False and "no existe" in oficial["motivo"]
    finally:
        notifier.stop()


def test_un_fichero_con_OTRA_huella_no_suena(cfg, gpio, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """Sólo suena lo auditado: un WAV cambiado en el disco del gabinete no es el oficial."""
    monkeypatch.setattr(catalog, "OFICIAL_SHA256", "0" * 64)
    otro = _wav(tmp_path / "sasmex_oficial.wav")
    notifier, siren = _notifier(_con_oficial(cfg, otro), gpio)
    try:
        gpio.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert siren.playing == cfg.audio_siren_path
        assert "huella" in notifier.profile_report["oficial"]["motivo"]
    finally:
        notifier.stop()


def test_un_oficial_que_no_es_WAV_no_se_valida(cfg, gpio, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """Con la huella correcta y el contenido roto, aplay moriría al arrancar y el
    vigilante lo relanzaría a 20 Hz, mudo, toda la alerta. Se descarta al arrancar."""
    roto = tmp_path / "sasmex_oficial.wav"
    roto.write_bytes(b"RIFF-esto-no-es-pcm")
    monkeypatch.setattr(catalog, "OFICIAL_SHA256", _huella(roto))
    notifier, _siren = _notifier(_con_oficial(cfg, roto), gpio)
    try:
        assert notifier.profile_report["oficial"]["disponible"] is False
        assert "WAV" in notifier.profile_report["oficial"]["motivo"]
    finally:
        notifier.stop()


def test_el_reporte_dice_que_hay_oficial_sin_dar_su_ruta(cfg, gpio, oficial) -> None:  # noqa: ANN001
    notifier, _siren = _notifier(_con_oficial(cfg, oficial), gpio)
    try:
        r = notifier.profile_report["oficial"]
        assert r == {
            "disponible": True,
            "jack": True,
            "sha256": catalog.OFICIAL_SHA256[:16],
            "motivo": None,
        }
    finally:
        notifier.stop()


def test_sin_parlante_en_el_jack_el_reporte_no_promete_el_oficial(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """Con `audio_siren_enabled=false` (el valor por defecto) por el jack no sale nada:
    el fichero puede estar, pero decir «suena el oficial» sería afirmar un sonido que
    nadie emite (regla de oro 7)."""
    sin_jack = _con_oficial(cfg, oficial).model_copy(update={"audio_siren_enabled": False})
    notifier, siren = _notifier(sin_jack, gpio)
    try:
        gpio.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert siren.playing is None
        assert notifier.profile_report["oficial"]["jack"] is False
    finally:
        notifier.stop()


def test_el_oficial_no_se_elige_por_ranura_desde_la_nube(cfg, gpio, oficial) -> None:  # noqa: ANN001
    """La ranura `siren` también suena con el umbral local: si la nube pudiera poner ahí
    el oficial, lo haría sonar donde la decisión dice que no. Sigue reservado."""
    notifier, _siren = _notifier(_con_oficial(cfg, oficial), gpio)
    try:
        r = notifier.apply_audio_profile({"siren": catalog.OFICIAL_ID})
        assert r["rejected"] == {"siren": catalog.OFICIAL_ID}
        assert "D-50" in r["reserved"]["siren"]
    finally:
        notifier.stop()


def test_el_supervisor_le_pasa_al_audio_el_cuorum_del_despachador(supervisor) -> None:  # noqa: ANN001
    """El audio se construye ANTES que el despachador: sin este enlace tardío, el cuórum
    sonaría siempre con el tono propio y nada lo diría."""
    assert supervisor.audio._quorum_source == supervisor.dispatch.quorum_siren_desde
