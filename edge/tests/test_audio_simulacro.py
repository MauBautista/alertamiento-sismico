"""La ranura de voceo de simulacro y su constancia (T-5.17).

Lo que fija, en orden:

* **La ranura nueva sigue las MISMAS reglas que las dos que ya había**: la nube
  elige por identificador de catálogo, nunca por binario ni ruta absoluta —ese
  canal viaja firmado hacia un aparato que toca gas y puertas—, y un id que este
  edge no puede servir **conserva el tono anterior** en vez de caer a otro.
* **Los tres caminos, con sus tres desenlaces distintos**: válido (aplica),
  desconocido (conserva y lo declara), reservado (conserva, lo declara, y además
  puede decir POR QUÉ — el tono oficial de SASMEX es de CIRES y su ausencia del
  catálogo es lo que lo hace seguro).
* **El sha256 se calcula de lo que VA A SONAR, en el instante de sonar** — no
  del asset que se enumeró al arrancar. Entre el arranque y el simulacro puede
  haber entrado una config firmada que cambió el tono.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from takab_edge.audio import catalog
from takab_edge.gpio import GpioController

ASSETS = Path(catalog.__file__).parent / "assets"


def test_el_catalogo_gana_el_tono_de_simulacro_Y_su_archivo_existe():
    """Un id en el catálogo sin su WAV empaquetado deja al inmueble mudo."""
    assert "takab-simulacro-v1" in catalog.CATALOG
    ruta = catalog.resolve("takab-simulacro-v1")
    assert ruta is not None and ruta.is_file()


def test_el_tono_de_simulacro_NO_es_el_de_la_sirena_ni_el_de_prueba():
    """Un simulacro que suena a sismo es una falsa alarma del propio sistema.

    Es la misma corrección que `T-2.49` hizo para el self-test, y aquí se
    comprueba por CONTENIDO: dos ids distintos apuntando al mismo binario
    sonarían igual aunque el catálogo dijera lo contrario.
    """
    digest = {
        cid: hashlib.sha256(catalog.resolve(cid).read_bytes()).hexdigest()
        for cid in ("takab-siren-v1", "takab-prueba-v1", "takab-simulacro-v1")
    }
    assert len(set(digest.values())) == 3, f"dos tonos comparten binario: {digest}"


def test_el_tono_oficial_de_SASMEX_sigue_reservado_y_ausente():
    assert "sasmex-oficial-v1" not in catalog.CATALOG
    assert "sasmex-oficial-v1" in catalog.RESERVED
    assert catalog.resolve("sasmex-oficial-v1") is None


# ── los tres caminos de la ranura ──────────────────────────────────────────


@pytest.fixture
def audio(settings):  # noqa: ANN001 — `settings` viene del conftest
    """Módulo de audio con backend simulado: aquí se prueba la RESOLUCIÓN del
    catálogo, no el jack. `audio_enabled` queda en false a propósito — la
    evidencia tiene que distinguir «qué sonaría» de «va a sonar»."""
    from takab_edge.audio import AudioNotifier, SimulatedAudioBackend

    return AudioNotifier(
        settings.model_copy(update={"audio_simulacro_path": ""}),
        gpio=GpioController(settings),
        backend=SimulatedAudioBackend(),
        siren_backend=SimulatedAudioBackend(),
    )


def test_camino_VALIDO_aplica_el_tono_y_lo_reporta(audio):
    reporte = audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    assert reporte["applied"]["simulacro"] == "takab-simulacro-v1"
    assert reporte["rejected"] == {}
    assert audio.simulacro_path.endswith("simulacro.wav")


def test_camino_DESCONOCIDO_conserva_el_tono_anterior_y_LO_DECLARA(audio):
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    antes = audio.simulacro_path

    reporte = audio.apply_audio_profile({"simulacro": "takab-inventado-v9"})
    assert audio.simulacro_path == antes, "cayó a otro tono en vez de conservar el suyo"
    assert reporte["rejected"]["simulacro"] == "takab-inventado-v9"
    assert reporte["applied"] == {}


def test_camino_RESERVADO_conserva_el_tono_Y_dice_por_que(audio):
    """`sasmex-oficial-v1` no es «desconocido»: es conocido y prohibido."""
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    antes = audio.simulacro_path

    reporte = audio.apply_audio_profile({"simulacro": "sasmex-oficial-v1"})
    assert audio.simulacro_path == antes
    assert reporte["rejected"]["simulacro"] == "sasmex-oficial-v1"
    # La razón viaja: un «desconocido» opaco no permitiría distinguir el descuido
    # de la infracción legal.
    assert "CIRES" in reporte["reserved"]["simulacro"]


def test_sin_ranura_en_el_perfil_no_se_toca_nada(audio):
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    antes = audio.simulacro_path
    audio.apply_audio_profile({"siren": "takab-siren-v1"})
    assert audio.simulacro_path == antes


# ── la evidencia de lo que sonó ────────────────────────────────────────────


def test_la_evidencia_dice_QUE_va_a_sonar_y_su_sha256(audio):
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    ev = audio.simulacro_evidence()
    esperado = hashlib.sha256((ASSETS / "simulacro.wav").read_bytes()).hexdigest()
    assert ev["asset_id"] == "takab-simulacro-v1"
    assert ev["sha256"] == esperado
    assert ev["will_sound"] is False, "audio_enabled=false: no suena, y la evidencia lo dice"


def test_la_evidencia_se_calcula_DE_LO_QUE_SONARIA_AHORA_no_de_lo_del_arranque(audio):
    """Entre el arranque y el simulacro puede haber entrado una config firmada."""
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
    primero = audio.simulacro_evidence()["sha256"]

    audio.apply_audio_profile({"simulacro": "takab-prueba-v1"})
    segundo = audio.simulacro_evidence()["sha256"]
    assert primero != segundo, "la evidencia se quedó congelada en el asset del arranque"


def test_sin_asset_la_evidencia_lo_DICE_en_vez_de_inventar_un_hash(audio):
    ev = audio.simulacro_evidence()
    assert ev["sha256"] is None
    assert ev["asset_id"] is None
    assert "sin asset" in ev["reason"].lower()


# ── la constancia: qué sonó, y dónde queda escrito ─────────────────────────
#
# El hueco que cierra esta parte: el sha256 se registraba AL ARRANCAR, no al
# sonar; al reproducir solo se escribía la ruta en el journal; y el botón del
# panel dejaba rastro en una `deque` EN MEMORIA que un reinicio borra. Si alguien
# preguntaba qué sonó el 19 de septiembre en la torre B, la única respuesta
# estaba en el journal de ese gabinete — y solo si nadie lo había rotado.


def test_el_simulacro_deja_en_su_ESTADO_que_va_a_sonar(settings):  # noqa: ANN001
    """El panel y el ack leen de aquí: una sola resolución, no dos."""
    from takab_edge.audio import AudioNotifier, SimulatedAudioBackend
    from takab_edge.drill import DrillController

    gpio = GpioController(settings)
    gpio.start()
    try:
        audio = AudioNotifier(
            settings.model_copy(update={"audio_simulacro_path": ""}),
            gpio=gpio,
            backend=SimulatedAudioBackend(),
            siren_backend=SimulatedAudioBackend(),
        )
        audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
        drill = DrillController(settings, gpio, audio=audio)

        ok, _ = drill.start_drill("DRILL-1", 5.0)
        assert ok
        estado = drill.status()
        assert estado["audio"]["asset_id"] == "takab-simulacro-v1"
        assert len(estado["audio"]["sha256"]) == 64
    finally:
        gpio.stop()


def test_sin_modulo_de_audio_el_simulacro_lo_DECLARA_en_vez_de_callar(settings):  # noqa: ANN001
    """Un simulacro sin voceo es legítimo (el banner vive igual); mudo, no.

    Sin esto, un `audio: null` y un «no había módulo» eran indistinguibles para
    quien lee el reporte al día siguiente.
    """
    from takab_edge.drill import DrillController

    gpio = GpioController(settings)
    gpio.start()
    try:
        drill = DrillController(settings, gpio, audio=None)
        assert drill.start_drill("DRILL-2", 5.0)[0]
        assert drill.status()["audio"]["reason"], "el hueco no se declaró"
        assert drill.status()["audio"]["sha256"] is None
    finally:
        gpio.stop()


def test_el_boton_del_panel_deja_fila_PERSISTIDA_no_solo_en_memoria(tmp_path, settings):  # noqa: ANN001
    """La `deque` de `_actions` la borra un reinicio. La bitácora local no."""
    from takab_edge.audio import AudioNotifier, SimulatedAudioBackend
    from takab_edge.audit import ActuationLedger
    from takab_edge.local_api import LocalDashboard

    gpio = GpioController(settings)
    gpio.start()
    try:
        audio = AudioNotifier(
            settings.model_copy(update={"audio_simulacro_path": ""}),
            gpio=gpio,
            backend=SimulatedAudioBackend(),
            siren_backend=SimulatedAudioBackend(),
        )
        audio.apply_audio_profile({"simulacro": "takab-simulacro-v1"})
        con_spool = settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")})
        ledger = ActuationLedger(con_spool)
        panel = LocalDashboard(gpio, None, None, audio=audio, ledger=ledger)

        panel.drill_audio()

        filas = ledger.read_all()
        vocea = [f for f in filas if f.get("action") == "drill_audio"]
        assert len(vocea) == 1, f"el botón no dejó fila persistida: {filas}"
        # Y la fila dice QUÉ sonó: sin el hash, la constancia no responde a nadie.
        assert "takab-simulacro-v1" in vocea[0]["detail"]
        assert audio.simulacro_evidence()["sha256"][:16] in vocea[0]["detail"]
    finally:
        gpio.stop()
