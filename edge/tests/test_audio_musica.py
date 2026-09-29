"""[T-9.72 · D-40] Música para PROBAR LOS PARLANTES del gabinete — advisory, jamás de vida.

Sale por el MISMO jack que la sirena por audio (son esos parlantes los que se prueban),
pero por un canal PROPIO: el vigilante de la sirena, a 20 Hz, calla todo lo que suene
en el suyo sin ser sirena.

Contrato (el de la ficha, y por qué cada línea):
- **Cualquier alerta la interrumpe, y ANTES de que suene la sirena.** Dos WAVs en el mismo
  jack se mezclan: un híbrido de himno y sirena no es ninguna de las dos cosas para quien
  está dentro del edificio.
- **El simulacro y el voceo de sismo también la cortan**, y el silencio la calla.
- **409 si hay una alerta viva** (o una prueba de sirena, o un voceo en curso): no se
  arranca música encima de algo que tiene que oírse.
- **Tope de 30 min**: nadie deja el edificio con música toda la noche por olvido.
- **Fail-CERRADO**: sin poder leer el estado del gabinete, la música calla. Nunca al revés.
- Sin parlante declarado (``audio_siren_enabled=False``) no hay música: no se promete lo
  que el gabinete no puede sonar.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest
from takab_edge import audio as audio_mod
from takab_edge.audio import MUSICA_TOPE_S, AudioNotifier, SimulatedAudioBackend
from takab_edge.contracts import SirenReason
from takab_edge.gpio import GpioController
from takab_edge.local_api import LocalDashboard


class _Bitacora:
    """Backend que anota en una lista COMPARTIDA: permite afirmar el ORDEN entre canales."""

    def __init__(self, nombre: str, diario: list[str]) -> None:
        self._nombre = nombre
        self._diario = diario
        self._playing: str | None = None
        self.plays: list[str] = []

    def play(self, path: str) -> None:
        self._diario.append(f"{self._nombre}:play")
        self._playing = path
        self.plays.append(path)

    def stop(self) -> None:
        if self._playing is not None:
            self._diario.append(f"{self._nombre}:stop")
        self._playing = None

    @property
    def playing(self) -> str | None:
        return self._playing

    def termina(self) -> None:
        """Lo que hace `aplay` al acabar el archivo: deja de sonar solo."""
        self._playing = None


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def musica_cfg(settings, tmp_path: Path):  # noqa: ANN001 — fixtures del conftest
    siren = tmp_path / "siren.wav"
    siren.write_bytes(b"RIFF-siren-fake")
    musica = tmp_path / "musica_prueba.wav"
    musica.write_bytes(b"RIFF-musica-fake")
    sismo = tmp_path / "sismo.wav"
    sismo.write_bytes(b"RIFF-sismo-fake")
    simulacro = tmp_path / "simulacro.wav"
    simulacro.write_bytes(b"RIFF-simulacro-fake")
    return settings.model_copy(
        update={
            "audio_siren_enabled": True,
            "audio_siren_path": str(siren),
            "audio_music_path": str(musica),
            "audio_enabled": True,
            "audio_sismo_path": str(sismo),
            "audio_simulacro_path": str(simulacro),
        }
    )


@pytest.fixture
def gpio(musica_cfg):  # noqa: ANN001
    controller = GpioController(musica_cfg)
    controller.start()
    yield controller
    controller.stop()


#: Lo que dura el archivo de verdad (~33 s): avanzar el reloj esto simula que terminó.
DURA_EL_ARCHIVO_S = 33


@pytest.fixture
def vigilante_dormido(monkeypatch):  # noqa: ANN001
    """El vigilante REAL arranca (la música lo exige vivo), pero con una vuelta de una
    hora: las pruebas dan cada «tic» a mano y pueden afirmar el orden."""
    monkeypatch.setattr(audio_mod, "_SIREN_POLL_S", 3600)


@pytest.fixture
def armado(musica_cfg, gpio, vigilante_dormido):  # noqa: ANN001
    diario: list[str] = []
    voz, sirena, musica = (_Bitacora(n, diario) for n in ("voz", "sirena", "musica"))
    reloj = _Reloj()
    notifier = AudioNotifier(
        musica_cfg,
        gpio=gpio,
        backend=voz,
        siren_backend=sirena,
        music_backend=musica,
        reloj=reloj,
    )
    notifier._on_start()
    yield notifier, voz, sirena, musica, diario, reloj
    notifier._on_stop()


# --- arranque, bucle y tope ---------------------------------------------------------


def test_suena_por_su_canal_propio_y_el_estado_lo_dice(armado, musica_cfg) -> None:  # noqa: ANN001
    notifier, voz, sirena, musica, _d, _r = armado
    assert notifier.start_music() is None
    assert musica.playing == musica_cfg.audio_music_path
    assert sirena.playing is None and voz.playing is None
    estado = notifier.music_status()
    assert estado["disponible"] is True
    assert estado["activa"] is True
    assert estado["restante_s"] == MUSICA_TOPE_S


def test_se_repite_en_bucle_mientras_no_se_detenga(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, reloj = armado
    notifier.start_music()
    reloj.t += DURA_EL_ARCHIVO_S
    musica.termina()
    notifier._tick()
    assert len(musica.plays) == 2
    assert notifier.music_status()["activa"] is True


def test_un_reproductor_que_muere_al_arrancar_NO_se_relanza_en_bucle(armado) -> None:  # noqa: ANN001
    """aplay que sale al instante (ALSA ocupado, sin tarjeta): relanzarlo a 20 Hz 30 min
    diría «SONANDO» con los parlantes mudos. Se corta una vez, con `fallo`."""
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    musica.termina()  # sin avanzar el reloj: murió en el acto
    notifier._tick()
    assert len(musica.plays) == 1
    estado = notifier.music_status()
    assert estado["activa"] is False
    assert estado["ultimo_corte"]["motivo"] == "fallo"


def test_si_el_bucle_no_puede_reanudar_corta_con_fallo(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, reloj = armado
    notifier.start_music()

    def _revienta(path: str) -> None:
        raise OSError("aplay no está")

    musica.play = _revienta  # type: ignore[method-assign]
    reloj.t += DURA_EL_ARCHIVO_S
    musica.termina()
    notifier._tick()
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "fallo"


def test_el_tope_de_30_min_la_termina(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, reloj = armado
    assert MUSICA_TOPE_S == 30 * 60
    notifier.start_music()
    reloj.t += MUSICA_TOPE_S + 1
    notifier._tick()
    assert musica.playing is None
    estado = notifier.music_status()
    assert estado["activa"] is False
    assert estado["ultimo_corte"]["motivo"] == "tope"


def test_detener_la_calla_y_lo_declara(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    notifier.stop_music()
    assert musica.playing is None
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "operador"


# --- lo que la interrumpe --------------------------------------------------------------


def test_una_alerta_la_calla_ANTES_de_que_suene_la_sirena(armado, gpio) -> None:  # noqa: ANN001
    notifier, _v, sirena, musica, diario, _r = armado
    notifier.start_music()
    diario.clear()
    gpio.simulate_sasmex(active=True)
    notifier._tick()
    assert musica.playing is None
    assert sirena.playing is not None
    assert diario.index("musica:stop") < diario.index("sirena:play")
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "alerta"


def test_la_prueba_de_sirena_tambien_la_calla(armado, gpio) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    notifier._tick()
    assert musica.playing is None
    gpio.reset()


def test_el_simulacro_la_corta_antes_de_vocear(armado) -> None:  # noqa: ANN001
    notifier, voz, _s, musica, diario, _r = armado
    notifier.start_music()
    diario.clear()
    notifier.play_simulacro()
    assert musica.playing is None
    assert voz.playing is not None
    assert diario.index("musica:stop") < diario.index("voz:play")


def test_el_voceo_de_sismo_la_corta(armado) -> None:  # noqa: ANN001
    notifier, voz, _s, musica, _d, _r = armado
    notifier.start_music()
    notifier.play_sismo()
    assert musica.playing is None and voz.playing is not None


def test_el_silencio_la_calla_sin_esperar_al_vigilante(armado, gpio) -> None:  # noqa: ANN001
    """Por el aviso del silencio, no por la vuelta del vigilante: sin `_tick()`."""
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    gpio.silence_audibles(True)
    assert musica.playing is None
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "silencio"


def test_un_voceo_que_entra_por_otro_camino_la_corta_en_el_vigilante(armado) -> None:  # noqa: ANN001
    """Si mañana algo vocea sin pasar por play_sismo/play_simulacro, el vigilante la calla."""
    notifier, voz, _s, musica, _d, _r = armado
    notifier.start_music()
    voz.play("otra-voz.wav")
    notifier._tick()
    assert musica.playing is None
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "voceo"


@dataclass
class _Snap:
    siren_reason: SirenReason | None = None
    sasmex_active: bool = False
    alert_latched: bool = False
    actuation_test_active: bool = False
    audible_silenced: bool = False


class _LinkFalso:
    def __init__(self) -> None:
        self.snap = _Snap()

    def snapshot(self) -> _Snap:
        return self.snap


_CONDICIONES = [
    ("siren_reason", SirenReason.ALERT, "alerta"),
    ("sasmex_active", True, "alerta"),
    ("alert_latched", True, "alerta"),
    ("actuation_test_active", True, "alerta"),
    ("audible_silenced", True, "silencio"),
]


@pytest.mark.parametrize(("campo", "valor", "motivo"), _CONDICIONES)
def test_cada_condicion_POR_SEPARADO_la_corta(armado, monkeypatch, campo, valor, motivo) -> None:  # noqa: ANN001
    """Una alerta real las enciende casi todas a la vez; aquí va UNA sola, para que
    quitar cualquiera del código ponga esto rojo."""
    notifier, _v, _s, musica, _d, _r = armado
    link = _LinkFalso()
    monkeypatch.setattr(notifier, "_link", link)
    assert notifier.start_music() is None
    setattr(link.snap, campo, valor)
    notifier._tick()
    assert musica.playing is None
    assert notifier.music_status()["ultimo_corte"]["motivo"] == motivo


@pytest.mark.parametrize(("campo", "valor", "motivo"), _CONDICIONES)
def test_cada_condicion_POR_SEPARADO_impide_arrancar(
    armado, monkeypatch, campo, valor, motivo
) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    link = _LinkFalso()
    monkeypatch.setattr(notifier, "_link", link)
    setattr(link.snap, campo, valor)
    razon = notifier.start_music()
    assert razon is not None
    assert ("silenciados" if motivo == "silencio" else "alerta") in razon
    assert musica.plays == []


def test_un_corte_que_falla_se_reintenta_hasta_callar(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    stop_real = musica.stop
    intentos = {"n": 0}

    def _stop_que_falla_una_vez() -> None:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise OSError("aplay no muere")
        stop_real()

    musica.stop = _stop_que_falla_una_vez  # type: ignore[method-assign]
    notifier.stop_music()
    assert musica.playing is not None  # el primer corte falló
    notifier._tick()  # el vigilante lo reintenta: no hay música pedida y algo suena
    assert musica.playing is None


def test_el_voceo_de_sismo_no_espera_al_reproductor_de_musica(armado) -> None:  # noqa: ANN001
    """El supervisor llama a play_sismo y DESPUÉS avisa a los secundarios y publica: un
    aplay que tarda en morir no puede tenerlo parado."""
    notifier, voz, _s, musica, _d, _r = armado
    notifier.start_music()
    stop_real = musica.stop

    def _stop_lento() -> None:
        time.sleep(1.5)
        stop_real()

    musica.stop = _stop_lento  # type: ignore[method-assign]
    t0 = time.monotonic()
    notifier.play_sismo()
    assert time.monotonic() - t0 < 0.5
    assert voz.playing is not None
    assert notifier.music_status()["activa"] is False


def test_sin_vigilante_vivo_no_hay_musica(musica_cfg, gpio) -> None:  # noqa: ANN001
    """Si el módulo no arrancó (p. ej. falta un asset de voceo), nadie podría callarla."""
    notifier = AudioNotifier(musica_cfg, gpio=gpio, music_backend=SimulatedAudioBackend())
    estado = notifier.music_status()
    assert estado["disponible"] is False
    assert "vigilante" in estado["motivo"]
    assert notifier.start_music() is not None


def test_sin_poder_leer_el_gabinete_CALLA(armado, monkeypatch) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()

    class _LinkRoto:
        def snapshot(self):  # noqa: ANN202
            raise ConnectionError("el dueño de los pines no contesta")

    monkeypatch.setattr(notifier, "_link", _LinkRoto())
    notifier._tick()
    assert musica.playing is None
    assert notifier.music_status()["ultimo_corte"]["motivo"] == "sin_estado"


def test_parar_el_modulo_la_calla(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.start_music()
    notifier._on_stop()
    assert musica.playing is None


# --- cuándo NO arranca ------------------------------------------------------------------


def test_no_arranca_con_una_alerta_viva(armado, gpio) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    gpio.simulate_sasmex(active=True)
    motivo = notifier.start_music()
    assert motivo is not None and "alerta" in motivo
    assert musica.plays == []


def test_no_arranca_con_un_voceo_en_curso(armado) -> None:  # noqa: ANN001
    notifier, _v, _s, musica, _d, _r = armado
    notifier.play_simulacro()
    assert notifier.start_music() is not None
    assert musica.plays == []


def test_sin_parlante_no_hay_musica(settings, gpio, tmp_path) -> None:  # noqa: ANN001
    musica_wav = tmp_path / "m.wav"
    musica_wav.write_bytes(b"RIFF")
    cfg = settings.model_copy(update={"audio_music_path": str(musica_wav)})  # sirena por jack OFF
    notifier = AudioNotifier(cfg, gpio=gpio, music_backend=SimulatedAudioBackend())
    estado = notifier.music_status()
    assert estado["disponible"] is False and estado["motivo"]
    assert notifier.start_music() is not None


def test_sin_asset_no_hay_musica(musica_cfg, gpio, tmp_path) -> None:  # noqa: ANN001
    cfg = musica_cfg.model_copy(update={"audio_music_path": str(tmp_path / "no-existe.wav")})
    notifier = AudioNotifier(cfg, gpio=gpio, music_backend=SimulatedAudioBackend())
    assert notifier.music_status()["disponible"] is False
    assert notifier.start_music() is not None


def test_el_asset_empaquetado_existe() -> None:
    """Sin override, suena el WAV que viaja con la release (T-9.72, parte B)."""
    from takab_edge import audio

    assert (Path(audio.__file__).parent / "assets" / "musica_prueba.wav").is_file()


# --- el panel LAN -----------------------------------------------------------------------


class _RulesStub:
    last_decision = None

    def reset(self) -> None:
        pass


class _HealthStub:
    last_snapshot = None


class _Ledger:
    def __init__(self) -> None:
        self.filas: list[dict] = []

    def record(self, **kw) -> None:  # noqa: ANN003
        self.filas.append(kw)


@pytest.fixture
def panel(musica_cfg, gpio, vigilante_dormido):  # noqa: ANN001
    musica = SimulatedAudioBackend()
    notifier = AudioNotifier(
        musica_cfg,
        gpio=gpio,
        backend=SimulatedAudioBackend(),
        siren_backend=SimulatedAudioBackend(),
        music_backend=musica,
    )
    notifier._on_start()
    ledger = _Ledger()
    dashboard = LocalDashboard(
        gpio, _RulesStub(), _HealthStub(), port=0, dev_mode=True, audio=notifier, ledger=ledger
    )
    dashboard.start()
    yield dashboard, notifier, musica, ledger
    dashboard.stop()
    notifier._on_stop()


def _post(dashboard: LocalDashboard, path: str) -> tuple[int, dict]:
    host, port = dashboard.address
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 — loopback de test
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_el_panel_la_arranca_y_la_detiene(panel) -> None:  # noqa: ANN001
    dashboard, _n, musica, _l = panel
    assert _post(dashboard, "/api/audio-musica")[0] == 200
    assert musica.playing is not None
    assert dashboard.status()["audio"]["music"]["activa"] is True
    assert _post(dashboard, "/api/audio-musica/detener")[0] == 200
    assert musica.playing is None


def test_el_panel_da_409_con_una_alerta_viva(panel, gpio) -> None:  # noqa: ANN001
    dashboard, _n, musica, _l = panel
    gpio.simulate_sasmex(active=True)
    code, cuerpo = _post(dashboard, "/api/audio-musica")
    assert code == 409
    assert "alerta" in cuerpo["error"]
    assert musica.plays == []


def test_el_panel_pide_el_PIN(musica_cfg, gpio) -> None:  # noqa: ANN001
    musica = SimulatedAudioBackend()
    notifier = AudioNotifier(musica_cfg, gpio=gpio, music_backend=musica)
    dashboard = LocalDashboard(
        gpio, _RulesStub(), _HealthStub(), port=0, dev_mode=False, audio=notifier, pin="4321"
    )
    dashboard.start()
    try:
        assert _post(dashboard, "/api/audio-musica")[0] == 401
        assert musica.plays == []
    finally:
        dashboard.stop()


def test_arrancar_la_musica_deja_fila_en_la_bitacora_con_su_huella(panel) -> None:  # noqa: ANN001
    """Sale por el altavoz de un edificio con gente hasta 30 min: se sabe qué sonó."""
    dashboard, _n, _m, ledger = panel
    _post(dashboard, "/api/audio-musica")
    filas = [f for f in ledger.filas if f.get("action") == "music_start"]
    assert len(filas) == 1
    assert str(filas[0]["cause"]) == "lan_music_test"
    assert "sha256=" in filas[0]["detail"]


def test_la_bitacora_dice_QUIEN_la_callo_y_no_culpa_al_operador_de_un_corte_ajeno(
    panel, gpio
) -> None:  # noqa: ANN001
    """La cortó una alerta; luego el guardia pulsa DETENER (el panel aún mostraba el botón).
    La bitácora dice «alerta», una vez, y no inventa un corte del operador."""
    dashboard, notifier, _m, ledger = panel
    assert _post(dashboard, "/api/audio-musica")[0] == 200
    gpio.simulate_sasmex(active=True)
    notifier._tick()
    assert _post(dashboard, "/api/audio-musica/detener")[0] == 200
    cortes = [f["detail"] for f in ledger.filas if f.get("action") == "music_stop"]
    assert len(cortes) == 1
    assert cortes[0].startswith("motivo=alerta")
