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

    # [T-9.71] Antes cambiaba al tono de PRUEBA, que ya no puede sonar en esta ranura.
    audio.apply_audio_profile({"simulacro": "takab-simulacro-v2"})
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


# ── el simulacro HABLADO (T-9.71 · D-41) ───────────────────────────────────
#
# D-41 sustituye, para `takab-simulacro-v2`, la regla de T-5.17 («un simulacro nunca
# suena a sismo»): ahora suena sobre el tono de ALERTA, y la voz es la única barrera
# para quien llegue tarde. Por eso el invariante se MIDE por energía sobre el fichero
# empaquetado, sin mirar cómo se generó: en las frecuencias del tono de alerta (se
# sacan de `siren.wav`, no se escriben aquí) y en el resto del espectro, en ventanas
# de 0,5 s cada 0,1 s. v1 sigue en el catálogo con su regla (arriba).
#
# ⚠️ El método supone un tono de alerta TONAL (el hi-lo de `takab-siren-v1`). Si
# T-9.70 elige un barrido, su energía se reparte y estas pruebas fallan: hay que
# regenerar el simulacro y rehacer la medida, no aflojar los umbrales.

_VENTANA_S = 0.5
_PASO_S = 0.1
_VOZ_SOLA_S = 2.5  # D-41


def _lee_wav(ruta: Path):  # noqa: ANN202
    import wave

    import numpy as np

    with wave.open(str(ruta), "rb") as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float) / 32768
    return x, sr


def _frecuencias_del_tono_de_alerta() -> list[float]:
    import numpy as np

    tono, sr = _lee_wav(catalog.resolve("takab-siren-v1"))
    espectro = np.abs(np.fft.rfft(tono * np.hanning(len(tono))))
    f = np.fft.rfftfreq(len(tono), 1 / sr)
    picos: list[float] = []
    for i in np.argsort(espectro)[::-1]:
        if all(abs(f[i] - p) > 20 for p in picos):
            picos.append(float(f[i]))
        if len(picos) == 2:
            return picos
    raise AssertionError("el tono de alerta no tiene dos picos")


@pytest.fixture(scope="module")
def ventanas():  # noqa: ANN201
    """(inicio_s, energía_en_el_tono_dB, energía_del_resto_dB) de cada ventana."""
    import numpy as np

    x, sr = _lee_wav(catalog.resolve("takab-simulacro-v2"))
    n, paso = int(_VENTANA_S * sr), int(_PASO_S * sr)
    f = np.fft.rfftfreq(4 * n, 1 / sr)
    banda = np.zeros_like(f, dtype=bool)
    for pico in _frecuencias_del_tono_de_alerta():
        banda |= np.abs(f - pico) <= 4
    filas = []
    for k in range(0, len(x) - n + 1, paso):
        p = np.abs(np.fft.rfft(x[k : k + n] * np.hanning(n), 4 * n)) ** 2
        filas.append(
            (
                k / sr,
                10 * np.log10(p[banda].sum() + 1e-20),
                10 * np.log10(p[~banda].sum() + 1e-20),
            )
        )
    return filas, len(x) / sr


def _nivel_del_tono(ventanas) -> float:  # noqa: ANN001
    import numpy as np

    filas, _ = ventanas
    return float(np.median([t for ini, t, _ in filas if ini >= _VOZ_SOLA_S]))


def _con_voz(ventanas) -> list[tuple[float, bool]]:  # noqa: ANN001
    """Hay voz donde el resto del espectro sobrepasa al tono en 6 dB o más."""
    filas, _ = ventanas
    tono = _nivel_del_tono(ventanas)
    return [(ini, resto >= tono + 6) for ini, _, resto in filas]


def _frases(ventanas) -> list[tuple[float, float]]:  # noqa: ANN001
    """(inicio, fin) de cada tramo seguido de ventanas con voz."""
    tramos: list[tuple[float, float]] = []
    for ini, voz in _con_voz(ventanas):
        if voz and tramos and ini - tramos[-1][1] <= _PASO_S + 1e-9:
            tramos[-1] = (tramos[-1][0], ini)
        elif voz:
            tramos.append((ini, ini))
    return tramos


def test_el_simulacro_hablado_esta_en_el_catalogo_y_es_otro_binario():
    ruta = catalog.resolve("takab-simulacro-v2")
    assert ruta is not None and ruta.is_file()
    digest = {
        cid: hashlib.sha256(catalog.resolve(cid).read_bytes()).hexdigest()
        for cid in ("takab-siren-v1", "takab-simulacro-v1", "takab-simulacro-v2")
    }
    assert len(set(digest.values())) == 3, f"dos tonos comparten binario: {digest}"


def test_nada_lo_elige_por_defecto():
    """Se enciende por la configuración firmada tras escucharlo (D-41), no solo."""
    from takab_edge.config.settings import AudioProfile, EdgeSettings

    assert AudioProfile().simulacro == ""
    assert "simulacro_hablado" not in EdgeSettings().audio_simulacro_path


def test_abre_con_VOZ_SOLA_sin_el_tono(ventanas):  # noqa: ANN001
    filas, _ = ventanas
    tono = _nivel_del_tono(ventanas)
    antes = [t for ini, t, _ in filas if ini + _VENTANA_S <= _VOZ_SOLA_S]
    assert antes, "no hay ventanas en la apertura"
    assert max(antes) <= tono - 10, (
        f"suena el tono en la apertura: {max(antes):.1f} dB frente a {tono:.1f} dB"
    )
    assert any(v for ini, v in _con_voz(ventanas) if ini + _VENTANA_S <= _VOZ_SOLA_S), (
        "la apertura no tiene voz"
    )


def test_despues_el_tono_suena_SIN_CORTES_hasta_el_final(ventanas):  # noqa: ANN001
    filas, duracion = ventanas
    tono = _nivel_del_tono(ventanas)
    # El último medio segundo se desvanece a propósito: termina en la voz.
    durante = [t for ini, t, _ in filas if _VOZ_SOLA_S <= ini <= duracion - 2 * _VENTANA_S]
    assert durante and min(durante) >= tono - 3, "el tono de alerta se corta a media pieza"


def test_la_voz_se_repite_al_menos_cuatro_veces_ENCIMA_del_tono(ventanas):  # noqa: ANN001
    sobre_el_tono = [f for f in _frases(ventanas) if f[0] >= _VOZ_SOLA_S]
    assert len(sobre_el_tono) >= 4, f"frases sobre el tono: {sobre_el_tono}"


def test_la_voz_va_15_dB_por_encima_del_tono(ventanas):  # noqa: ANN001
    """D-41: tono atenuado 15 dB. Se mide contra la voz de cada frase (el pico de la
    ventana, que es la que la cubre entera); 1,5 dB de tolerancia por el ventaneo."""
    filas, _ = ventanas
    tono = _nivel_del_tono(ventanas)
    for ini, fin in _frases(ventanas):
        if ini < _VOZ_SOLA_S:
            continue
        pico = max(resto for i, _, resto in filas if ini <= i <= fin)
        assert pico - tono >= 13.5, f"frase en {ini:.1f} s: sólo {pico - tono:.1f} dB"


def test_el_tono_nunca_suena_mas_de_3_5_s_sin_la_voz(ventanas):  # noqa: ANN001
    """«El precio» de D-41: quien llegue tarde oye un tono de alerta, y la voz es la
    única barrera. Ningún hueco entre frases, ni el final, lo deja solo más de 3,5 s."""
    _, duracion = ventanas
    frases = [f for f in _frases(ventanas)]
    huecos = [b[0] - a[1] - _VENTANA_S for a, b in zip(frases, frases[1:], strict=False)]
    huecos.append(duracion - frases[-1][1] - _VENTANA_S)
    assert max(huecos) <= 3.5, f"huecos sin voz (s): {[round(h, 2) for h in huecos]}"
    assert huecos[-1] <= 1.0, "no termina en la voz: lo último que se oye es el tono"


# ── cada tono, en SU ranura ────────────────────────────────────────────────
#
# La revisión adversaria de T-9.71: una config firmada con las ranuras cruzadas
# (`siren: takab-simulacro-v2`) se aplicaba sin queja, y en una alerta REAL el jack
# habría dicho «Esto es un simulacro». El hueco ya existía con v1 (un carillón en
# una alerta); con la voz, el audio equivocado niega la alerta en voz alta.


def test_todo_tono_del_catalogo_declara_su_ranura():
    """Sin ranura declarada no suena en ninguna: un id nuevo no puede colarse."""
    assert set(catalog.RANURAS) == set(catalog.CATALOG)


@pytest.mark.parametrize(
    ("ranura", "tono"),
    [
        ("siren", "takab-simulacro-v2"),
        ("siren", "takab-simulacro-v1"),
        ("simulacro", "takab-siren-v1"),
        ("test", "takab-simulacro-v2"),
    ],
)
def test_un_tono_en_la_ranura_equivocada_conserva_el_anterior_y_dice_por_que(audio, ranura, tono):  # noqa: ANN001
    antes = audio.apply_audio_profile({})
    reporte = audio.apply_audio_profile({ranura: tono})
    assert reporte["applied"] == {}
    assert reporte["rejected"] == {ranura: tono}
    assert ranura in reporte["wrong_slot"], reporte
    assert reporte[f"{ranura}_path"] == antes[f"{ranura}_path"]


def test_la_sirena_de_una_alerta_nunca_es_el_simulacro_hablado(audio):
    audio.apply_audio_profile({"siren": "takab-simulacro-v2", "simulacro": "takab-simulacro-v2"})
    reporte = audio.profile_report
    assert not reporte["siren_path"].endswith("simulacro_hablado.wav")
    assert reporte["simulacro_path"].endswith("simulacro_hablado.wav")


# ── la voz ES la voz auditada: entera y al derecho ─────────────────────────
#
# La energía no distingue una frase de un ruido con su misma envolvente, ni «Esto es
# un…» de «Esto es un simulacro.» (la revisión adversaria hizo pasar las cinco pruebas
# de arriba con la voz al revés, con ruido de banda vocal y con la frase truncada a
# 1 s). Aquí cada frase se busca por correlación normalizada contra el ingrediente
# del manifiesto: la frase real correlaciona 0,98 sobre el tono; la truncada, 0,81;
# la invertida y el ruido, menos de 0,5.

_VOZ_AUDITADA = Path(__file__).resolve().parents[2] / "shared/audio/fuentes/voz_simulacro.wav"
_CORRELACION_MIN = 0.95


def test_la_voz_auditada_es_la_frase_que_D41_pide():
    import json

    manifiesto = json.loads(
        (_VOZ_AUDITADA.parents[1] / "MANIFEST.json").read_text(encoding="utf-8")
    )
    (voz,) = [a for a in manifiesto["audios"] if a["id"] == "takab-voz-simulacro-v1"]
    assert voz["fuente"]["texto"] == "Esto es un simulacro."
    assert voz["sha256"] == hashlib.sha256(_VOZ_AUDITADA.read_bytes()).hexdigest()


def test_cada_frase_ES_la_voz_auditada_entera_y_al_derecho():
    import numpy as np

    x, sr = _lee_wav(catalog.resolve("takab-simulacro-v2"))
    v, sr_voz = _lee_wav(_VOZ_AUDITADA)
    assert sr == sr_voz, "el simulacro y su voz no comparten frecuencia de muestreo"
    n = len(v)
    largo = 1 << int(np.ceil(np.log2(len(x) + n)))
    cruce = np.fft.irfft(np.fft.rfft(x, largo) * np.fft.rfft(v[::-1], largo), largo)
    cruce = cruce[n - 1 : len(x)]
    acumulada = np.concatenate([[0.0], np.cumsum(x * x)])
    energia = acumulada[n:] - acumulada[: len(x) - n + 1]
    rho = cruce / (np.linalg.norm(v) * np.sqrt(np.maximum(energia, 1e-20)))

    inicios: list[float] = []
    while True:
        k = int(np.argmax(rho))
        if rho[k] < _CORRELACION_MIN:
            break
        inicios.append(k / sr)
        rho[max(0, k - n // 2) : k + n // 2] = 0.0
    inicios.sort()
    sola = [t for t in inicios if t + n / sr <= _VOZ_SOLA_S]
    encima = [t for t in inicios if t >= _VOZ_SOLA_S]
    assert sola and len(encima) >= 4, f"frases enteras encontradas en {inicios} s"
