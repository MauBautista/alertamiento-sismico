"""Voceo por audio del gabinete (hallazgo A-6) — canal ADVISORY, jamás de vida.

Contrato:
- La sirena de RELÉ es la alerta primaria; el voceo solo COMPLEMENTA. Un fallo del
  audio (backend roto, asset ausente en caliente) se registra y se aísla — nunca
  propaga al hilo de actuación.
- DESHABILITADO por default: se enciende por gabinete cuando el hardware de audio
  (DAC/amplificador/bocina — el Pi 5 no trae jack) exista físicamente (gate HW).
- Subordinado al SILENCIO: si los audibles están silenciados no se vocea, y
  silenciar (botón físico o panel) DETIENE el voceo en curso.
- Sismo y simulacro usan assets DISTINTOS; el drill del panel LAN va con PIN y no
  toca relés.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
from takab_edge.audio import AudioNotifier, SimulatedAudioBackend
from takab_edge.config import load_settings
from takab_edge.contracts import AlertSource, Tier, TierDecision
from takab_edge.gpio import GpioController
from takab_edge.local_api import LocalDashboard
from takab_edge.supervisor import EdgeSupervisor


@pytest.fixture
def assets(tmp_path: Path) -> dict[str, str]:
    sismo = tmp_path / "sismo.wav"
    simulacro = tmp_path / "simulacro.wav"
    sismo.write_bytes(b"RIFF-sismo-fake-wav")
    simulacro.write_bytes(b"RIFF-simulacro-fake-wav")
    return {"sismo": str(sismo), "simulacro": str(simulacro)}


@pytest.fixture
def audio_settings(settings, assets):  # noqa: ANN001 — fixtures del conftest
    return settings.model_copy(
        update={
            "audio_enabled": True,
            "audio_sismo_path": assets["sismo"],
            "audio_simulacro_path": assets["simulacro"],
        }
    )


@pytest.fixture
def gpio(audio_settings) -> GpioController:  # noqa: ANN001
    controller = GpioController(audio_settings)
    controller.start()
    yield controller
    controller.stop()


def _notifier(cfg, gpio: GpioController) -> tuple[AudioNotifier, SimulatedAudioBackend]:  # noqa: ANN001
    backend = SimulatedAudioBackend()
    notifier = AudioNotifier(cfg, gpio=gpio, backend=backend)
    notifier.start()
    return notifier, backend


def _evacuate() -> TierDecision:
    return TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.SASMEX)


def test_deshabilitado_por_default() -> None:
    """El voceo NO existe hasta que el hardware exista: default apagado."""
    assert load_settings().audio_enabled is False


def test_on_tier_evacuate_reproduce_sismo(audio_settings, gpio) -> None:  # noqa: ANN001
    notifier, backend = _notifier(audio_settings, gpio)
    notifier.on_tier(_evacuate())
    assert backend.plays == [audio_settings.audio_sismo_path]


def test_on_tier_menor_no_reproduce(audio_settings, gpio) -> None:  # noqa: ANN001
    """Solo el tier audible (evacuate_or_hold) vocea; watch/restricted no."""
    notifier, backend = _notifier(audio_settings, gpio)
    for tier in (Tier.NORMAL, Tier.WATCH, Tier.RESTRICTED, Tier.MANUAL_ONLY):
        notifier.on_tier(TierDecision(tier=tier, source=AlertSource.THRESHOLD))
    assert backend.plays == []


def test_deshabilitado_no_reproduce(audio_settings, gpio) -> None:  # noqa: ANN001
    cfg = audio_settings.model_copy(update={"audio_enabled": False})
    notifier, backend = _notifier(cfg, gpio)
    notifier.on_tier(_evacuate())
    notifier.play_simulacro()
    assert backend.plays == []


def test_silenciado_no_reproduce(audio_settings, gpio) -> None:  # noqa: ANN001
    """Con los audibles silenciados NO arranca un voceo nuevo."""
    notifier, backend = _notifier(audio_settings, gpio)
    gpio.silence_audibles(True)
    notifier.play_sismo()
    assert backend.plays == []


def test_silencio_detiene_el_voceo_en_curso(audio_settings, gpio) -> None:  # noqa: ANN001
    """SILENCIAR (físico o panel) calla TAMBIÉN la voz, no solo la sirena."""
    notifier, backend = _notifier(audio_settings, gpio)
    notifier.play_sismo()
    assert backend.playing is not None
    gpio.silence_audibles(True)
    assert backend.playing is None


def test_simulacro_usa_asset_distinto(audio_settings, gpio) -> None:  # noqa: ANN001
    notifier, backend = _notifier(audio_settings, gpio)
    notifier.play_simulacro()
    assert backend.plays == [audio_settings.audio_simulacro_path]
    assert audio_settings.audio_simulacro_path != audio_settings.audio_sismo_path


def test_asset_faltante_truena_al_arrancar(audio_settings, gpio, tmp_path) -> None:  # noqa: ANN001
    """Habilitado + asset inexistente = módulo NO arranca (fail-loud, aislado)."""
    cfg = audio_settings.model_copy(update={"audio_sismo_path": str(tmp_path / "no-existe.wav")})
    notifier = AudioNotifier(cfg, gpio=gpio, backend=SimulatedAudioBackend())
    with pytest.raises(RuntimeError, match="sismo"):
        notifier.start()


def test_backend_roto_no_propaga(audio_settings, gpio) -> None:  # noqa: ANN001
    """El voceo es ADVISORY: un backend que revienta jamás tira el hilo llamador."""

    class _Explota(SimulatedAudioBackend):
        def play(self, path: str) -> None:
            raise OSError("aplay no existe")

    notifier = AudioNotifier(audio_settings, gpio=gpio, backend=_Explota())
    notifier.start()
    notifier.play_sismo()  # no debe lanzar
    notifier.on_tier(_evacuate())  # tampoco


# --- Sirena por AUDIO (T-1.68): el sonido de la sirena sale por el jack 3.5 mm --
# Toggle PROPIO (audio_siren_enabled), independiente del voceo. Sigue el estado
# `gpio.siren_sounding` (reflejo real, prueba de sirena o prueba de actuación) y
# se calla al silenciar/resetear — un solo poll cubre todos los casos.


@pytest.fixture
def siren_cfg(settings, tmp_path):  # noqa: ANN001
    wav = tmp_path / "siren.wav"
    wav.write_bytes(b"RIFF-siren-fake-wav")
    return settings.model_copy(update={"audio_siren_enabled": True, "audio_siren_path": str(wav)})


def _siren_notifier(cfg, gpio):  # noqa: ANN001
    siren = SimulatedAudioBackend()
    notifier = AudioNotifier(cfg, gpio=gpio, backend=SimulatedAudioBackend(), siren_backend=siren)
    notifier.start()
    return notifier, siren


def test_sirena_por_audio_sigue_el_estado_de_la_sirena(siren_cfg, gpio) -> None:  # noqa: ANN001
    notifier, siren = _siren_notifier(siren_cfg, gpio)
    gpio.simulate_sasmex(active=True)  # sirena SONANDO
    notifier._reconcile_siren()
    assert siren.playing == siren_cfg.audio_siren_path
    gpio.silence_audibles(True)  # el operador silencia
    notifier._reconcile_siren()
    assert siren.playing is None  # la sirena por audio se calla con la de relé


def test_prueba_de_actuacion_suena_por_audio(siren_cfg, gpio) -> None:  # noqa: ANN001
    """La prueba LOCAL de actuación (T-1.67) también hace sonar la sirena por el jack."""
    notifier, siren = _siren_notifier(siren_cfg, gpio)
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    notifier._reconcile_siren()
    assert siren.playing == siren_cfg.audio_siren_path
    gpio.reset()


def test_sirena_por_audio_deshabilitada_no_suena(settings, gpio) -> None:  # noqa: ANN001
    notifier, siren = _siren_notifier(settings, gpio)  # audio_siren_enabled=False (default)
    gpio.simulate_sasmex(active=True)
    notifier._reconcile_siren()
    assert siren.plays == []


def test_sirena_por_audio_asset_faltante_truena_al_arrancar(settings, gpio, tmp_path) -> None:  # noqa: ANN001
    cfg = settings.model_copy(
        update={"audio_siren_enabled": True, "audio_siren_path": str(tmp_path / "no.wav")}
    )
    notifier = AudioNotifier(cfg, gpio=gpio, siren_backend=SimulatedAudioBackend())
    with pytest.raises(RuntimeError, match="sirena"):
        notifier.start()


def test_sirena_por_audio_backend_roto_no_propaga(siren_cfg, gpio) -> None:  # noqa: ANN001
    class _Explota(SimulatedAudioBackend):
        def play(self, path: str) -> None:
            raise OSError("aplay no existe")

    notifier = AudioNotifier(siren_cfg, gpio=gpio, siren_backend=_Explota())
    notifier.start()
    gpio.simulate_sasmex(active=True)
    notifier._reconcile_siren()  # advisory: jamás propaga al camino de vida


def test_watcher_arranca_la_sirena_en_segundo_plano(siren_cfg, gpio) -> None:  # noqa: ANN001
    import time

    notifier, siren = _siren_notifier(siren_cfg, gpio)
    gpio.simulate_sasmex(active=True)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and siren.playing is None:
        time.sleep(0.02)
    assert siren.playing == siren_cfg.audio_siren_path  # el hilo watcher la levantó solo
    notifier.stop()


class _RulesStub:
    last_decision = None


class _HealthStub:
    last_snapshot = None


@pytest.fixture
def panel(audio_settings, gpio):  # noqa: ANN001
    notifier, backend = _notifier(audio_settings, gpio)
    dashboard = LocalDashboard(
        gpio,
        _RulesStub(),
        _HealthStub(),
        port=0,
        dev_mode=True,
        audio=notifier,
    )
    dashboard.start()
    yield dashboard, backend
    dashboard.stop()
    notifier.stop()


def _post(dashboard: LocalDashboard, path: str) -> int:
    host, port = dashboard.address
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 — loopback de test
        return r.status


def test_drill_por_panel_lan(panel) -> None:  # noqa: ANN001
    """POST /api/drill-audio (PIN abierto en dev) reproduce el asset de SIMULACRO."""
    dashboard, backend = panel
    assert _post(dashboard, "/api/drill-audio") == 200
    assert len(backend.plays) == 1
    assert backend.plays[0].endswith("simulacro.wav")


def test_reset_por_panel_detiene_voceo(panel) -> None:  # noqa: ANN001
    """CERRAR ALERTA también calla la voz (la alerta terminó)."""
    dashboard, backend = panel
    assert _post(dashboard, "/api/drill-audio") == 200
    assert backend.playing is not None
    assert _post(dashboard, "/api/reset") == 200
    assert backend.playing is None


def test_status_expone_audio(panel) -> None:  # noqa: ANN001
    """El panel solo muestra el botón si status.audio.enabled — sin botones muertos."""
    dashboard, _backend = panel
    section = dashboard.status()["audio"]
    assert section == {"enabled": True, "sounding": False}


def test_supervisor_cablea_el_voceo(audio_settings, monkeypatch) -> None:  # noqa: ANN001
    """El supervisor construye el módulo, lo registra y lo dispara tras actuar."""
    sup = EdgeSupervisor(audio_settings).build()
    assert "audio" in sup._modules
    assert sup.local_api._audio is sup.audio

    voceados: list[Tier] = []
    monkeypatch.setattr(sup.audio, "on_tier", lambda d: voceados.append(d.tier))
    monkeypatch.setattr(sup.cloud, "publish", lambda *a, **k: None)
    monkeypatch.setattr(sup.backfill, "queue_evidence", lambda *a, **k: None)
    sup.gpio.start()
    sup.actuators.start()
    try:
        sup._act_and_publish(_evacuate(), None)
    finally:
        sup.actuators.stop()
        sup.gpio.stop()
    assert voceados == [Tier.EVACUATE_OR_HOLD]
