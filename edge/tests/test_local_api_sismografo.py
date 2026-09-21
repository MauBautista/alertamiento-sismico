"""[T-7.23] Vista SISMÓGRAFO del panel del gabinete: los dos endpoints y su pantalla.

Lo que esta suite defiende, y por qué cada cosa lleva guarda propia:

- **El helicorder NO puede leer el fichero del día entero.** Medido en el gabinete
  el 2026-09-20: `obspy.read()` del EHZ del día (100.2 MB a media tarde) cuesta
  2.9 s y 159 MB de RSS pico; sobre uno de 287 MB, 8.75 s y 421 MB. El Pi 4 tiene
  905.7 MiB de RAM y ~260 MiB libres. Eso es exactamente lo que hace
  `RingBuffer.extract_window()`, así que aquí se exige **que no se llame** y que
  lo leído sea una fracción del fichero.
- **Los huecos se cortan y se declaran.** Ese mismo día el anillo cubría 20.93 h
  en SIETE tramos con SEIS huecos: una ventana de 1–6 h cruza un hueco casi con
  seguridad. Rellenar con ceros escribe «el suelo estuvo quieto» donde no hubo
  medición, dentro de la pantalla de un sismógrafo.
- **Nada de esto devuelve 500 ni 400 al kiosco.** Parámetro ilegal ⇒ default;
  módulo ausente, anillo ilegible o lectura ocupada ⇒ 200 con su razón escrita.
  Misma doctrina que `/api/waveform`, que nació del mismo problema.
- **Nada de esto toca la ruta de disparo.** Son lecturas de sólo lectura sobre
  RAM y disco; el proceso que sostiene los pines es otro (`takab-gpio`).

El miniSEED se FABRICA en el anillo temporal del supervisor: el anillo del
gabinete real no se toca desde una suite. Y el reloj de las pruebas con dato es
FIJO —se le pasa `ahora=` al método— porque una ventana anclada en
`datetime.now()` cruza la medianoche una vez al día y el fallo saldría a las 00:10
de la mañana en el CI de otra persona.
"""

from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
import textwrap
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from takab_edge.local_api import sismografo
from tests.test_local_api import _get
from tests.test_local_api_panel import _base, _hidden, _node, _render, _txt

#: Reloj fijo de las pruebas con dato en disco. Un mediodía cualquiera: lejos de
#: la medianoche para que una ventana de 6 h quepa en el fichero de un solo día,
#: salvo donde el cruce ES lo que se está probando.
AHORA = datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC)

_INDEX = Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "index.html"


# ---------------------------------------------------------------- utilidades


def _fabricar(
    root: Path,
    canal: str,
    inicio: datetime,
    duracion_s: float,
    *,
    paso_s: float = 1.0,
    amplitud: int = 1000,
    sr: float = 100.0,
    pico: tuple[float, int] | None = None,
    red: str = "AM",
    estacion: str = "R4F74",
    loc: str = "00",
) -> list[Path]:
    """Escribe dato continuo en el anillo, repartido por fichero de DÍA.

    Cada paquete cae en el fichero de su propia fecha, igual que hace
    `RingBuffer.append`, así que un tramo que cruza la medianoche se parte solo.
    `paso_s` grande = menos escrituras (una prueba que fabrica 3 h a paquetes de
    1 s tarda más en montar el escenario que en medirlo).
    `pico` es `(desplazamiento_s, valor)`: una única muestra alta, para que el
    mín/máx tenga algo que conservar.
    """
    from obspy import Stream, Trace, UTCDateTime

    tocados: list[Path] = []
    npts = int(round(sr * paso_s))
    k = 0
    while k * paso_s < duracion_s:
        arranque = inicio + timedelta(seconds=k * paso_s)
        muestras = np.full(npts, amplitud, dtype=np.int32)
        if pico is not None:
            desplazamiento, valor = pico
            indice = int(round((desplazamiento - k * paso_s) * sr))
            if 0 <= indice < npts:
                muestras[indice] = valor
        traza = Trace(muestras)
        traza.stats.network, traza.stats.station = red, estacion
        traza.stats.location, traza.stats.channel = loc, canal
        traza.stats.sampling_rate = sr
        traza.stats.starttime = UTCDateTime(arranque)
        buf = io.BytesIO()
        Stream([traza]).write(buf, format="MSEED")
        ruta = root / f"{red}.{estacion}.{loc}.{canal}.{arranque.strftime('%Y%m%d')}.mseed"
        with open(ruta, "ab") as fh:
            fh.write(buf.getvalue())
        if ruta not in tocados:
            tocados.append(ruta)
        k += 1
    return tocados


def _paquete(canal: str, muestras: np.ndarray, inicio: datetime, sr: float = 100.0):
    from takab_edge.contracts import WaveformPacket

    return WaveformPacket(
        network="AM",
        station="R4F74",
        location="00",
        channel=canal,
        sample_rate=sr,
        starttime=inicio,
        samples=[int(v) for v in muestras],
    )


def _alimentar_anillo(
    ring, canal: str, segundos: int, freq_hz: float, amplitud: int, offset: int = 0
) -> datetime:
    """Mete un tono puro en el anillo de RAM, un paquete de 1 s cada vez.

    `offset` es la CONTINUA que lleva encima. Por defecto cero, que es lo que
    hacía que borrar la resta de la media pasase desapercibido: el dato real
    del acelerómetro lleva ~1 g de continua.
    """
    sr = 100.0
    t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    n = int(round(sr))
    for k in range(segundos):
        t = (np.arange(n) + k * n) / sr
        muestras = np.rint(amplitud * np.sin(2 * np.pi * freq_hz * t)).astype(np.int32) + offset
        ring.append(_paquete(canal, muestras.astype(np.int32), t0 + timedelta(seconds=k), sr))
    return t0


def _json(supervisor, path: str) -> dict:
    code, body = _get(supervisor.local_api, path)
    assert code == 200, f"{path} devolvió {code}: el kiosco no puede recibir otra cosa"
    return json.loads(body)


def _raiz(supervisor) -> Path:
    return Path(supervisor.buffer.root)


# ====================================================== /api/spectrogram


def test_el_espectrograma_encuentra_el_tono_que_se_le_metio(supervisor):
    """Guarda de NO-VACUIDAD del eje de frecuencias: 12 Hz dentro, 12 Hz fuera.

    Sin esto, una matriz de ceros con la forma correcta pasaría por
    espectrograma. La tolerancia es la resolución que da la propia ventana
    (`fs/nperseg` ≈ 0.78 Hz a 128), no un número elegido a ojo.
    """
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 30, freq_hz=12.0, amplitud=20000)

    payload = _json(supervisor, "/api/spectrogram?channel=EHZ&nperseg=128")

    assert payload["degraded"] is False and payload["reason"] is None
    assert payload["channel"] == "EHZ"
    filas = np.array(payload["rows"], dtype=np.uint8)
    assert filas.shape == (len(payload["freq_hz"]), len(payload["t_offset_s"]))
    pico_hz = payload["freq_hz"][int(np.argmax(filas.mean(axis=1)))]
    resolucion = payload["sample_rate"] / payload["nperseg"]
    assert abs(pico_hz - 12.0) <= resolucion, (
        f"el pico del espectrograma cayó en {pico_hz} Hz con un tono de 12 Hz dentro"
    )


def test_la_escala_en_db_es_fija_y_no_se_reajusta_en_cada_peticion(supervisor):
    """Una escala automática haría que dos columnas de minutos distintos mintieran.

    Se pide el mismo canal con un tono DIEZ veces más fuerte: los límites en dB
    tienen que ser los MISMOS y el valor pintado tiene que SUBIR. Con una matriz
    normalizada por petición, las dos saldrían casi idénticas.
    """
    anillo = supervisor.signal.waveform
    _alimentar_anillo(anillo, "ENZ", 25, freq_hz=8.0, amplitud=2000)
    flojo = _json(supervisor, "/api/spectrogram?channel=ENZ")
    _alimentar_anillo(anillo, "ENZ", 25, freq_hz=8.0, amplitud=20000)
    fuerte = _json(supervisor, "/api/spectrogram?channel=ENZ")

    assert flojo["db_min"] == fuerte["db_min"]
    assert flojo["db_max"] == fuerte["db_max"]
    assert np.array(fuerte["rows"]).max() > np.array(flojo["rows"]).max(), (
        "subir la amplitud 10× no subió el valor pintado: la escala se reajusta "
        "por petición y dos columnas de minutos distintos ya no comparan"
    )


def test_la_matriz_es_uint8_acotada_y_cuenta_lo_que_se_sale(supervisor):
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 20, freq_hz=5.0, amplitud=8_000_000)
    payload = _json(supervisor, "/api/spectrogram?channel=EHZ")
    plano = np.array(payload["rows"]).ravel()
    assert plano.min() >= 0 and plano.max() <= 255
    assert payload["below_scale"] + payload["above_scale"] <= plano.size
    assert payload["above_scale"] > 0, (
        "un tono a fondo de escala del ADC tiene que salirse por arriba: si no, "
        "los límites en dB no están donde dicen"
    )


def test_un_nperseg_ilegal_cae_al_default_y_jamas_da_400(supervisor):
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 20, freq_hz=5.0, amplitud=5000)
    for ilegal in ("nperseg=7", "nperseg=hola", "nperseg=-3", "nperseg=1000000"):
        assert _json(supervisor, f"/api/spectrogram?channel=EHZ&{ilegal}")["nperseg"] == 128, ilegal
    assert _json(supervisor, "/api/spectrogram?channel=EHZ&nperseg=256")["nperseg"] == 256


def test_un_canal_que_el_anillo_no_tiene_se_sustituye_y_se_declara(supervisor):
    """El kiosco no recibe un 400: recibe otro canal Y el aviso de la sustitución."""
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 20, freq_hz=5.0, amplitud=5000)
    payload = _json(supervisor, "/api/spectrogram?channel=ZZZ")
    assert payload["requested_channel"] == "ZZZ"
    assert payload["channel"] == "EHZ"


def test_sin_muestras_el_espectrograma_degrada_con_200_y_su_razon(supervisor):
    payload = _json(supervisor, "/api/spectrogram?channel=EHZ")
    assert payload["degraded"] is True
    assert payload["reason"] and payload["reason"] != "ok"
    assert payload["rows"] == []


def test_sin_modulo_de_senal_el_espectrograma_sigue_respondiendo_200(supervisor):
    supervisor.local_api._signal = None
    payload = _json(supervisor, "/api/spectrogram?channel=EHZ")
    assert payload["degraded"] is True and payload["reason"] == "sin_modulo_de_senal"
    assert payload["rows"] == []


def test_con_menos_muestras_que_una_ventana_fft_se_declara(supervisor):
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 1, freq_hz=5.0, amplitud=5000)
    payload = _json(supervisor, "/api/spectrogram?channel=EHZ&nperseg=256")
    assert payload["degraded"] is True
    assert payload["reason"] == "muestras_insuficientes"


def test_el_espectrograma_no_publica_ni_sondea(supervisor, monkeypatch):
    """Hermano de `test_waveform_does_not_publish_nor_probe`: esto es SOLO LAN."""
    fugas: list = []
    supervisor.health.on_snapshot(fugas.append)
    monkeypatch.setattr(supervisor.cloud, "publish", lambda *a, **k: fugas.append(a))
    _alimentar_anillo(supervisor.signal.waveform, "EHZ", 10, freq_hz=6.0, amplitud=4000)
    for _ in range(5):
        assert _get(supervisor.local_api, "/api/spectrogram?channel=EHZ")[0] == 200
    assert fugas == []


# ======================================================== /api/helicorder


def test_el_helicorder_corta_por_hueco_y_lo_declara(supervisor):
    """Tres tramos con dos huecos: tres `segments` y dos `gaps`, jamás uno solo.

    Es la forma REAL del anillo del gabinete (siete tramos, seis huecos el
    2026-09-20), reducida a lo mínimo que la reproduce.
    """
    raiz = _raiz(supervisor)
    _fabricar(raiz, "EHZ", AHORA - timedelta(minutes=30), 60)
    _fabricar(raiz, "EHZ", AHORA - timedelta(minutes=30) + timedelta(seconds=180), 60)
    _fabricar(raiz, "EHZ", AHORA - timedelta(minutes=30) + timedelta(seconds=420), 60)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)

    assert payload["degraded"] is False, payload["reason"]
    assert len(payload["segments"]) == 3, payload["segments"]
    huecos = sorted(round(g["seconds"]) for g in payload["gaps"])
    assert 120 in huecos and 180 in huecos, huecos


def test_el_helicorder_no_rellena_el_hueco_con_nada(supervisor):
    """La suma de lo servido NO puede cubrir la ventana: el hueco es hueco.

    Un relleno con ceros o una interpolación entre tramos se delatan aquí — el
    total de buckets se acercaría a los segundos de la ventana en vez de quedarse
    en los del dato que de verdad existe— y además ningún tramo puede, él solo,
    abarcar el hueco.
    """
    raiz = _raiz(supervisor)
    _fabricar(raiz, "EHZ", AHORA - timedelta(minutes=30), 60)
    _fabricar(raiz, "EHZ", AHORA - timedelta(minutes=20), 60)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    total = sum(s["buckets"] for s in payload["segments"])
    assert 115 <= total <= 125, f"{total} buckets para 120 s de dato real"
    assert all(s["buckets"] <= 65 for s in payload["segments"]), payload["segments"]


def test_el_helicorder_conserva_el_pico_en_el_par_minmax(supervisor):
    """Un submuestreo ingenuo se salta el pico; el mín/máx por bucket no.

    Una sola muestra alta en 60 s: con `samples[::100]` la probabilidad de
    cazarla sería 1/100.
    """
    _fabricar(
        _raiz(supervisor),
        "ENZ",
        AHORA - timedelta(minutes=10),
        60,
        amplitud=10,
        pico=(30.57, 99_999),
    )
    payload = supervisor.local_api.helicorder("ENZ", 1.0, ahora=AHORA)
    maximos = [v for s in payload["segments"] for v in s["minmax"][1::2]]
    assert max(maximos) == 99_999, "el pico se perdió: el bucket no es un mín/máx"
    minimos = [v for s in payload["segments"] for v in s["minmax"][0::2]]
    assert min(minimos) == 10, "el mínimo tampoco se conserva"


def test_el_helicorder_lee_solo_la_cola_del_anillo(supervisor):
    """Lo medido: leer el día entero cuesta 2.9 s y 159 MB. Aquí se exige que no.

    Dos afirmaciones, porque cada una puede fallar por su cuenta: `bytes_read`
    tiene que ser una fracción del fichero, y `RingBuffer.extract_window` —el
    camino que SÍ lee el día entero— no puede llegar a llamarse ni una vez.
    """
    rutas = _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(hours=3), 3 * 3600, paso_s=60)
    tamano = rutas[0].stat().st_size

    def _prohibido(*_a, **_k):
        raise AssertionError("el helicorder llamó a extract_window: lee el día ENTERO")

    supervisor.buffer.extract_window = _prohibido  # type: ignore[method-assign]

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is False, payload["reason"]
    assert 0 < payload["bytes_read"] < tamano * 0.6, (
        f"leyó {payload['bytes_read']} de {tamano} B: eso no es leer la cola"
    )


def test_las_horas_se_acotan_a_la_banda_declarada(supervisor):
    """La cota no es estética: es el presupuesto de RAM de un Pi con 905.7 MiB."""
    for pedido, servido in (("0.1", 1.0), ("99", 6.0), ("hola", 1.0), ("3", 3.0)):
        payload = _json(supervisor, f"/api/helicorder?channel=EHZ&hours={pedido}")
        assert payload["hours"] == servido, (pedido, payload["hours"])
    assert _json(supervisor, "/api/helicorder?hours=99")["requested_hours"] == 99.0
    assert _json(supervisor, "/api/helicorder?hours=hola")["requested_hours"] is None


def test_el_helicorder_encadena_el_fichero_del_dia_anterior(supervisor):
    """Una ventana que cruza la medianoche no puede perder la mitad de abajo."""
    medianoche = datetime(2026, 9, 20, 0, 30, 0, tzinfo=UTC)
    _fabricar(_raiz(supervisor), "EHZ", medianoche - timedelta(minutes=50), 50 * 60, paso_s=10)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=medianoche)
    assert payload["degraded"] is False, payload["reason"]
    assert len(payload["files"]) == 2, payload["files"]
    total = sum(s["buckets"] for s in payload["segments"])
    assert total >= 2900, f"{total} buckets: se perdió el tramo del día anterior"


def test_sin_ficheros_del_canal_el_helicorder_degrada_con_200(supervisor):
    payload = _json(supervisor, "/api/helicorder?channel=EHZ")
    assert payload["degraded"] is True
    assert payload["reason"] and payload["reason"] != "ok"
    assert payload["segments"] == []


def test_con_el_anillo_mudo_en_esa_ventana_se_declara_en_vez_de_servir_vacio(supervisor):
    """Hay fichero y se leyó, pero la ventana no tiene ni una muestra.

    Servir eso como respuesta buena con `segments: []` dejaría la tarjeta
    diciendo «0 huecos declarados» sobre una pantalla en blanco: el operador
    leería «todo bien» donde lo que hay es «el sensor lleva horas callado».
    """
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(hours=5), 60)
    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is True
    assert payload["reason"] == "sin_dato_en_la_ventana"


def test_sin_modulo_de_anillo_el_helicorder_sigue_respondiendo_200(supervisor):
    supervisor.local_api._buffer = None
    payload = _json(supervisor, "/api/helicorder?channel=EHZ")
    assert payload["degraded"] is True and payload["reason"] == "sin_anillo"


def test_un_anillo_ilegible_se_declara_en_vez_de_reventar(supervisor):
    ruta = _raiz(supervisor) / f"AM.R4F74.00.EHZ.{AHORA.strftime('%Y%m%d')}.mseed"
    ruta.write_bytes(b"esto no es miniSEED" * 1000)
    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is True
    assert payload["reason"] == "anillo_ilegible"


def test_dos_lecturas_a_la_vez_la_segunda_declara_ocupado(supervisor):
    """Tres kioscos abiertos no pueden multiplicar por tres el coste del gabinete."""
    from takab_edge.local_api import sismografo

    entro, suelta = threading.Event(), threading.Event()
    original = sismografo.helicorder

    def _lento(*args, **kwargs):
        entro.set()
        suelta.wait(5)
        return original(*args, **kwargs)

    sismografo.helicorder = _lento  # type: ignore[assignment]
    try:
        hilo = threading.Thread(
            target=supervisor.local_api.helicorder, args=("EHZ", 1.0), kwargs={"ahora": AHORA}
        )
        hilo.start()
        assert entro.wait(5), "la primera lectura no llegó a entrar"
        segunda = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
        suelta.set()
        hilo.join(10)
    finally:
        sismografo.helicorder = original  # type: ignore[assignment]
    assert segunda["degraded"] is True and segunda["reason"] == "ocupado"


def test_el_presupuesto_de_bytes_recorta_por_el_principio_y_lo_declara(supervisor, monkeypatch):
    """Cuando el presupuesto muerde se conserva lo NUEVO, y se dice que se recortó."""
    from takab_edge.local_api import sismografo

    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=50), 50 * 60, paso_s=10)
    # A 10 s por registro de 4096 B, 30 registros ≈ 300 s: muerde sobre 1 h.
    monkeypatch.setattr(sismografo, "PRESUPUESTO_BYTES", 30 * 4096)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["truncated"] is True
    assert payload["truncated_reason"] == "presupuesto"
    assert payload["bytes_read"] <= 30 * 4096
    assert sum(s["buckets"] for s in payload["segments"]) < 3000


def test_cuando_el_anillo_no_llega_tan_atras_se_dice_que_es_el_anillo(supervisor):
    """`presupuesto` y `anillo` son dos hechos distintos y el operador los separa."""
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=5), 120)
    payload = supervisor.local_api.helicorder("EHZ", 6.0, ahora=AHORA)
    assert payload["truncated"] is True
    assert payload["truncated_reason"] == "anillo"


def test_el_helicorder_no_publica_ni_sondea(supervisor, monkeypatch):
    fugas: list = []
    supervisor.health.on_snapshot(fugas.append)
    monkeypatch.setattr(supervisor.cloud, "publish", lambda *a, **k: fugas.append(a))
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=3), 60)
    for _ in range(3):
        assert _get(supervisor.local_api, "/api/helicorder?channel=EHZ&hours=1")[0] == 200
    assert fugas == []


# ==================================================== identidad de estación


def test_status_publica_la_identidad_completa_sin_tocar_station_code(supervisor):
    """`station_code` es contrato con la nube: la identidad completa va APARTE."""
    st = supervisor.local_api.status()
    ajustes = supervisor.settings
    assert st["station_code"] == f"{ajustes.seedlink_network}.{ajustes.seedlink_station_code}"
    esperado = [
        f"{ajustes.seedlink_network}.{ajustes.seedlink_station_code}"
        f".{ajustes.seedlink_location}.{canal}"
        for canal in ajustes.seedlink_channels
    ]
    assert st["station_nslc"] == esperado
    assert all(codigo.count(".") == 3 for codigo in st["station_nslc"])


def test_la_identidad_completa_se_deriva_de_los_ajustes_una_sola_vez():
    """Dos sitios que compongan el mismo código acabarían divergiendo."""
    from takab_edge.config import EdgeSettings

    ajustes = EdgeSettings(
        seedlink_network="AM",
        seedlink_station="R4F74",
        seedlink_location="00",
        seedlink_channels=["EHZ", "ENZ"],
    )
    assert ajustes.seedlink_nslc == ["AM.R4F74.00.EHZ", "AM.R4F74.00.ENZ"]


# ============================================================ la pantalla


def _status_con_identidad() -> dict:
    st = _base()
    st["station_nslc"] = ["AM.R4F74.00.EHZ", "AM.R4F74.00.ENZ"]
    return st


def _heli_payload(**extra) -> dict:
    payload = {
        "degraded": False,
        "reason": None,
        "channel": "EHZ",
        "requested_channel": "EHZ",
        "hours": 1.0,
        "requested_hours": 1.0,
        "window_start": "2026-08-04T09:00:00+00:00",
        "window_end": "2026-08-04T10:00:00+00:00",
        "sample_rate": 100.0,
        "bucket_s": 1.0,
        # [T-7.23 · V2] Los cuatro campos de la edad, con el sensor AL DÍA por
        # defecto: el caso raro se pide, no se hereda.
        "last_sample_at": "2026-08-04T09:59:59+00:00",
        "age_s": 1.0,
        "stale": False,
        # [T-7.23 · Q1] El umbral se LEE del servidor y no se teclea: tecleado,
        # esta fixture seguiría diciendo 10 s el día que el servidor cambie y
        # las guardas de la pantalla medirían un panel que no existe.
        "stale_after_s": sismografo.RANCIO_HELI_S,
        "segments": [
            {
                "start": "2026-08-04T09:00:00+00:00",
                "buckets": 3,
                "dc_counts": 0.0,
                "minmax": [-5, 5, -7, 7, -3, 3],
            },
            {
                "start": "2026-08-04T09:30:00+00:00",
                "buckets": 2,
                "dc_counts": 0.0,
                "minmax": [-9, 9, -2, 2],
            },
        ],
        "gaps": [
            {
                "start": "2026-08-04T09:00:03+00:00",
                "end": "2026-08-04T09:30:00+00:00",
                "seconds": 1797.0,
            }
        ],
        "bytes_read": 40960,
        "files": ["AM.R4F74.00.EHZ.20260804.mseed"],
        "truncated": False,
        "truncated_reason": None,
        # [T-7.23 · Q2] El anillo sano por defecto: la advertencia se pide.
        "ring_unordered": False,
    }
    payload.update(extra)
    return payload


def _spec_payload(**extra) -> dict:
    filas = [[10, 40, 90], [200, 30, 5]]
    payload = {
        "degraded": False,
        "reason": None,
        "channel": "EHZ",
        "requested_channel": "EHZ",
        "sample_rate": 100.0,
        "nperseg": 128,
        "noverlap": 64,
        "window": "hann",
        "freq_hz": [0.0, 25.0],
        "t_offset_s": [0.0, 1.0, 2.0],
        "first_sample_at": "2026-08-04T09:59:00+00:00",
        "gap_before": False,
        "dc_counts": 12.0,
        "db_min": -20.0,
        "db_max": 130.0,
        "rows": filas,
        "below_scale": 0,
        "above_scale": 0,
    }
    payload.update(extra)
    return payload


def test_la_vista_sismografo_se_enciende_y_esconde_la_rejilla(tmp_path):
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=sismografo")
    assert _hidden(out, "grid") is True
    assert _hidden(out, "sismo") is False


def test_la_vista_por_defecto_no_cambia(tmp_path):
    """El censo de render mide la vista por defecto: moverla movería la vara."""
    out = _render(tmp_path, status=_status_con_identidad())
    assert _hidden(out, "grid") is False
    assert _hidden(out, "sismo") is True


def test_una_vista_desconocida_cae_a_la_de_siempre_y_lo_declara(tmp_path):
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=loquesea")
    assert _hidden(out, "grid") is False
    assert "NO EXISTE" in _txt(out, "hdr-meta")
    assert "loquesea" in _txt(out, "hdr-meta")


def test_la_tarjeta_de_estacion_pinta_la_identidad_completa_y_su_calibracion(tmp_path):
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=sismografo")
    texto = _txt(out, "sismo-station")
    assert "AM.R4F74.00.EHZ" in texto
    assert "AM.R4F74.00.ENZ" in texto
    assert _base()["calibration"]["source"] in texto


def test_sin_identidad_provisionada_la_tarjeta_lo_declara_en_vez_de_callar(tmp_path):
    st = _status_con_identidad()
    st["station_nslc"] = []
    out = _render(tmp_path, status=st, search="?view=sismografo")
    assert "S/D" in _txt(out, "sismo-station")


def test_sin_calibrar_la_tarjeta_de_estacion_lo_dice(tmp_path):
    st = _status_con_identidad()
    st["calibration"] = {
        "calibrated": False,
        "source": None,
        "vel_sensitivity_ms_per_count": None,
        "accel_sensitivity_ms2_per_count": None,
    }
    out = _render(tmp_path, status=st, search="?view=sismografo")
    assert "SIN CALIBRAR" in _txt(out, "sismo-station").upper()


def test_en_la_vista_por_defecto_no_se_pide_ni_espectrograma_ni_helicorder(tmp_path):
    """Coste cero para el 99.9 % de la vida del panel."""
    out = _render(tmp_path, status=_status_con_identidad(), clicks=["tick", "tick"])
    urls = " ".join(f["url"] for f in out["fetches"])
    assert "api/spectrogram" not in urls
    assert "api/helicorder" not in urls


def test_la_vista_sismografo_no_pide_waveform_y_si_pide_los_suyos(tmp_path):
    """Pedir las dos cosas sería pagar dos veces por el mismo anillo de 60 s."""
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=sismografo")
    urls = [f["url"] for f in out["fetches"]]
    assert any("api/spectrogram" in u for u in urls), urls
    assert any("api/helicorder" in u for u in urls), urls
    assert not any("api/waveform" in u for u in urls), urls


def test_el_helicorder_no_se_repide_en_cada_tick(tmp_path):
    """0.89 s de disco por petición: a 1 Hz sería el 89 % de un núcleo del Pi."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        clicks=["tick", "tick", "tick"],
    )
    urls = [f["url"] for f in out["fetches"]]
    assert sum("api/helicorder" in u for u in urls) == 1, urls
    assert sum("api/spectrogram" in u for u in urls) == 4, urls


def test_el_helicorder_declara_su_edad_porque_por_diseno_llega_viejo(tmp_path):
    """Puede tener 60 s: un dato viejo pintado como vivo es peor que «sin datos»."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
    )
    assert "CALCULADO HACE" in _txt(out, "sismo-heli-meta")


def test_el_helicorder_nombra_sus_huecos_en_la_pantalla(tmp_path):
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
    )
    assert "1 HUECO" in _txt(out, "sismo-heli-meta").upper()


def test_un_helicorder_recortado_lo_dice_con_su_causa(tmp_path):
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(truncated=True, truncated_reason="anillo"),
    )
    texto = _txt(out, "sismo-heli-meta").upper()
    assert "RECORTADO" in texto and "ANILLO" in texto


def test_el_helicorder_degradado_se_declara_con_su_razon(tmp_path):
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(degraded=True, reason="ocupado", segments=[], gaps=[]),
    )
    texto = _txt(out, "sismo-heli-meta").upper()
    assert "SIN HELICORDER" in texto
    # [T-7.23 · M3] La razón llega en snake_case desde la API y el muro la
    # imprimía así. Lo que tiene que leerse de pie es la FRASE.
    assert "OTRA LECTURA DEL ANILLO EN CURSO" in texto
    assert "OCUPADO" not in texto


def test_el_espectrograma_declara_su_escala_fija_en_pantalla(tmp_path):
    """Si no se rotula el rango, el color no significa nada medible."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(),
    )
    texto = _txt(out, "sismo-spec-meta")
    assert "-20" in texto and "130" in texto and "dB" in texto


def test_el_espectrograma_degradado_se_declara_con_su_razon(tmp_path):
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(
            degraded=True,
            reason="canal_sin_muestras",
            channel=None,
            rows=[],
            freq_hz=[],
            t_offset_s=[],
        ),
    )
    texto = _txt(out, "sismo-spec-meta").upper()
    assert "SIN ESPECTROGRAMA" in texto
    assert "EL ANILLO DE RAM NO TIENE ESE CANAL" in texto
    assert "CANAL_SIN_MUESTRAS" not in texto


def test_un_canal_sustituido_se_nombra_por_el_que_se_sirvio(tmp_path):
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(channel="ENZ", requested_channel="ZZZ"),
    )
    texto = _txt(out, "sismo-spec-meta")
    assert "ENZ" in texto and "ZZZ" in texto


def test_la_vista_nueva_no_anade_ni_una_peticion_a_internet():
    """El veto del panel vale igual para el marcado nuevo."""
    html = _INDEX.read_text("utf-8")
    assert 'id="sismo"' in html, "la vista sismógrafo no existe en el marcado"
    for vetado in ("https://", "http://", "localStorage", "EventSource", "new WebSocket"):
        assert vetado not in html, vetado
    assert "setInterval" not in html
    assert html.count("setTimeout(tick") == 1


def test_la_vista_nueva_no_anade_movimiento():
    """El inventario de movimiento sigue siendo dos keyframes y cero transiciones."""
    hoja = re.sub(r"/\*[\s\S]*?\*/", "", _INDEX.read_text("utf-8"))
    assert set(re.findall(r"@keyframes ([a-z-]+)", hoja)) == {"tk-blink", "tk-pulse"}
    assert re.findall(r"transition:\s*([a-z-]+)", hoja) == ["none"]


def test_el_nodo_de_la_vista_existe_en_el_arbol(tmp_path):
    """Guarda del arnés: si el id no se parsea, todo lo de arriba sería verde falso."""
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=sismografo")
    assert _node(out["tree"], "sismo")["id"] == "sismo"
    assert _node(out["tree"], "sismo-station")["id"] == "sismo-station"


def test_los_lienzos_se_repintan_por_dato_y_no_por_fotograma(tmp_path):
    """El espectrograma son ~6000 celdas: repintarlas a 60 fps sería quemar el
    kiosco para enseñar exactamente la misma imagen.

    El arnés devuelve la geometría del ÚLTIMO fotograma, así que con dos
    fotogramas seguidos y nada que cambie entre medias la respuesta es directa:
    el primero tiene que pintar los dos lienzos y el segundo, ninguno. Las dos
    mitades van en el mismo test porque cada una sola daría un verde falso — un
    panel que no dibujara nada pasaría la segunda.
    """
    comun = {
        "status": _status_con_identidad(),
        "search": "?view=sismografo",
        "spectrogram": _spec_payload(),
        "helicorder": _heli_payload(),
        "canvasOps": True,
    }
    primero = _render(tmp_path, frames=1, **comun)
    pintados = {op["lienzo"] for op in primero["canvasOps"]}
    assert {"spec-canvas", "heli-canvas"} <= pintados, (
        f"el primer fotograma no pintó los dos lienzos: {sorted(pintados)}"
    )

    segundo = _render(tmp_path, frames=2, **comun)
    repintados = {op["lienzo"] for op in segundo["canvasOps"]}
    assert not ({"spec-canvas", "heli-canvas"} & repintados), (
        "el segundo fotograma vuelve a pintar sin que haya llegado dato nuevo: "
        f"{sorted(repintados)}"
    )


@pytest.mark.parametrize("lienzo", ["spec-canvas", "heli-canvas"])
def test_los_dos_lienzos_estan_en_el_arbol(tmp_path, lienzo):
    out = _render(tmp_path, status=_status_con_identidad(), search="?view=sismografo")
    assert _node(out["tree"], lienzo)["tag"] == "CANVAS"


# ============================== [T-7.23 · A1] el coste de scipy


def test_scipy_signal_no_esta_cargado_tras_el_arranque_y_su_import_no_es_gratis():
    """La afirmación «importar `scipy.signal` cuesta 0 MB» era FALSA. Aquí se mide.

    De dónde salía el error: alguien miró `/proc/<pid>/maps` del proceso vivo,
    vio `scipy` y concluyó que `scipy.signal` ya estaba dentro. Lo que `obspy`
    arrastra es `scipy.integrate` y `scipy.fft`. Esta guarda comprueba las dos
    mitades de la corrección:

    - tras cargar lo que carga el arranque del edge, `scipy.signal` NO está en
      `sys.modules` — es decir, el import del espectrograma sigue siendo
      perezoso y sigue habiendo una primera vez que lo paga;
    - y ese import NO es gratis en RSS, que es justo lo que la prosa decía.

    Va en un SUBPROCESO porque dentro de la suite cualquier otro test podría
    haber importado `scipy.signal` antes y la primera mitad saldría verde por
    contaminación. El umbral es deliberadamente flojo (5 MB frente a los 24.3
    medidos): lo que se defiende es «no es cero», no una cifra concreta de un
    equipo concreto.
    """
    if not sys.platform.startswith("linux"):  # pragma: no cover - el edge es Linux
        pytest.skip("el RSS se lee de /proc; el gabinete y el CI son Linux")
    guion = textwrap.dedent(
        """
        import json, sys, os
        # RSS ACTUAL, no el pico: `ru_maxrss` es una marca de agua que ya la
        # subieron los imports de arriba y se queda quieta aunque scipy.signal
        # reserve 24 MB nuevos (medido: daba 0.0 MB y la guarda no mordía).
        PAGINA = os.sysconf("SC_PAGE_SIZE")
        def rss_mb():
            with open("/proc/self/statm") as fh:
                return int(fh.read().split()[1]) * PAGINA / (1024 * 1024)
        import takab_edge.supervisor            # noqa
        from takab_edge.local_api import sismografo  # noqa
        import obspy                            # noqa
        from obspy.io.mseed.util import get_record_information  # noqa
        antes_cargado = "scipy.signal" in sys.modules
        base = rss_mb()
        from scipy import signal                # noqa
        print(json.dumps({
            "ya_estaba": antes_cargado,
            "scipy": "scipy" in sys.modules,
            "base_mb": base,
            "delta_mb": rss_mb() - base,
        }))
        """
    )
    salida = subprocess.run(  # noqa: S603 — intérprete propio, guion propio
        [sys.executable, "-c", guion],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert salida.returncode == 0, salida.stderr[-2000:]
    medido = json.loads(salida.stdout.strip().splitlines()[-1])
    assert medido["scipy"] is True, "ni siquiera `scipy` se cargó: la medida no dice nada"
    assert medido["ya_estaba"] is False, (
        "`scipy.signal` YA estaba cargado tras el arranque del edge. O alguien lo "
        "importó arriba del todo en un módulo del arranque —y entonces los +24 MB "
        "los paga TODO gabinete, abra o no la vista sismógrafo—, o `obspy` cambió "
        "y hay que re-medir la cifra del docstring de `sismografo.py`."
    )
    assert medido["delta_mb"] > 5.0, (
        f"importar `scipy.signal` movió el RSS sólo {medido['delta_mb']:.1f} MB: si "
        "de verdad pasó a ser casi gratis, la cifra de 24.3 MB del docstring y la "
        "cuenta del presupuesto de `PRESUPUESTO_BYTES` están obsoletas y hay que "
        "re-escribirlas con lo medido."
    )


# ====================================== [T-7.23 · A2] la edad del espectrograma


def test_el_espectrograma_declara_la_edad_de_su_dato(supervisor):
    """`WaveformRing` sólo poda al appendear: sin edad, el rancio se ve igual."""
    t0 = _alimentar_anillo(supervisor.signal.waveform, "EHZ", 20, freq_hz=6.0, amplitud=4000)
    # La última muestra cae en t0 + 19.99 s; el reloj se pone 4 s después.
    ahora = t0 + timedelta(seconds=24)
    payload = supervisor.local_api.spectrogram("EHZ", 128, ahora=ahora)

    assert payload["degraded"] is False
    assert payload["stale"] is False
    assert 3.9 <= payload["age_s"] <= 4.1, payload["age_s"]
    assert payload["last_sample_at"].startswith("2026-09-20T12:00:19")
    assert payload["stale_after_s"] == sismografo.RANCIO_S


def test_con_el_sensor_callado_el_espectrograma_deja_de_decirse_de_ahora(supervisor):
    """Tres horas de silencio y el anillo sirve exactamente lo mismo que vivo.

    Es el defecto entero en dos llamadas: el MISMO anillo, sin appendear nada
    entre medias, con dos relojes distintos. Si el estado no depende del reloj,
    la vista no tiene forma de distinguir un sismógrafo vivo de uno muerto.
    """
    t0 = _alimentar_anillo(supervisor.signal.waveform, "EHZ", 20, freq_hz=6.0, amplitud=4000)

    fresco = supervisor.local_api.spectrogram("EHZ", 128, ahora=t0 + timedelta(seconds=21))
    rancio = supervisor.local_api.spectrogram("EHZ", 128, ahora=t0 + timedelta(hours=3))

    assert fresco["rows"] == rancio["rows"], (
        "el anillo devolvió otra cosa: entonces esta prueba no está midiendo lo que dice medir"
    )
    assert fresco["stale"] is False
    assert rancio["stale"] is True
    assert rancio["age_s"] > 3 * 3600 - 60
    # Sigue habiendo dibujo: `stale` NO es `degraded`. Lo que deja de ser cierto
    # es el rótulo del borde derecho, no la matriz.
    assert rancio["degraded"] is False and rancio["rows"]


def test_el_umbral_de_rancio_es_el_mismo_que_el_rojo_del_retraso_del_sensor():
    """Dos superficies del panel no pueden discrepar sobre cuándo el sensor cesó.

    El umbral del servidor (`RANCIO_S`) y el rojo con el que la tabla
    de salud pinta `seedlink_lag_s` (`umbralColor(v, 2, 10)`) son el MISMO
    número, y se comprueba leyéndolo del panel en vez de teclearlo dos veces.
    """
    html = _INDEX.read_text("utf-8")
    m = re.search(r"return \['Retraso del sensor', txt, umbralColor\(v, (\d+), (\d+)\)\];", html)
    assert m, "el panel ya no pinta el retraso del sensor con `umbralColor`"
    assert float(m.group(2)) == sismografo.RANCIO_S, (
        f"el panel pone el rojo del retraso en {m.group(2)} s y el servidor marca "
        f"`stale` a los {sismografo.RANCIO_S} s"
    )


# ================================ [T-7.23 · M1] JSON que el kiosco pueda parsear


def _sin_constantes(texto: str):
    """`json.loads` con la MISMA severidad que el `JSON.parse` del navegador.

    Python acepta `Infinity` y `NaN` de fábrica; el kiosco no. Sin esto, un
    cuerpo que tumba el panel pasaría esta prueba sin inmutarse.
    """

    def _prohibido(literal):
        raise AssertionError(f"el cuerpo trae `{literal}`: eso NO es JSON y `JSON.parse` lanza")

    return json.loads(texto, parse_constant=_prohibido)


@pytest.mark.parametrize("crudo", ["inf", "-inf", "nan", "1e400", "-1e400", "infinity"])
def test_un_hours_no_finito_no_rompe_el_json_del_kiosco(supervisor, crudo):
    """`float('inf')` PARSEA en Python: caía fuera del `except` y viajaba crudo.

    Y lo que llegaba al kiosco no era un 400 —que la doctrina prohíbe— sino
    algo peor: un cuerpo que `JSON.parse` no puede leer, cuya excepción sube al
    `catch` del tick y hace que el panel declare caído un gabinete sano.
    """
    code, body = _get(supervisor.local_api, f"/api/helicorder?channel=EHZ&hours={crudo}")
    assert code == 200
    texto = body.decode() if isinstance(body, bytes) else body
    assert "Infinity" not in texto and "NaN" not in texto, texto[:200]
    payload = _sin_constantes(texto)
    assert payload["hours"] == sismografo.HORAS_DEFAULT
    assert payload["requested_hours"] is None


_LOCAL_API = Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "__init__.py"

#: Un cuerpo con un no-finito en LOS TRES sitios que el saneador tiene que
#: alcanzar: la raíz, una lista y un diccionario anidado. Un arreglo que sólo
#: tapara el campo culpable dejaría abiertos los otros dos.
_ENVENENADO = {
    "degraded": False,
    "reason": None,
    "sample_rate": float("nan"),
    "segments": [{"start": "x", "dc_counts": float("inf"), "minmax": [1.0, float("-inf")]}],
    "gaps": [],
}


def _manejador_del_panel() -> ast.ClassDef:
    arbol = ast.parse(_LOCAL_API.read_text("utf-8"))
    clases = [n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)]
    manejador = next((c for c in clases if c.name == "_DashboardHandler"), None)
    assert manejador is not None, (
        "el panel ya no tiene `_DashboardHandler`: este censo mira al aire"
    )
    return manejador


def _endpoints_json_del_panel() -> dict[str, str]:
    """`{ruta: método del dashboard}` de cada GET que sirve JSON, DERIVADO de `do_GET`.

    Enumerarlos aquí sería el censo que acaba divergiendo: el sexto endpoint no
    estaría en la lista y su cuerpo saldría sin mirar. Se sacan del árbol de
    sintaxis, emparejando la ruta de cada rama con la llamada al dashboard que
    alimenta `_send_json`.
    """
    do_get = next(
        n
        for n in _manejador_del_panel().body
        if isinstance(n, ast.FunctionDef) and n.name == "do_GET"
    )
    fuera: dict[str, str] = {}
    for nodo in ast.walk(do_get):
        if not isinstance(nodo, ast.If):
            continue
        rutas = [
            c.value
            for c in ast.walk(nodo.test)
            if isinstance(c, ast.Constant)
            and isinstance(c.value, str)
            and c.value.startswith("/api/")
        ]
        if len(rutas) != 1:
            continue
        metodos = {
            arg.func.attr
            # SÓLO `nodo.body`: `ast.walk(nodo)` se metería en el `elif` de al
            # lado y le colgaría a esta ruta el método de la siguiente.
            for stmt in nodo.body
            for c in ast.walk(stmt)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "_send_json"
            and len(c.args) >= 2
            and isinstance(arg := c.args[1], ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and isinstance(arg.func.value, ast.Name)
            and arg.func.value.id == "dashboard"
        }
        if len(metodos) == 1:
            fuera[rutas[0]] = metodos.pop()
    return fuera


def test_el_barrido_de_endpoints_encuentra_los_que_sirven_json():
    """Sin esto, un barrido vacío dejaría pasar la prueba de abajo sin medir nada."""
    endpoints = _endpoints_json_del_panel()
    assert len(endpoints) >= 4, endpoints
    # No-vacuidad dirigida: los dos que existían antes de esta vista.
    assert {"/api/status", "/api/waveform"} <= set(endpoints), endpoints


@pytest.mark.parametrize("ruta", sorted(_endpoints_json_del_panel()))
def test_ningun_flotante_no_finito_sale_por_el_socket(supervisor, monkeypatch, ruta):
    """El agujero no era `requested_hours`: era que NINGÚN flotante se miraba.

    **Y la guarda tampoco miraba a los cuatro [T-7.23 · C3].** Sólo ejercía el
    helicorder: medido, devolviendo `/api/status`, `/api/waveform`,
    `/api/spectrogram` y `/api/catalog` a un `self._send(200, json.dumps(…))`
    crudo, la suite del edge seguía en `489 passed`. La lista de endpoints se
    DERIVA ahora de `do_GET`, así que el siguiente que alguien añada entra aquí
    solo.
    """
    metodo = _endpoints_json_del_panel()[ruta]
    monkeypatch.setattr(
        supervisor.local_api, metodo, lambda *a, **k: dict(_ENVENENADO), raising=True
    )
    code, body = _get(supervisor.local_api, ruta)
    assert code == 200
    texto = body.decode() if isinstance(body, bytes) else body
    payload = _sin_constantes(texto)
    assert payload["sample_rate"] is None
    assert payload["segments"][0]["dc_counts"] is None
    assert payload["segments"][0]["minmax"] == [1.0, None]


def _puertas_de_json_del_panel() -> list[int]:
    """Líneas del manejador donde un cuerpo JSON sale por la puerta, del `ast`.

    [T-7.23 · Q3] El recuento vive AQUÍ y en ningún comentario. Lo tecleaban
    dos prosas —la de `_send_json` y la de la guarda de abajo— y decían cosas
    distintas, que es la forma más barata de demostrar que una cifra escrita a
    mano no la está midiendo nadie. Es la misma familia que la de `scipy.signal`
    («importarlo cuesta 0 MB»), y el arreglo es el mismo: derivarla.
    """
    return sorted(
        n.lineno
        for n in ast.walk(_manejador_del_panel())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_send_json"
    )


#: Las dos prosas que tecleaban el recuento. Se vigilan las DOS: arreglar una
#: sola dejaba la otra diciendo su número, que es exactamente lo que pasó.
_PROSAS_DE_LA_PUERTA = ("_send_json", "test_la_unica_puerta_de_json_lo_es_de_verdad")


def test_ninguna_prosa_vuelve_a_teclear_cuantas_puertas_de_json_hay():
    """Una decía 15 y la otra 21. No podían ser las dos, y ninguna se medía.

    La regla que sustituye a las dos cifras: **estas dos prosas no llevan
    números**. No es una regla de estilo — es que cualquier cantidad escrita
    aquí habla del mismo barrido que `_puertas_de_json_del_panel` ya hace, y
    una copia a mano de un recuento derivado sólo puede envejecer.

    Las marcas de ficha (`T-7.23`, `C3`, `Q3`, `§15.4`) no son cantidades y se
    quitan antes de mirar; lo que quede con un dígito es una cifra tecleada.
    """
    manejador = _manejador_del_panel()
    prosas = {
        n.name: ast.get_docstring(n) or ""
        for n in ast.walk(manejador)
        if isinstance(n, ast.FunctionDef) and n.name in _PROSAS_DE_LA_PUERTA
    }
    propio = ast.parse(Path(__file__).read_text("utf-8"))
    prosas.update(
        {
            n.name: ast.get_docstring(n) or ""
            for n in ast.walk(propio)
            if isinstance(n, ast.FunctionDef) and n.name in _PROSAS_DE_LA_PUERTA
        }
    )
    assert set(prosas) == set(_PROSAS_DE_LA_PUERTA), (
        f"este censo mira al aire: no encontró {set(_PROSAS_DE_LA_PUERTA) - set(prosas)}"
    )
    assert all(prosas.values()), f"alguna de las dos se quedó sin prosa: {prosas.keys()}"

    # Marcas de ficha y de sección: `T-7.23`, `C3`, `Q3`, `M1`, `§15.4`, `0`/`1`
    # dentro de un identificador. No son cantidades de nada.
    marcas = re.compile(r"T-\d+(?:\.\d+)*|§\d+(?:\.\d+)*|\b[A-ZÁÉÍÓÚÑ]\d+\b")
    con_cifra = {
        nombre: sorted(set(re.findall(r"\d+", marcas.sub("", texto))))
        for nombre, texto in prosas.items()
    }
    sucias = {n: c for n, c in con_cifra.items() if c}
    assert not sucias, (
        "estas prosas vuelven a teclear un recuento que `_puertas_de_json_del_panel` "
        f"ya deriva del árbol de sintaxis: {sucias}"
    )


def test_la_unica_puerta_de_json_lo_es_de_verdad():
    """«La única puerta por la que sale JSON del panel» era una afirmación, no un hecho.

    Quedaban `json.dumps` sueltos en el manejador —los cuerpos de error de
    `do_GET`, los de `do_POST`, los del grant de CCTV— saliendo al socket sin
    pasar por la verja, y ningún censo lo impedía. Se derivan del árbol de
    sintaxis y no de una lista: el `json.dumps` que alguien escriba mañana
    tampoco estará enumerado. Cuántas puertas hay lo cuenta
    `_puertas_de_json_del_panel`; aquí no se escribe, y hay guarda que lo
    exige.

    Se vigilan las dos mitades, porque tapar una sola dejaría la otra abierta:
    ningún `json.dumps` dentro del manejador, y ningún `_send` que mande un
    cuerpo JSON sin declararlo — `_send` pone `application/json` por defecto,
    así que todo el que no pase un `content_type` está sirviendo JSON.
    """
    manejador = _manejador_del_panel()
    # No-vacuidad: un manejador del que no saliera JSON por ninguna puerta
    # haría pasar las dos mitades de abajo sin medir nada.
    puertas = _puertas_de_json_del_panel()
    assert len(puertas) >= len(_endpoints_json_del_panel()), (
        f"sólo {len(puertas)} puertas de JSON para {len(_endpoints_json_del_panel())} "
        "endpoints que sirven JSON: el barrido está roto"
    )
    volcados = [
        n
        for n in ast.walk(manejador)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "dumps"
    ]
    assert not volcados, (
        "hay `json.dumps` dentro de `_DashboardHandler`, o sea JSON que sale al socket "
        "sin pasar por `_send_json`: líneas " + ", ".join(str(n.lineno) for n in volcados)
    )

    crudos: list[int] = []
    for metodo in [n for n in manejador.body if isinstance(n, ast.FunctionDef)]:
        for n in ast.walk(metodo):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr != "_send":
                continue
            declara_tipo = len(n.args) >= 3 or any(k.arg == "content_type" for k in n.keywords)
            if metodo.name != "_send_json" and not declara_tipo:
                crudos.append(n.lineno)
    assert not crudos, (
        "estos `self._send(...)` mandan `application/json` (el defecto de `_send`) sin "
        f"pasar por `_send_json`: líneas {crudos}"
    )


def test_el_saneo_del_cuerpo_no_lo_paga_el_camino_limpio(supervisor, monkeypatch):
    """[T-7.23 · N3] La verja es correcta; lo que no puede es cobrarse siempre.

    Reconstruía la respuesta ENTERA en Python, incluidas las listas de muestras
    de `/api/waveform`, donde un no-finito no cabe: son enteros decimados.
    Medido [MEDIDO · equipo de desarrollo x86-64 · Python 3.12 · 2026-09-20]:
    1.82 ms por llamada con 8 000 valores y 9.95 ms sobre un helicorder de 6 h,
    frente a los 0.61 ms y 2.43 ms del `json.dumps` que ya se hacía. Con
    `allow_nan=False` la comprobación la hace el codificador en C —0.43 ms y
    2.37 ms— y el saneador corre sólo cuando de verdad hay algo que sanear.

    No se mide tiempo aquí a propósito: un reloj en el CI es ruido. Se mide el
    HECHO —cuántas veces corre el saneador— que es lo que causa el tiempo.
    """
    from takab_edge import local_api as modulo

    corridas: list[int] = []
    original = modulo.sanear_no_finitos

    def contando(valor):
        corridas.append(1)
        return original(valor)

    monkeypatch.setattr(modulo, "sanear_no_finitos", contando)

    for ruta in sorted(_endpoints_json_del_panel()):
        code, _ = _get(supervisor.local_api, ruta)
        assert code == 200, ruta
    assert corridas == [], (
        f"el saneador corrió {len(corridas)} veces sobre cuerpos que no tenían un solo "
        "no-finito: el camino caliente está pagando por una imposibilidad"
    )

    # …y sigue corriendo cuando hace falta, que es la otra mitad: un saneador
    # que no corriera nunca también dejaría `corridas == []`.
    monkeypatch.setattr(
        supervisor.local_api, "catalog", lambda *a, **k: dict(_ENVENENADO), raising=True
    )
    code, body = _get(supervisor.local_api, "/api/catalog")
    assert code == 200
    assert corridas, "con un NaN dentro, el saneador no corrió y el cuerpo salió sin mirar"
    assert _sin_constantes(body.decode())["sample_rate"] is None


# ===================== [T-7.23 · M2] el anillo que llegó fuera de orden


def _anillo_de_seis_horas(anillo, *, paso_s: int = 30) -> None:
    """6 h continuas de EHZ en el anillo REAL, escritas por `RingBuffer.append`.

    Con `RingBuffer` y no con `_fabricar` a propósito: lo que se quiere probar
    incluye el testigo de desorden, y el testigo lo pone el escritor. `paso_s`
    de 30 deja 720 escrituras, que son 0.7 s de montaje [MEDIDO · equipo de
    desarrollo x86-64 · 2026-09-20] — un paquete de 1 s tardaría más en montar
    el escenario que en medirlo.
    """
    inicio = AHORA - timedelta(hours=6)
    for k in range(int(6 * 3600 / paso_s)):
        anillo.append(
            _paquete(
                "EHZ",
                np.full(paso_s * 100, 100 + k % 50, dtype=np.int32),
                inicio + timedelta(seconds=paso_s * k),
            )
        )


def test_un_bloque_re_entregado_no_apaga_el_helicorder_treinta_horas(supervisor):
    """[T-7.23 · Q2] Servir lo que haya y DECLARAR lo que no se sabe.

    Esto degradaba con `anillo_desordenado` en cuanto el fichero del día
    llevaba el testigo, y el testigo no se borra al rodar el día: se borra con
    su fichero. O sea la pantalla del sismógrafo EN BLANCO unas 30 h porque un
    paquete llegó dos veces — y re-entregar un bloque es lo que hace una
    reconexión larga de SeedLink, por diseño, según el propio docstring de
    `_DESORDEN_SUFIJO`. Es peor que el defecto que arreglaba: una pantalla
    apagada no protege a nadie.

    El escenario es el medido: 6 h continuas y luego UN paquete de hace 6 h.
    Las dos mitades van juntas — sin la primera, un helicorder que sirviera
    siempre pasaría la segunda sin haber arreglado nada.
    """
    anillo = supervisor.buffer
    _anillo_de_seis_horas(anillo)

    antes = {h: supervisor.local_api.helicorder("EHZ", h, ahora=AHORA) for h in (1.0, 6.0)}
    for h, r in antes.items():
        assert r["degraded"] is False, (h, r["reason"])
        assert r["ring_unordered"] is False, "el anillo sano no puede declararse desordenado"

    # El Shake re-entrega el primer bloque: se appendea al final, más viejo que
    # su vecino, y el escritor pone el testigo.
    anillo.append(_paquete("EHZ", np.full(3000, 7, dtype=np.int32), AHORA - timedelta(hours=6)))
    from takab_edge.buffer import RingBuffer

    fichero = next(_raiz(supervisor).glob("*.mseed"))
    assert RingBuffer.hay_desorden(fichero), (
        "sin testigo esta prueba mide el camino del lector, no el del desorden declarado"
    )

    for h in (1.0, 6.0):
        r = supervisor.local_api.helicorder("EHZ", h, ahora=AHORA)
        assert r["degraded"] is False, (
            f"la ventana de {h} h se apagó por un paquete duplicado: {r['reason']}"
        )
        assert r["segments"], f"{h} h sin un solo tramo que pintar"
        # …y lo que no se sabe se DICE. Apagar es una decisión del operador.
        assert r["ring_unordered"] is True, "sirvió la ventana sin advertir del desorden"
        # La cobertura sigue siendo la real, medida sobre dato decodificado.
        assert r["truncated"] is False, (r["truncated_reason"], r["segments"][0]["start"])


def test_el_lector_avisa_del_desorden_UNA_vez_y_no_una_por_peticion(supervisor, caplog):
    """[T-7.23 · Q2] El desorden dura ~30 h y el kiosco pregunta cada 60 s.

    Un `log.warning` por lectura son del orden de mil ochocientas líneas sobre
    un hecho que ocurrió UNA vez: un intervalo disfrazado de evento (regla de
    oro 10), contra la cota de log de T-7.47. Antes casi no se notaba porque la
    respuesta era degradada; ahora el helicorder sigue sirviendo y el kiosco se
    queda abierto delante del gabinete.
    """
    from takab_edge.local_api import sismografo as modulo

    modulo._DESORDEN_AVISADO.clear()
    anillo = supervisor.buffer
    inicio = AHORA - timedelta(minutes=20)
    for k in range(60):
        anillo.append(
            _paquete("EHZ", np.full(1000, 100, dtype=np.int32), inicio + timedelta(seconds=10 * k))
        )
    anillo.append(_paquete("EHZ", np.full(1000, 7, dtype=np.int32), inicio + timedelta(seconds=30)))

    with caplog.at_level("WARNING", logger="takab_edge.local_api.sismografo"):
        for _ in range(5):
            supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    avisos = [r for r in caplog.records if "fuera de orden" in r.getMessage()]
    assert len(avisos) == 1, f"{len(avisos)} avisos para cinco lecturas del mismo fichero"


def test_sin_indice_fiable_la_cola_por_presupuesto_recupera_lo_que_el_indice_perdia(
    supervisor,
):
    """El desorden no sólo deja de apagar: además se sirve MÁS, y está medido.

    Escenario V1 pero escrito por `RingBuffer`, así que esta vez el testigo SÍ
    está puesto: una hora continua con un bloque de hace un minuto metido justo
    en el medio, que es la posición que la búsqueda binaria prueba primero.

    Medido sobre este mismo montaje [MEDIDO · equipo de desarrollo x86-64 ·
    2026-09-20]: confiando en el índice se sirve desde las 14:30 para una
    ventana que empieza a las 14:00 —media hora que existe en el anillo— y sale
    `truncated: anillo`; sin confiar en él (la cola entera acotada por el
    presupuesto) se sirve desde las 14:00 y la ventana sale completa. Por eso
    el testigo deja de degradar y pasa a cambiar CÓMO se lee.
    """
    anillo = supervisor.buffer
    inicio = AHORA - timedelta(hours=1)
    for k in range(180):  # 14:00–14:30
        anillo.append(
            _paquete("EHZ", np.full(1000, 100, dtype=np.int32), inicio + timedelta(seconds=10 * k))
        )
    anillo.append(  # 13:59, re-entregado, en MITAD del fichero
        _paquete("EHZ", np.full(1000, 7, dtype=np.int32), inicio - timedelta(minutes=1))
    )
    for k in range(180):  # 14:30–15:00
        anillo.append(
            _paquete(
                "EHZ",
                np.full(1000, 100, dtype=np.int32),
                inicio + timedelta(minutes=30, seconds=10 * k),
            )
        )

    servido = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert servido["degraded"] is False, servido["reason"]
    assert servido["ring_unordered"] is True
    primero = datetime.fromisoformat(servido["segments"][0]["start"])
    assert primero <= inicio + timedelta(seconds=sismografo.BUCKET_S), (
        f"lo servido empieza en {primero} y la ventana en {inicio}: la cola por "
        "presupuesto no está recuperando el dato que el índice perdía"
    )
    assert servido["truncated"] is False, servido["truncated_reason"]

    # La otra mitad, y es la que da sentido a la primera: con el índice —el
    # camino que se toma cuando NO hay testigo— se perdía media hora.
    from takab_edge.local_api import sismografo as modulo

    original = modulo._hay_desorden
    try:
        modulo._hay_desorden = lambda ruta: False
        con_indice = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    finally:
        modulo._hay_desorden = original
    perdido = datetime.fromisoformat(con_indice["segments"][0]["start"]) - inicio
    assert perdido > timedelta(minutes=20), (
        f"el índice sólo perdió {perdido} en este montaje: el escenario ya no muerde "
        "donde dice morder y la comparación no significa nada"
    )
    assert con_indice["truncated"] is True and con_indice["truncated_reason"] == "anillo"


def test_el_testigo_de_desorden_se_va_con_su_fichero_al_podar(tmp_path):
    """Un testigo huérfano condenaría a un fichero que ya no es el que falló."""
    from takab_edge.buffer import RingBuffer
    from takab_edge.config import BufferConfig

    # `max_bytes=1` hace que la poda por TAMAÑO se lleve el fichero en la
    # primera pasada; la de retención pide días > 0 y aquí no hace falta.
    anillo = RingBuffer(BufferConfig(root=str(tmp_path), retention_days=1, max_bytes=1))
    base = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    anillo.append(_paquete("EHZ", np.full(1000, 5, dtype=np.int32), base + timedelta(seconds=30)))
    anillo.append(_paquete("EHZ", np.full(1000, 5, dtype=np.int32), base))
    testigos = list(tmp_path.glob("*.desorden"))
    assert len(testigos) == 1, "el anillo no marcó el desorden que acaba de escribir"

    anillo.prune()
    assert list(tmp_path.glob("*.desorden")) == [], "el testigo sobrevivió a su fichero"


# ============ [T-7.23] las guardas que faltaban: mutaciones que salían VERDES
#
# Cada una de estas nació de romper el código a propósito y ver la suite pasar.
# No son «más cobertura»: son el sitio exacto donde el panel podía mentir sin
# que nadie se enterase.


def test_el_presupuesto_conserva_lo_NUEVO_y_no_lo_viejo(supervisor, monkeypatch):
    """Invertir el extremo que se conserva dejaba 47 tests en verde.

    Se comprobaba `truncated`, `truncated_reason` y `bytes_read` — o sea CUÁNTO
    se recortó— y nunca QUÉ EXTREMO sobrevivió. Un helicorder que, al morder el
    presupuesto, enseñara los primeros cinco minutos de hace una hora en vez de
    los últimos cinco, pasaba entero. Y es la peor forma de fallar: la pantalla
    se ve llena y sin avisos, y el operador está mirando el pasado.
    """
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=50), 50 * 60, paso_s=10)
    monkeypatch.setattr(sismografo, "PRESUPUESTO_BYTES", 30 * 4096)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["truncated"] is True and payload["truncated_reason"] == "presupuesto"

    arranques = [datetime.fromisoformat(s["start"]) for s in payload["segments"]]
    finales = [
        datetime.fromisoformat(s["start"]) + timedelta(seconds=s["buckets"] * payload["bucket_s"])
        for s in payload["segments"]
    ]
    assert min(arranques) >= AHORA - timedelta(minutes=15), (
        f"lo servido empieza en {min(arranques)} con la ventana acabando en {AHORA}: "
        "el recorte conservó lo VIEJO. El operador quiere lo de ahora."
    )
    assert max(finales) >= AHORA - timedelta(minutes=1), (
        "lo servido no llega hasta el final de la ventana: falta lo reciente"
    )


def test_el_espectrograma_resta_la_continua_antes_de_transformar(supervisor):
    """Borrar `muestras -= dc` dejaba 47 tests en verde: todos usaban media cero.

    Y el dato real no la tiene: el acelerómetro lleva ~1 g de continua en ENZ y
    un bias de fábrica en ENN/ENE. Sin restarla, la primera fila del
    espectrograma se come toda la escala y el resto del dibujo se apaga — el
    mismo defecto que ya se había pagado en el waveform crudo (T-2.25).

    Se mide con el MISMO tono en dos canales, uno con un millón de counts de
    continua encima: las dos matrices tienen que salir idénticas, y `dc_counts`
    tiene que publicar lo que se quitó.
    """
    anillo = supervisor.signal.waveform
    _alimentar_anillo(anillo, "EHZ", 20, freq_hz=8.0, amplitud=1000)
    _alimentar_anillo(anillo, "ENZ", 20, freq_hz=8.0, amplitud=1000, offset=1_000_000)

    limpio = _json(supervisor, "/api/spectrogram?channel=EHZ")
    sucio = _json(supervisor, "/api/spectrogram?channel=ENZ")

    assert abs(limpio["dc_counts"]) < 1.0
    assert abs(sucio["dc_counts"] - 1_000_000) < 1.0, sucio["dc_counts"]
    assert limpio["rows"] == sucio["rows"], (
        "un millón de counts de continua cambió el espectrograma: la media no se "
        "está restando y la fila de 0 Hz se come la escala"
    )


def test_elegir_canal_prefiere_el_geofono_aunque_no_sea_el_primero_alfabetico():
    """Quitar la preferencia por EHZ dejaba 47 en verde: hoy `sorted()[0]` ES EHZ.

    Con los cuatro canales de un RS4D (EHZ/ENE/ENN/ENZ) el mutante es
    equivalente y ninguna prueba podía distinguirlo. Con los de un RS3D
    (EHE/EHN/EHZ) sí: alfabéticamente gana EHE, y lo que el panel tiene que
    enseñar por defecto es el GEÓFONO vertical, que es el canal con el que se
    mira un sismo.
    """
    assert sismografo.elegir_canal(["EHE", "EHN", "EHZ"], None) == "EHZ"
    assert sismografo.elegir_canal(["EHE", "EHN", "EHZ"], "EHN") == "EHN"
    # Sin EHZ no hay geófono vertical que preferir: el primero, y el rótulo lo dice.
    assert sismografo.elegir_canal(["ENE", "ENN"], None) == "ENE"


def test_el_hueco_de_COLA_se_declara_cuando_el_sensor_lleva_un_rato_callado(supervisor):
    """Desactivarlo dejaba 47 en verde, y es el ÚNICO aviso de sensor mudo del
    helicorder.

    Sin él, el último tramo se estira hasta el borde derecho y una hora sin
    sensor se dibuja como una hora de calma.
    """
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=20), 600, paso_s=10)

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is False, payload["reason"]
    colas = [g for g in payload["gaps"] if g["end"] == AHORA.isoformat()]
    assert colas, (
        "el sensor lleva 10 minutos callado y el helicorder no declara hueco de "
        f"cola: {payload['gaps']}"
    )
    assert 590 <= colas[0]["seconds"] <= 610, colas[0]


def test_la_cola_se_alinea_al_registro_y_un_registro_a_medias_no_la_tumba(supervisor):
    """`fin = tamano` (sin alinear) dejaba 47 en verde.

    El anillo se appendea MIENTRAS esto lee, así que el último registro puede
    estar a medio escribir. Pasarle a obspy media cabecera es un error que no
    se distingue de un fichero corrupto: el panel diría `anillo_ilegible` de un
    anillo perfectamente sano, y lo diría justo cuando más dato está entrando.
    """
    rutas = _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=10), 600, paso_s=10)
    with open(rutas[0], "ab") as fh:
        fh.write(b"\x00" * 1500)  # un registro a medio escribir

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is False, (
        f"un registro a medio escribir tumbó la lectura: {payload['reason']}"
    )
    assert payload["bytes_read"] % 4096 == 0, (
        f"se leyeron {payload['bytes_read']} B, que no es múltiplo del registro: "
        "el corte no está alineado"
    )


def test_el_tramo_crudo_corta_en_el_ultimo_hueco_igual_que_serve(supervisor):
    """Devolver todos los marks sin cortar dejaba 47 en verde.

    Unir dos tramos discontinuos es inventar movimiento que no ocurrió, y en un
    espectrograma el salto se transforma en un golpe de banda ancha que no
    existió: un escalón artificial pintado como si fuera un sismo.
    """
    anillo = supervisor.signal.waveform
    t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    for k in range(5):
        anillo.append(_paquete("EHZ", np.full(100, 10, dtype=np.int32), t0 + timedelta(seconds=k)))
    # …silencio de 20 s, y el sensor vuelve.
    despues = t0 + timedelta(seconds=25)
    for k in range(4):
        anillo.append(
            _paquete("EHZ", np.full(100, 20, dtype=np.int32), despues + timedelta(seconds=k))
        )

    tramo = anillo.tramo_crudo("EHZ")
    assert tramo["gap_before"] is True
    assert tramo["first_sample_at"] == despues, (
        "el tramo arranca antes del hueco: se están empalmando dos mediciones"
    )
    assert tramo["samples"].size == 400, tramo["samples"].size
    assert set(tramo["samples"].tolist()) == {20}, "el tramo trae muestras de ANTES del hueco"


def test_lo_que_se_sale_por_arriba_y_lo_que_se_sale_por_abajo_no_se_confunden(supervisor):
    """Intercambiar `below_scale` y `above_scale` dejaba 52 en verde.

    Sólo se comprobaba `above_scale > 0` con un tono a fondo de escala, y en ese
    caso los dos contadores son distintos de cero. Con los dos extremos medidos
    —1 count de amplitud y 8·10⁶— la dirección ya no se puede intercambiar: un
    espectrograma que dijera «60 celdas por debajo» de una señal saturada manda
    al operador a mirar la ganancia del sensor en vez de al sismo.
    """
    anillo = supervisor.signal.waveform
    _alimentar_anillo(anillo, "EHZ", 20, freq_hz=5.0, amplitud=1)
    _alimentar_anillo(anillo, "ENZ", 20, freq_hz=5.0, amplitud=8_000_000)

    apagado = _json(supervisor, "/api/spectrogram?channel=EHZ")
    saturado = _json(supervisor, "/api/spectrogram?channel=ENZ")

    assert apagado["below_scale"] > apagado["above_scale"], (
        f"1 count de amplitud y {apagado['above_scale']} celdas POR ENCIMA de "
        f"{sismografo.ESCALA_DB_MAX} dB: los contadores están al revés"
    )
    assert apagado["above_scale"] == 0
    assert saturado["above_scale"] > saturado["below_scale"], (
        f"un tono a fondo de escala del ADC y {saturado['below_scale']} celdas "
        "POR DEBAJO: los contadores están al revés"
    )


# ------------------------------------------------- utilidades de las guardas


def _paleta_c() -> dict[str, str]:
    """El objeto `const C` del panel, que es una de las dos fuentes de color."""
    html = _INDEX.read_text("utf-8")
    i = html.index("const C = {")
    bloque = html[i : html.index("}", i)]
    return {m[1]: m[2].upper() for m in re.finditer(r"(\w+)\s*:\s*'(#[0-9a-fA-F]{6})'", bloque)}


def _rgb(token: str) -> str:
    v = _paleta_c()[token].lstrip("#")
    return "rgb({},{},{})".format(*(int(v[i : i + 2], 16) for i in (0, 2, 4)))


def _bloque_sismografo() -> str:
    """El JS de la vista SISMÓGRAFO, delimitado por sus dos fronteras.

    Lo comprueba `test_el_barrido_del_bloque_del_sismografo_encuentra_algo`: un
    barrido que no encontrara el bloque daría verde a todo lo que mire.
    """
    html = _INDEX.read_text("utf-8")
    i = html.index("[T-7.23] vista SISMÓGRAFO")
    return html[i : html.index("function frame(){", i)]


def _ops(out: dict, lienzo: str, op: str) -> list[dict]:
    return [o for o in (out.get("canvasOps") or []) if o["lienzo"] == lienzo and o["op"] == op]


def test_el_barrido_del_bloque_del_sismografo_encuentra_algo():
    bloque = _bloque_sismografo()
    assert "SPEC_PARADAS" in bloque and "function drawHeli()" in bloque
    assert "function renderSalud" not in bloque, "el barrido se comió medio panel"


# ============================= [T-7.23 · A2] la pantalla del dato rancio


def test_con_el_dato_rancio_la_tarjeta_deja_de_prometer_los_ultimos_60_s(tmp_path):
    """El rótulo decía «Espectrograma · últimos 60 s» sobre dato de hace horas."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(
            stale=True, age_s=10800.0, last_sample_at="2026-08-04T07:00:00+00:00"
        ),
        canvasOps=True,
    )
    titulo = _txt(out, "sismo-spec-title")
    assert "últimos 60 s" not in titulo, titulo
    assert "DATO RETENIDO" in titulo.upper()
    meta = _txt(out, "sismo-spec-meta").upper()
    assert "DATO RETENIDO HACE" in meta
    assert "3.0 H" in meta, meta

    textos = [o["txt"] for o in _ops(out, "spec-canvas", "fillText")]
    assert "AHORA" not in textos, (
        "el borde derecho del espectrograma sigue diciendo «AHORA» con dato de "
        f"hace tres horas: {textos}"
    )
    assert "07:00:00 UTC" in textos, textos


def test_con_el_dato_fresco_el_espectrograma_si_dice_ahora(tmp_path):
    """La mitad que impide que el arreglo sea «no decir AHORA nunca»."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(stale=False, age_s=0.4),
        canvasOps=True,
    )
    assert "últimos 60 s" in _txt(out, "sismo-spec-title")
    assert "AHORA" in [o["txt"] for o in _ops(out, "spec-canvas", "fillText")]


def test_la_vista_sismografo_no_puede_esconder_la_salud_del_sensor(tmp_path):
    """`?view=sismografo` esconde `#grid`, y ahí vivía lo único que delataba al
    sensor mudo.

    Con el sensor callado el anillo de 60 s sigue sirviendo su último minuto
    bueno: si además se esconde el retraso y los paquetes vistos, no queda NADA
    en pantalla que diga que el sismógrafo lleva horas sin medir.
    """
    st = _status_con_identidad()
    st["health"] = {**st["health"], "seedlink_lag_s": 54200.0}
    st["seedlink"] = {**st["seedlink"], "packets_seen": 0}

    out = _render(tmp_path, status=st, search="?view=sismografo")
    texto = _txt(out, "sismo-station")
    assert "Retraso del sensor" in texto
    assert "15.1 h" in texto, texto
    assert "Paquetes vistos" in texto


def test_el_retraso_del_sensor_de_la_vista_sismografo_cambia_con_el_dato(tmp_path):
    """Un rótulo fijo cumpliría la prueba de arriba sin leer nada del gabinete."""
    st = _status_con_identidad()
    sano = _render(tmp_path, status=st, search="?view=sismografo")
    st_malo = {**st, "health": {**st["health"], "seedlink_lag_s": 54200.0}}
    mudo = _render(tmp_path, status=st_malo, search="?view=sismografo")
    assert _txt(sano, "sismo-station") != _txt(mudo, "sismo-station")


# ============================== [T-7.23] las guardas ciegas de la pantalla


def test_la_edad_del_helicorder_es_una_RESTA_y_no_un_rotulo(tmp_path):
    """Clavar `const edad = 0` dejaba la prueba en verde: sólo buscaba el marcador.

    Es la lección exacta de T-7.60 —un marcador tapa la resta— y aquí se
    corrige del único modo que sirve: adelantando el reloj del arnés y exigiendo
    que la cifra lo siga. 37 s es un número sin nada especial, elegido para que
    no pueda salir por casualidad de ningún redondeo.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        now="2026-08-04T10:00:00Z",
        clicks=["clock:+37000", "tick"],
    )
    texto = _txt(out, "sismo-heli-meta")
    assert "CALCULADO HACE 37 s" in texto, texto


def test_la_edad_del_helicorder_no_se_re_pide_y_por_eso_crece(tmp_path):
    """La otra mitad: a los 0 s dice 0, y el número no es una constante."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        now="2026-08-04T10:00:00Z",
    )
    assert "CALCULADO HACE 0 s" in _txt(out, "sismo-heli-meta")


def test_el_eje_de_frecuencias_del_espectrograma_va_hacia_ARRIBA(tmp_path):
    """Invertirlo dejaba 52 en verde, y su propio comentario avisaba de que
    nadie lo notaría.

    Un espectrograma leído al revés pone el microsismo oceánico —el ruido de
    fondo de 0.1–1 Hz, que siempre está— arriba del todo, donde uno busca el
    contenido de alta frecuencia de un sismo cercano. La fila 0 es la
    frecuencia MÁS BAJA y tiene que pintarse ABAJO.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        # Fila 0 (0 Hz) al mínimo, fila 1 (25 Hz) al máximo: los dos extremos de
        # la rampa, que no se pueden confundir con nada.
        spectrogram=_spec_payload(rows=[[0, 0, 0], [255, 255, 255]]),
        canvasOps=True,
    )
    celdas = _ops(out, "spec-canvas", "fillRect")
    assert celdas, "el espectrograma no pintó ni una celda"
    abajo = max(celdas, key=lambda o: o["y0"])
    arriba = min(celdas, key=lambda o: o["y0"])
    assert abajo["color"] == _rgb("surface0"), (
        f"la celda de más abajo se pintó {abajo['color']}: esa es la fila de 25 Hz, "
        "o sea el eje está invertido"
    )
    assert arriba["color"] == _rgb("crit"), arriba["color"]


def test_el_helicorder_pinta_la_franja_del_hueco(tmp_path):
    """Borrarla dejaba 52 en verde: la tarjeta decía «1 HUECO» y el dibujo no.

    El hueco es la diferencia entre «no hubo movimiento» y «no hubo medición»,
    que en la pantalla de un sismógrafo es toda la diferencia que hay.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        canvasOps=True,
    )
    ambar = _paleta_c()["warn"].lstrip("#")
    esperado = "rgba({},{},{},0.14)".format(*(int(ambar[i : i + 2], 16) for i in (0, 2, 4)))
    franjas = [o for o in _ops(out, "heli-canvas", "fillRect") if o["color"] == esperado]
    assert franjas, (
        "el helicorder declara un hueco de media hora y no pinta ninguna franja: "
        f"{[o['color'] for o in _ops(out, 'heli-canvas', 'fillRect')]}"
    )
    ancho = franjas[0]["x1"] - franjas[0]["x0"]
    # El hueco cubre 1797 s de una ventana de 3600 s: la mitad del lienzo útil.
    assert 350 < ancho < 500, f"la franja mide {ancho:.0f} px sobre media ventana"


def test_pulsar_un_chip_de_canal_vuelve_a_pedir_el_helicorder(tmp_path):
    """Quitar `S.heliDirty = true` del clic dejaba 52 en verde: nadie los pulsaba.

    Sin eso, cambiar de canal repinta el espectrograma al instante y deja el
    helicorder del canal ANTERIOR hasta 60 s debajo, con el rótulo del canal
    nuevo. Dos canales distintos en la misma pantalla diciendo ser el mismo.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        clicks=["data:sismo-ch:ENZ", "tick"],
    )
    pedidos = [f["url"] for f in out["fetches"] if "api/helicorder" in f["url"]]
    assert len(pedidos) == 2, pedidos
    assert "channel=ENZ" in pedidos[-1], pedidos


def test_la_vista_se_conmuta_aunque_el_gabinete_no_conteste(tmp_path):
    """Hacerla depender del status dejaba 52 en verde: nadie renderizaba sin él.

    Y es justo cuando más importa: quien abre `?view=sismografo` con el
    gabinete mudo tiene que ver la superficie que pidió, con sus zonas en S/D,
    y no la otra — si no, creería que el parámetro no funciona.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        statusStatus=500,
    )
    assert _hidden(out, "grid") is True
    assert _hidden(out, "sismo") is False
    assert "SIN ESPECTROGRAMA" in _txt(out, "sismo-spec-meta").upper()


# ================================ [T-7.23 · M4] los lienzos y su tamaño


@pytest.mark.parametrize(
    ("paso", "porque"),
    [
        ("resize:412", "un resize del navegador"),
        ("data:mode:muro", "un clic en MURO/CONSOLA/CAMPO"),
    ],
)
def test_los_lienzos_se_repintan_cuando_cambia_su_TAMANO(tmp_path, paso, porque):
    """`fitCanvas()` vive dentro de los dos `draw*`, que sólo corren por DATO.

    Así que nada los redibujaba cuando lo que cambiaba era la geometría: el
    helicorder se quedaba hasta 60 s con el bitmap viejo ESTIRADO por CSS. Un
    sismograma deformado es peor que uno ausente — parece que el suelo se movió
    de otra manera.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        spectrogram=_spec_payload(),
        helicorder=_heli_payload(),
        canvasOps=True,
        clicks=[paso, "frame"],
    )
    pintados = {o["lienzo"] for o in (out["canvasOps"] or [])}
    assert {"spec-canvas", "heli-canvas"} <= pintados, (
        f"tras {porque} el fotograma siguiente no repintó los dos lienzos: {sorted(pintados)}"
    )


# ============================ [T-7.23] los defectos baratos, con su guarda


def test_los_botones_de_canal_salen_del_gabinete_y_no_del_marcado(tmp_path):
    """Estaban enumerados a mano (EHZ/ENZ/ENN/ENE) mientras la lista ya viajaba.

    Un RS3D —tres canales, EHE/EHN/EHZ— ofrecía tres botones que no existen y
    escondía los suyos. Y pulsar uno que el anillo no tiene es pedirle al
    gabinete un canal inventado.
    """
    st = _status_con_identidad()
    st["station_nslc"] = ["AM.R3D01.00.EHE", "AM.R3D01.00.EHN", "AM.R3D01.00.EHZ"]
    out = _render(tmp_path, status=st, search="?view=sismografo")
    chips = [k["txt"] for k in _node(out["tree"], "sismo-ch-chips")["kids"]]
    assert chips == ["EHE", "EHN", "EHZ"], chips


def test_sin_canales_provisionados_la_botonera_lo_declara(tmp_path):
    st = _status_con_identidad()
    st["station_nslc"] = []
    out = _render(tmp_path, status=st, search="?view=sismografo")
    assert "S/D" in _txt(out, "sismo-ch-chips")


def test_un_ocupado_transitorio_no_deja_el_lienzo_en_blanco_60_s(tmp_path):
    """`S.heliAt` se marcaba ANTES del fetch.

    `ocupado` es la respuesta más común del helicorder cuando hay dos kioscos
    abiertos —existe para eso— y marcaba el reloj igual que una respuesta
    buena: un minuto entero de lienzo en blanco por una colisión de milisegundos.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=[
            _heli_payload(degraded=True, reason="ocupado", segments=[], gaps=[]),
            _heli_payload(),
        ],
        clicks=["tick"],
    )
    pedidos = [f["url"] for f in out["fetches"] if "api/helicorder" in f["url"]]
    assert len(pedidos) == 2, (
        f"tras un `ocupado` el panel no volvió a pedir el helicorder: {pedidos}"
    )
    assert "CALCULADO HACE" in _txt(out, "sismo-heli-meta"), (
        "el segundo intento trajo dato bueno y la tarjeta sigue en degradado"
    )


def test_una_respuesta_no_ocupada_si_respeta_los_60_s(tmp_path):
    """La otra mitad: sin esto, el arreglo sería «pedirlo siempre»."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(degraded=True, reason="canal_sin_ficheros", segments=[], gaps=[]),
        clicks=["tick", "tick", "tick"],
    )
    pedidos = [f["url"] for f in out["fetches"] if "api/helicorder" in f["url"]]
    assert len(pedidos) == 1, f"una razón que no es `ocupado` se re-pidió a 1 Hz: {pedidos}"


#: Semieje ÚTIL del lienzo del helicorder en el arnés, en píxeles. El mini-DOM
#: da 900×420 a todo elemento, `drawHeli` descuenta `SISMO_PAD_B` (16 px) para
#: el eje de tiempos y pinta contra `medio - 2`: ése es el desvío máximo que
#: puede tener un trazo, y contra él se miden las fracciones de abajo.
_HELI_SEMIEJE = (420 - 16) / 2 - 2

#: Canales con los que se miden los pisos. Uno de CADA familia, que es lo que
#: importa: el defecto era que las dos estaban intercambiadas, así que una
#: guarda sobre un solo canal se habría quedado verde con el error puesto en la
#: otra mitad.
_FAMILIAS = ("EHZ", "ENZ")


def _evaluar(tmp_path: Path, expresiones: list[str]) -> list:
    """Pregunta al PANEL, en su propio contexto y ya renderizado."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        evals=expresiones,
    )
    valores = out.get("evals")
    assert valores is not None and len(valores) == len(expresiones), (
        f"el arnés no devolvió las sondas pedidas: {valores!r}"
    )
    for expr, v in zip(expresiones, valores, strict=True):
        assert not (isinstance(v, dict) and "error" in v), f"{expr} lanzó: {v['error']}"
    return valores


def _piso_esperado_en_counts(tmp_path: Path) -> dict[str, float]:
    """`{canal: el piso que le TOCA al helicorder, en counts}`.

    Sale de `scaleFor` —que es quien declara el piso— convertido a counts con
    `toPhys`, que es quien sabe en qué unidad mide cada canal. **No sale de
    `pisoHeliCounts`**, a propósito: es la función bajo prueba, y derivar de
    ella la amplitud del escenario haría que la guarda se moviera con el
    defecto. Es literalmente el agujero de `C4`: las dos guardas viejas usaban
    ±9 y ±400 000 counts, tan lejos de cualquier piso que seguían verdes con
    los pisos intercambiados.

    `toPhys` es lineal en los counts, así que un count basta para invertirla.
    """
    valores = _evaluar(
        tmp_path,
        [
            # `peakHold` se vacía primero: `renderLanes` ya corrió y lo dejó con
            # el pico del fixture dentro, y entonces `scaleFor` no devolvería el
            # PISO sino el pico × 1.35.
            f"(function(){{for (const k in peakHold) delete peakHold[k];"
            f"return scaleFor({c!r}, null)/toPhys({c!r}, 1);}})()"
            for c in _FAMILIAS
        ],
    )
    pisos = dict(zip(_FAMILIAS, (float(v) for v in valores), strict=True))
    assert all(v > 1000 for v in pisos.values()), (
        f"los pisos derivados no son counts de un sensor real: {pisos}. "
        "O la sonda no está midiendo lo que dice, o el piso volvió a ser `1`"
    )
    return pisos


def test_el_piso_del_helicorder_es_EL_MISMO_que_el_de_los_carriles_de_onda(tmp_path):
    """[T-7.23 · N1] Estaban INTERCAMBIADOS, 8.33× en cada sentido.

    `scaleFor` declara el piso en unidades físicas —0.10 cm/s en el geófono,
    0.012 g en los acelerómetros— y `pisoHeliCounts` los aplicaba al revés: le
    daba al geófono el piso de los acelerómetros y a los acelerómetros el del
    geófono. Su propio comentario afirmaba lo contrario, que es lo que hizo que
    nadie lo leyera dos veces. En pantalla: un carril de velocidad con el piso
    de aceleración dibuja un anillo en calma como un sismo, y al revés un sismo
    como una línea plana.

    La comparación se hace CONTRA EL PANEL y en su propia moneda: se le pide el
    piso del helicorder en counts, se pasa por `toPhys` —que es la única
    función que sabe qué unidad tiene cada canal— y tiene que dar exactamente
    lo que `scaleFor` declara sin pico encima. Cero constantes tecleadas aquí.
    """
    canales = (*_FAMILIAS, "ENN", "ENE", "EHN")
    valores = _evaluar(
        tmp_path,
        [
            # `peakHold` se vacía primero: `renderLanes` ya corrió y lo dejó con
            # el pico del fixture dentro, y entonces `scaleFor` no devolvería el
            # PISO sino el pico × 1.35.
            "(function(){for (const k in peakHold) delete peakHold[k];"
            f"return [toPhys({c!r}, pisoHeliCounts({c!r})), scaleFor({c!r}, null)];}})()"
            for c in canales
        ],
    )
    for canal, (del_heli, de_la_onda) in zip(canales, valores, strict=True):
        assert del_heli == pytest.approx(de_la_onda, rel=1e-9), (
            f"{canal}: el helicorder llama «plano» a {del_heli:g} y el carril de onda "
            f"a {de_la_onda:g} (×{del_heli / de_la_onda:.2f}). Las dos superficies del "
            "mismo panel tienen que usar el MISMO piso, y en la unidad de ESE canal"
        )


@pytest.mark.parametrize("canal", _FAMILIAS)
def test_un_anillo_en_calma_no_se_dibuja_como_un_terremoto(tmp_path, canal):
    """El comentario prometía un piso de escala y debajo ponía `let amp = 1`.

    Un count. O sea: ningún piso. El suelo quieto se dibujaba a pantalla
    completa, que es exactamente lo que el comentario decía estar evitando.

    **[T-7.23 · C4] Y la primera versión de esta guarda no podía ver el piso.**
    Medía ±9 counts contra «menos de 5 px de desvío»: nueve counts están tan
    lejos de cualquier piso plausible que la prueba salía verde con los dos
    pisos INTERCAMBIADOS. Ahora la amplitud se DERIVA del piso que el panel
    declara —un cuarto de él— y lo que se exige es la PROPORCIÓN: un cuarto del
    piso tiene que dibujarse a un cuarto del semieje. Con el piso equivocado por
    debajo, la amplitud lo supera y el trazo llena el lienzo; con el piso
    equivocado por encima, el trazo se aplasta contra el eje. Las dos cosas se
    ven desde aquí.
    """
    piso = _piso_esperado_en_counts(tmp_path)[canal]
    cuarto = int(round(piso / 4))
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(
            channel=canal,
            requested_channel=canal,
            segments=[
                {
                    "start": "2026-08-04T09:00:00+00:00",
                    "buckets": 3,
                    "dc_counts": 0.0,
                    "minmax": [-cuarto, cuarto, -cuarto, cuarto, -cuarto, cuarto],
                }
            ],
            gaps=[],
        ),
        canvasOps=True,
    )
    trazos = _ops(out, "heli-canvas", "stroke")
    assert trazos, "el helicorder no trazó nada"
    medio = (420 - 16) / 2
    desvio = max(max(abs(t["y0"] - medio), abs(t["y1"] - medio)) for t in trazos)
    esperado = _HELI_SEMIEJE / 4
    assert desvio == pytest.approx(esperado, abs=2.0), (
        f"{canal}: un cuarto del piso ({cuarto} counts de {piso:.0f}) se dibujó con "
        f"{desvio:.0f} px de desvío y tocaban {esperado:.0f}. Si es mucho más, el piso "
        "es demasiado bajo y el suelo en calma parece un sismo; si es mucho menos, es "
        "demasiado alto y un sismo de verdad se vería plano"
    )


@pytest.mark.parametrize("canal", _FAMILIAS)
def test_un_movimiento_de_verdad_si_llena_el_lienzo(tmp_path, canal):
    """La otra mitad del piso: por encima de él la escala SUBE con el dato.

    También derivada (`C4`): antes usaba ±400 000 counts, que superan cualquier
    piso plausible y por eso no podían delatar uno inflado 8.33×. Cuatro veces
    el piso declarado tiene que usar el semieje ENTERO.
    """
    piso = _piso_esperado_en_counts(tmp_path)[canal]
    grande = int(round(piso * 4))
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(
            channel=canal,
            requested_channel=canal,
            segments=[
                {
                    "start": "2026-08-04T09:00:00+00:00",
                    "buckets": 3,
                    "dc_counts": 0.0,
                    "minmax": [-grande, grande, -grande, grande, -grande, grande],
                }
            ],
            gaps=[],
        ),
        canvasOps=True,
    )
    trazos = _ops(out, "heli-canvas", "stroke")
    medio = (420 - 16) / 2
    desvio = max(max(abs(t["y0"] - medio), abs(t["y1"] - medio)) for t in trazos)
    assert desvio == pytest.approx(_HELI_SEMIEJE, abs=2.0), (
        f"{canal}: cuatro veces el piso ({grande} counts) se dibujó con {desvio:.0f} px "
        f"y el semieje son {_HELI_SEMIEJE:.0f}: la escala no está siguiendo al dato"
    )


# ================= [T-7.23 · M3] ninguna razón llega al muro en snake_case

_SERVIDOR = [
    Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "sismografo.py",
    Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "__init__.py",
]


def _razones_del_servidor() -> set[str]:
    """Las razones que los dos endpoints pueden emitir, DERIVADAS del código.

    Enumerarlas a mano aquí sería exactamente el censo que acaba divergiendo:
    la siguiente razón que alguien añada no estaría en la lista y el muro
    volvería a imprimir snake_case sin que nada se pusiera rojo.
    """
    razones: set[str] = set()
    for ruta in _SERVIDOR:
        razones |= set(
            re.findall(r'_degradado_(?:espectro|heli)\(\s*"([a-z_]+)"', ruta.read_text("utf-8"))
        )
    return razones


def _razones_del_panel() -> dict[str, str]:
    html = _INDEX.read_text("utf-8")
    i = html.index("const RAZONES_SISMO = {")
    bloque = html[i : html.index("};", i)]
    return {m[1]: m[2] for m in re.finditer(r"(\w+):\s*'([^']+)'", bloque)}


def test_el_barrido_de_razones_encuentra_las_dos_listas():
    """Sin esto, dos barridos vacíos se darían la razón el uno al otro."""
    assert len(_razones_del_servidor()) >= 8, _razones_del_servidor()
    assert len(_razones_del_panel()) >= 8, _razones_del_panel()


def test_toda_razon_que_el_servidor_emite_tiene_su_frase_en_el_panel():
    """Ocho razones se imprimían tal cual: «SIN ESPECTROGRAMA · canal_sin_muestras».

    Un guardia de pie frente al gabinete no lee snake_case. Y el censo del
    glosario (`test_glosario_de_estados.py`) tampoco las veía: extrae literales
    del HTML y éstas llegaban como DATO desde la API, así que entraban al panel
    sin pasar por el vocabulario del repositorio. Aquí se exige la igualdad en
    los dos sentidos: una razón sin frase deja snake_case en la pared, y una
    frase sin razón documenta un estado que ya no existe.
    """
    del_servidor, del_panel = _razones_del_servidor(), set(_razones_del_panel())
    assert del_servidor == del_panel, (
        "las razones del servidor y las frases del panel se separaron.\n"
        f"  · sin frase (saldrían en snake_case): {sorted(del_servidor - del_panel)}\n"
        f"  · frases huérfanas: {sorted(del_panel - del_servidor)}"
    )


def test_las_frases_de_las_razones_estan_en_el_vocabulario_del_panel():
    """Y que el censo del glosario las VEA: son literales del HTML, no datos."""
    from tests.test_glosario_de_estados import frases_del_panel

    vistas = frases_del_panel()
    faltan = [f for f in _razones_del_panel().values() if f not in vistas]
    assert not faltan, (
        "el censo del glosario no ve estas frases; si no las ve, nadie vigila que "
        f"usen el vocabulario del repositorio: {faltan}"
    )


# ============= [T-7.23 · M5] ninguna cifra medida viaja sin su procedencia

_SPEC = (
    Path(__file__).resolve().parents[2]
    / "takab-docs"
    / "design"
    / "edge-panel"
    / "ESPECIFICACION-PANEL-GABINETE.md"
)

#: Etiquetas admitidas. Una cifra tiene procedencia si dice de dónde salió:
#: `PROTOTIPO` = se midió la operación, no el endpoint servido; `MEDIDO` = se
#: midió lo que se nombra, en el equipo que se nombra.
_ETIQUETAS = ("PROTOTIPO", "MEDIDO")


def _cifras_medidas() -> set[str]:
    """Las cifras de coste, leídas de las tablas de la spec (§15.7 y §15.9).

    Se DERIVAN de la spec en vez de teclearse aquí: la spec es el sitio donde
    la cifra lleva su advertencia, así que es el sitio del que tiene que salir
    la lista de las que hay que vigilar en los ficheros que las repiten.

    [T-7.23 · N3] La §15.9 entró con la tabla del coste del saneo del cuerpo,
    que se repite en el docstring de `volcar_json`. Una tabla de cifras medidas
    que el censo no mirase sería justo el agujero que la §15.8 describe.
    """
    texto = _SPEC.read_text("utf-8")
    tramos = [
        texto[texto.index("### 15.7") : texto.index("\n**Cómo se re-miden")],
        texto[texto.index("### 15.9") : texto.index("### 15.10")],
    ]
    cifras: set[str] = set()
    for tramo in tramos:
        cifras |= set(re.findall(r"\d+\.\d+\s?(?:ms|s)\b", tramo))
        cifras |= set(re.findall(r"\d+(?:\.\d+)?\s?MB\b", tramo))
    return cifras


def _bloques_de_prosa(ruta: Path) -> list[tuple[int, int]]:
    """Los tramos del fichero donde vive PROSA: docstrings y comentarios."""
    texto = ruta.read_text("utf-8")
    spans: list[tuple[int, int]] = []
    if ruta.suffix == ".py":
        spans += [m.span() for m in re.finditer(r'"""[\s\S]*?"""', texto)]
        pos, actual = 0, None
        for linea in texto.splitlines(keepends=True):
            if linea.lstrip().startswith("#"):
                actual = (
                    (pos, pos + len(linea)) if actual is None else (actual[0], pos + len(linea))
                )
            elif actual is not None:
                spans.append(actual)
                actual = None
            pos += len(linea)
        if actual is not None:
            spans.append(actual)
    else:
        spans += [m.span() for m in re.finditer(r"/\*[\s\S]*?\*/", texto)]
        spans += [m.span() for m in re.finditer(r"<!--[\s\S]*?-->", texto)]
    return spans


def test_el_barrido_de_cifras_encuentra_la_tabla_de_costes():
    cifras = _cifras_medidas()
    assert len(cifras) >= 8, cifras
    assert any(c.replace(" ", "") == "0.89s" for c in cifras), cifras
    # …y la tabla nueva de la §15.9, que entró con el coste del saneo.
    assert any(c.replace(" ", "") == "9.95ms" for c in cifras), cifras


@pytest.mark.parametrize(
    "ruta",
    [
        Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "sismografo.py",
        Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "index.html",
        _LOCAL_API,
    ],
    ids=["sismografo.py", "index.html", "local_api/__init__.py"],
)
def test_ninguna_cifra_medida_se_repite_sin_su_etiqueta_de_procedencia(ruta):
    """Las mismas cifras estaban en tres sitios y sólo UNO llevaba la advertencia.

    La spec dice con todas las letras que son de PROTOTIPO —se midió la
    operación, no el endpoint servido—; el docstring del módulo y los
    comentarios del panel las repetían a secas. Una cifra sin procedencia se
    lee como definitiva, y la primera consecuencia ya se pagó en esta misma
    ficha: «importar scipy no cuesta RSS» era una conclusión sacada de una
    medición que medía otra cosa.
    """
    texto = ruta.read_text("utf-8")
    bloques = _bloques_de_prosa(ruta)
    huerfanas: list[str] = []
    linea_de = lambda pos: texto[:pos].count("\n") + 1  # noqa: E731
    for cifra in sorted(_cifras_medidas()):
        # `(?<!\d)` y `(?!\d)`: sin ellos, buscar «0 MB» casaba DENTRO de
        # «100 MB» y el censo señalaba una cifra que no existía.
        for m in re.finditer(r"(?<!\d)" + re.escape(cifra) + r"(?!\d)", texto):
            dentro = [b for b in bloques if b[0] <= m.start() < b[1]]
            if not dentro:
                huerfanas.append(
                    f"{cifra!r} fuera de todo comentario (línea {linea_de(m.start())})"
                )
                continue
            prosa = texto[dentro[0][0] : dentro[0][1]]
            if not any(e in prosa for e in _ETIQUETAS):
                huerfanas.append(
                    f"{cifra!r} en la línea {linea_de(m.start())} "
                    "sin PROTOTIPO ni MEDIDO en su comentario"
                )
    assert not huerfanas, f"cifras sin procedencia en {ruta.name}:\n" + "\n".join(
        "  · " + h for h in huerfanas
    )


# ================ [T-7.23] la rampa del espectrograma no es otra paleta


def test_la_vista_sismografo_no_estrena_su_propia_paleta():
    """`SPEC_PARADAS` y la franja del hueco eran la TERCERA y CUARTA copia.

    El censo de color del panel sólo sabe leer dos sitios: el `:root` del CSS y
    el objeto `const C`. Un color escrito en cualquier otro sitio es invisible
    para él — es literalmente lo que dejó al panel con cuatro violetas en
    T-2.137, uno de ellos inline en el rótulo que la persona lee. Aquí se exige
    que el bloque entero de esta vista no nombre ni un solo componente de la
    paleta a mano.
    """
    bloque = re.sub(r"/\*[\s\S]*?\*/", "", _bloque_sismografo())
    c = _paleta_c()
    trios = {tuple(int(v.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)): k for k, v in c.items()}
    copias: list[str] = []
    for patron in (
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)",
        r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]",
    ):
        for m in re.finditer(patron, bloque):
            trio = tuple(int(m.group(i)) for i in (1, 2, 3))
            if trio in trios:
                copias.append(f"{m.group(0)} es una copia de C.{trios[trio]}")
    assert not copias, "la vista sismógrafo escribe colores de la paleta a mano:\n" + "\n".join(
        "  · " + x for x in copias
    )
    # …y tampoco un `#RRGGBB`, que es la otra forma de escribir un color y la
    # que el barrido de tríos no ve. Así no hace falta saber de antemano en qué
    # notación vendrá la próxima copia.
    hexes = re.findall(r"#[0-9a-fA-F]{6}\b", bloque)
    assert not hexes, f"la vista sismógrafo escribe colores en hex a mano: {hexes}"


@pytest.mark.parametrize("crudo", ["inf", "-inf", "nan", "1e400", "Infinity"])
def test_el_parseo_de_hours_rechaza_lo_no_finito_en_la_PUERTA(crudo):
    """El saneador de la salida TAPA este arreglo: por eso lleva guarda propia.

    Medido: quitar el `math.isfinite` de `_helicorder_params` dejaba verde la
    prueba del cuerpo JSON, porque `sanear_no_finitos` convierte el infinito en
    `null` antes del socket. Las dos verjas son deliberadas —el parámetro se
    arregla donde se lee y el cuerpo se sanea donde se escribe—, y una verja
    sin guarda propia es una verja que alguien quita sin enterarse.
    """
    from takab_edge.local_api import _helicorder_params

    assert _helicorder_params(f"channel=EHZ&hours={crudo}") == ("EHZ", None)
    # …y la banda buena sigue pasando: el arreglo no puede ser «rechazarlo todo».
    assert _helicorder_params("channel=EHZ&hours=3") == ("EHZ", 3.0)


# ===== [T-7.23 · V1] la COBERTURA la comprueba el LECTOR, no el testigo


def test_un_fichero_que_este_proceso_no_vio_desordenarse_no_se_sirve_como_completo(supervisor):
    """El testigo del escritor sólo ve el desorden que ESE proceso presenció.

    Y el caso que más importa es justo el otro: al arrancar, el anillo siembra
    su listón con el ÚLTIMO REGISTRO del fichero, que en un fichero ya
    desordenado es el re-entregado —el más viejo—, así que todo lo que venga
    detrás parece «más nuevo» y no se marca nada. Un fichero escrito por otro
    proceso, o por el de antes del reinicio, llega aquí SIN testigo.

    El escenario es el real y está construido para que muerda donde muerde:
    una hora continua con un bloque de hace un minuto metido JUSTO EN EL
    MEDIO. La búsqueda binaria empieza probando el registro central; ése es
    ahora el viejo, sale «anterior o igual» al inicio de la ventana y el índice
    salta ahí. Resultado medido: se sirve de 14:30 en adelante para una ventana
    que empieza a las 14:00 — **media hora de dato que existe en el anillo y no
    se lee**. Y, hasta esta ficha, con `truncated: false`: la pantalla se veía
    llena y sin un solo aviso.

    La cobertura se mide ahora sobre la PRIMERA MUESTRA DECODIFICADA, que ya
    está en memoria y no cuesta nada más. `degraded` sigue en `false` a
    propósito: lo que se dibuja es cierto, lo que no era cierto es que fuese la
    ventana entera.
    """
    raiz = _raiz(supervisor)
    inicio = AHORA - timedelta(hours=1)
    _fabricar(raiz, "EHZ", inicio, 1800, paso_s=10)  # 14:00–14:30
    _fabricar(raiz, "EHZ", inicio - timedelta(minutes=1), 10, paso_s=10)  # 13:59, en medio
    _fabricar(raiz, "EHZ", inicio + timedelta(minutes=30), 1800, paso_s=10)  # 14:30–15:00

    from takab_edge.buffer import RingBuffer

    fichero = next(raiz.glob("*.mseed"))
    assert not RingBuffer.hay_desorden(fichero), (
        "este escenario tiene que llegar SIN testigo: con él, el helicorder dejaría de "
        "fiarse del índice y leería la cola entera (T-7.23 · Q2), que es el OTRO camino "
        "— y esta prueba no mediría el del lector"
    )

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is False, payload["reason"]
    # La pérdida es real y está medida, no supuesta: sin esto, una prueba que
    # sólo mirase `truncated` pasaría también con el anillo servido entero.
    primero = datetime.fromisoformat(payload["segments"][0]["start"])
    assert primero - inicio > timedelta(minutes=20), (
        f"lo servido empieza en {primero} y la ventana en {inicio}: este escenario ya "
        "no pierde dato, así que no está midiendo lo que dice medir"
    )
    assert payload["truncated"] is True, (
        "media hora de la ventana no se leyó y la respuesta la da por completa"
    )
    assert payload["truncated_reason"] == "anillo", payload["truncated_reason"]


def test_una_ventana_que_el_anillo_SI_cubre_no_se_declara_recortada(supervisor):
    """La otra mitad: una comprobación de cobertura que dijera «recortado» siempre
    sería igual de inútil que la que no decía nunca."""
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=70), 70 * 60, paso_s=10)
    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert payload["degraded"] is False, payload["reason"]
    assert payload["truncated"] is False and payload["truncated_reason"] is None


# ===== [T-7.23 · N2] el desorden se registra por TRANSICIÓN, no por paquete


def test_una_rafaga_fuera_de_orden_deja_UN_aviso_y_UNA_escritura(tmp_path, caplog, monkeypatch):
    """Esto corre en el hilo de ingesta de SeedLink, y justo en la reconexión.

    Que es cuando el Shake re-entrega bloques a puñados. La versión anterior
    soltaba un `log.warning` y reescribía el fichero testigo POR PAQUETE: una
    transición convertida en un intervalo (regla de oro 10) y una ráfaga de
    líneas contra la cota de log de T-7.47, en el peor momento posible. El
    hecho que el lector necesita —«este fichero perdió la monotonía»— ocurre
    UNA vez y se lee por existencia.
    """
    import logging

    from takab_edge.buffer import RingBuffer
    from takab_edge.config import BufferConfig

    escrituras: list[str] = []
    original = Path.write_text

    def espia(self, *a, **k):
        if self.suffix == ".desorden":
            escrituras.append(self.name)
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", espia)

    anillo = RingBuffer(BufferConfig(root=str(tmp_path), retention_days=7, max_bytes=10**9))
    base = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    for k in range(40):
        anillo.append(_paquete("EHZ", np.full(100, 5, dtype=np.int32), base + timedelta(seconds=k)))

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="takab_edge.buffer"):
        # La ráfaga: cuarenta bloques re-entregados, todos más viejos que el
        # último escrito. Es lo que llega tras una reconexión larga.
        for k in range(40):
            anillo.append(
                _paquete("EHZ", np.full(100, 7, dtype=np.int32), base + timedelta(seconds=k))
            )

    avisos = [r for r in caplog.records if "perdió el orden" in r.getMessage()]
    assert len(avisos) == 1, (
        f"cuarenta paquetes fuera de orden dejaron {len(avisos)} líneas de log: "
        "el hecho ocurre una vez y se registra una vez"
    )
    assert len(escrituras) == 1, (
        f"el testigo se reescribió {len(escrituras)} veces dentro del hilo de ingesta"
    )
    assert list(tmp_path.glob("*.desorden")), "…pero el testigo tiene que estar"


def test_al_reiniciar_el_edge_el_puntero_se_siembra_del_FICHERO(tmp_path):
    """[T-7.23 · C2] El caso que el comentario del anillo declara más importante.

    `_last_start` vive en memoria: tras un reinicio está vacío, y el primer
    paquete de un fichero que ya existe no tendría contra qué compararse. El
    desorden más probable es justo ése —el bloque re-entregado al reconectar,
    o sea al arrancar— así que sin la siembra sería el único que no se vería.
    No tenía ninguna guarda.
    """
    from takab_edge.buffer import RingBuffer
    from takab_edge.config import BufferConfig

    cfg = BufferConfig(root=str(tmp_path), retention_days=7, max_bytes=10**9)
    base = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)

    primero = RingBuffer(cfg)
    for k in range(5):
        primero.append(
            _paquete("EHZ", np.full(100, 5, dtype=np.int32), base + timedelta(seconds=k))
        )
    assert not list(tmp_path.glob("*.desorden")), (
        "el primer proceso escribió en orden y el anillo lo marcó igual"
    )

    # El edge se reinicia: anillo NUEVO, misma raíz, memoria en blanco.
    segundo = RingBuffer(cfg)
    segundo.append(_paquete("EHZ", np.full(100, 7, dtype=np.int32), base + timedelta(seconds=1)))
    assert list(tmp_path.glob("*.desorden")), (
        "el primer paquete tras un reinicio llegó más viejo que el último escrito y "
        "el anillo no lo vio: `_last_start` arrancó vacío y no se sembró del fichero"
    )


# ===== [T-7.23 · V2] el borde derecho del helicorder no dice «AHORA» porque sí


def test_el_helicorder_declara_la_edad_de_su_ultima_muestra(supervisor):
    """Los MISMOS cuatro campos que el espectrograma, con SU PROPIO umbral.

    El helicorder no los tenía: su lienzo rotulaba «AHORA» en el borde derecho
    con dato de cualquier edad. Y es peor que en el espectrograma, porque ese
    lienzo sólo se repinta cuando llega dato nuevo —cada 60 s por diseño, o
    nunca si el gabinete deja de contestar—, así que el rótulo se queda puesto
    en el bitmap.

    [T-7.23 · Q1] El umbral que declara es `RANCIO_HELI_S`, no el del
    espectrograma: compartirlo ponía la tarjeta en rojo casi todo el minuto con
    el sensor sano.
    """
    # Seis horas de ventana, con el sensor callado desde hace tres.
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(hours=6), 3 * 3600, paso_s=10)
    rancio = supervisor.local_api.helicorder("EHZ", 6.0, ahora=AHORA)
    assert rancio["degraded"] is False, rancio["reason"]
    assert rancio["stale"] is True
    assert rancio["stale_after_s"] == sismografo.RANCIO_HELI_S
    assert rancio["age_s"] > 3 * 3600 - 60, rancio["age_s"]
    # La hora de la última muestra es la que el lienzo va a estampar: tiene que
    # ser una cabecera del Shake, no el reloj del Pi.
    ultima = datetime.fromisoformat(rancio["last_sample_at"])
    assert AHORA - timedelta(hours=3, minutes=1) < ultima < AHORA - timedelta(hours=2, minutes=59)
    # Y sigue habiendo dibujo: `stale` NO es `degraded`.
    assert rancio["segments"]


def test_con_el_sensor_al_dia_el_helicorder_no_se_declara_rancio(supervisor):
    """La otra mitad: un `stale` que estuviera siempre puesto no diría nada."""
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=30), 30 * 60, paso_s=10)
    fresco = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)
    assert fresco["degraded"] is False, fresco["reason"]
    assert fresco["stale"] is False
    assert fresco["age_s"] < sismografo.RANCIO_S


# ===== [T-7.23 · Q1] el helicorder llega viejo POR DISEÑO y eso no es una alarma


def test_el_umbral_del_helicorder_se_deriva_de_su_cadencia_y_de_la_del_anillo():
    """El umbral del ESPECTROGRAMA, puesto al helicorder, era una falsa alarma.

    Medido con el arnés y el sensor al día (`age_s = 1.0 s` del servidor): a
    t=0 y t=9 s la tarjeta estaba bien y a t=11 s ya gritaba «EL SENSOR NO
    ENTREGA MUESTRAS NUEVAS» — unos 50 de cada 60 segundos en rojo con el
    gabinete sano. La causa no era el rótulo: era que se le aplicó a un dibujo
    del anillo de DISCO, que se re-pide cada 60 s y cuyo dato se escribe por
    registros, el umbral del anillo de RAM, que se re-pide a 1 Hz.

    El umbral de aquí se DERIVA de sus tres sumandos y ninguno se teclea dos
    veces: la cadencia sale del panel, el registro de una cuenta de registros
    medida sobre el anillo real, y el retraso tolerado al enlace es el que la
    tabla de salud ya pinta en rojo.
    """
    # La cadencia es la del panel, leída del panel.
    html = _INDEX.read_text("utf-8")
    m = re.search(r"const HELI_REFRESH_MS = (\d+);", html)
    assert m, "el panel ya no declara cada cuánto re-pide el helicorder"
    assert float(m.group(1)) / 1000.0 == sismografo.REFRESCO_HELI_S, (
        f"el panel re-pide el helicorder cada {float(m.group(1)) / 1000.0} s y el "
        f"servidor deriva su umbral de {sismografo.REFRESCO_HELI_S} s"
    )
    # …y la granularidad del anillo sale de una cuenta de registros, no de un
    # número redondo: 86 400 s entre los registros que tenía el fichero real.
    assert sismografo.GRANULARIDAD_ANILLO_S == 86400.0 / sismografo._REGISTROS_POR_DIA_MEDIDOS
    assert 3.0 < sismografo.GRANULARIDAD_ANILLO_S < 4.0, sismografo.GRANULARIDAD_ANILLO_S
    # El umbral ES la suma. Tecleado, se separaría de sus sumandos en silencio.
    assert sismografo.RANCIO_HELI_S == (
        sismografo.RANCIO_S + sismografo.GRANULARIDAD_ANILLO_S + sismografo.REFRESCO_HELI_S
    )
    # Y no es el del espectrograma: si volvieran a ser el mismo, vuelve la
    # falsa alarma. Los dos lienzos declaran el suyo.
    assert sismografo.RANCIO_HELI_S > sismografo.RANCIO_S


def test_el_retraso_normal_del_anillo_no_declara_rancio_el_helicorder(supervisor):
    """Un dato al día en el anillo de DISCO pasa del umbral del espectrograma.

    Y con el umbral compartido eso bastaba para acusar al sensor. El escenario
    pone la última muestra a `RANCIO_S + GRANULARIDAD_ANILLO_S`: el retraso que
    el panel ya tolera al enlace más el registro que el anillo todavía no ha
    escrito. Es lo normal, y con el umbral viejo salía `stale: true`.
    """
    _fabricar(_raiz(supervisor), "EHZ", AHORA - timedelta(minutes=30), 30 * 60, paso_s=10)
    retraso_sano = sismografo.RANCIO_S + sismografo.GRANULARIDAD_ANILLO_S
    payload = supervisor.local_api.helicorder(
        "EHZ", 1.0, ahora=AHORA + timedelta(seconds=retraso_sano)
    )
    assert payload["degraded"] is False, payload["reason"]
    assert payload["age_s"] > sismografo.RANCIO_S, (
        "este escenario ya no pasa del umbral del espectrograma: no mide lo que dice"
    )
    assert payload["stale"] is False, (
        f"con el sensor al día y {payload['age_s']:.1f} s de retraso normal el "
        "servidor ya declara rancio el helicorder"
    )


def test_el_anillo_sin_orden_se_advierte_en_la_tarjeta_y_el_dibujo_SIGUE(tmp_path):
    """[T-7.23 · Q2] Lo que la persona ve cuando el anillo perdió la monotonía.

    No es «SIN HELICORDER»: es el helicorder, dibujado, con una advertencia
    encima sobre la ventana. Las dos mitades juntas — un aviso que estuviera
    siempre puesto no diría nada, y un dibujo que desapareciera con el aviso
    sería el defecto que esta ficha quita.
    """
    con_aviso = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(ring_unordered=True),
        canvasOps=True,
    )
    meta = _txt(con_aviso, "sismo-heli-meta")
    assert "EL ANILLO DE DISCO LLEGÓ FUERA DE ORDEN" in meta, meta
    assert "ESTA VENTANA PUEDE ESTAR INCOMPLETA" in meta, meta
    assert "SIN HELICORDER" not in meta, "la advertencia se comió el helicorder"
    # …y el lienzo pintó de verdad: sin esto, un panel que dibujara la
    # advertencia sobre un canvas vacío pasaría.
    trazos = _ops(con_aviso, "heli-canvas", "fillRect") + _ops(con_aviso, "heli-canvas", "rect")
    assert trazos, "la tarjeta avisa y el lienzo está en blanco"

    sano = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
    )
    assert "FUERA DE ORDEN" not in _txt(sano, "sismo-heli-meta"), (
        "la advertencia sale con el anillo sano: entonces no advierte de nada"
    )


def test_con_el_dato_retenido_el_helicorder_no_rotula_AHORA(tmp_path):
    """Lo que la persona ve: el borde derecho deja de mentir y la tarjeta lo dice."""
    viejo = _heli_payload(
        last_sample_at="2026-08-04T07:00:00+00:00",
        age_s=10800.0,
        stale=True,
    )
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=viejo,
        canvasOps=True,
    )
    rotulos = [o["txt"] for o in _ops(out, "heli-canvas", "fillText")]
    assert "AHORA" not in rotulos, (
        f"el helicorder rotula «AHORA» sobre dato de hace tres horas: {rotulos}"
    )
    assert "07:00:00 UTC" in rotulos, f"…y tampoco dice la hora de la última muestra: {rotulos}"
    assert "DATO RETENIDO" in _txt(out, "sismo-heli-title"), _txt(out, "sismo-heli-title")
    assert "EL SENSOR NO ENTREGA MUESTRAS NUEVAS" in _txt(out, "sismo-heli-meta")


def test_con_el_dato_fresco_el_helicorder_si_dice_AHORA(tmp_path):
    """Control positivo: un rótulo que nunca apareciera dejaría la guarda hueca."""
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        canvasOps=True,
    )
    rotulos = [o["txt"] for o in _ops(out, "heli-canvas", "fillText")]
    assert "AHORA" in rotulos, rotulos
    assert "DATO RETENIDO" not in _txt(out, "sismo-heli-title")


#: [T-7.23 · Q1] Los instantes del ciclo de re-pedido en los que se mira la
#: tarjeta. Salen de las constantes y no de una lista de números: el 9 y el 11
#: son los dos que se midieron cuando el helicorder llevaba el umbral del
#: espectrograma —a t=9 s la tarjeta estaba bien y a t=11 s ya gritaba—, y el
#: último es el peor instante sano que existe, justo antes de que el kiosco
#: vuelva a preguntar. El veredicto crece de forma monótona con el reloj
#: (`age_s + desde`), así que si el peor instante no grita, ninguno grita.
_INSTANTES_DEL_CICLO = (
    0.0,
    sismografo.RANCIO_S - 1.0,
    sismografo.RANCIO_S + 1.0,
    sismografo.REFRESCO_HELI_S / 2.0,
    sismografo.REFRESCO_HELI_S - 1.0,
)


@pytest.mark.parametrize("segundos", _INSTANTES_DEL_CICLO, ids=lambda s: f"t+{s:g}s")
def test_con_el_sensor_sano_el_helicorder_no_grita_en_ningun_instante(tmp_path, segundos):
    """LA FALSA ALARMA DEL MURO, medida donde ocurría: en la pantalla.

    Con el umbral del espectrograma puesto al helicorder, la tarjeta se ponía
    en rojo con «EL SENSOR NO ENTREGA MUESTRAS NUEVAS» unos 50 de cada 60
    segundos teniendo el sensor perfectamente sano — porque este dibujo llega
    viejo POR DISEÑO y eso no es una avería.

    El dato del arnés es el del gabinete sano: `age_s = 1.0 s`, que es lo que
    sirve el servidor cuando el sensor está al día. Lo que se barre es el reloj
    del kiosco a lo largo del ciclo de re-pedido, y se comprueba que no hay ni
    un instante en que la tarjeta acuse a nadie.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(),
        now="2026-08-04T10:00:00+00:00",
        # El `resize:` al MISMO ancho no cambia el reparto: lo que hace es
        # ensuciar los lienzos (`invalidarLienzosSismo`) para que el último
        # fotograma REPINTE. Sin él, el helicorder no se redibuja —no ha
        # cambiado nada, que es lo correcto— y las órdenes del lienzo llegan
        # vacías: la guarda quedaría midiendo una lista vacía.
        clicks=["frame", f"clock:+{int(segundos * 1000)}", "tick", "resize:1920", "frame"],
        canvasOps=True,
    )
    pedidos = [f["url"] for f in out["fetches"] if "api/helicorder" in f["url"]]
    assert len(pedidos) == 1, (
        f"el kiosco re-pidió el helicorder dentro del ciclo: ya no se mide el "
        f"envejecimiento de UNA respuesta ({pedidos})"
    )
    meta, titulo = _txt(out, "sismo-heli-meta"), _txt(out, "sismo-heli-title")
    assert "EL SENSOR NO ENTREGA MUESTRAS NUEVAS" not in meta, (
        f"a t+{segundos:g} s la tarjeta acusa al sensor con el gabinete sano: {meta}"
    )
    assert "DATO RETENIDO" not in titulo, titulo
    # …y el borde derecho del lienzo sigue pudiendo decir «AHORA».
    rotulos = [o["txt"] for o in _ops(out, "heli-canvas", "fillText")]
    assert "AHORA" in rotulos, (
        f"a t+{segundos:g} s el lienzo ya estampa la hora de la última muestra: {rotulos}"
    )
    # La otra edad, la del DIBUJO, SÍ se declara y SÍ crece: son dos hechos
    # distintos y la tarjeta los separa. Sin esto, un panel que hubiera dejado
    # de rotular la edad pasaría esta guarda tan tranquilo.
    assert "CALCULADO HACE " + str(int(segundos)) + " s" in meta, meta


def test_con_el_sensor_callado_de_verdad_el_helicorder_si_lo_dice(tmp_path):
    """La otra dirección, sin la cual lo de arriba se arregla borrando el aviso.

    Tres horas de silencio: eso ya no lo explica ninguna cadencia.
    """
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=_heli_payload(
            last_sample_at="2026-08-04T07:00:00+00:00", age_s=10800.0, stale=True
        ),
        now="2026-08-04T10:00:00+00:00",
        clicks=["frame"],
        canvasOps=True,
    )
    assert "EL SENSOR NO ENTREGA MUESTRAS NUEVAS" in _txt(out, "sismo-heli-meta")
    assert "DATO RETENIDO" in _txt(out, "sismo-heli-title")
    assert "AHORA" not in [o["txt"] for o in _ops(out, "heli-canvas", "fillText")]


def test_el_bitmap_congelado_del_helicorder_deja_de_decir_AHORA_solo(tmp_path):
    """El caso que el espectrograma no tiene: el lienzo NO se repinta por reloj.

    El helicorder se re-pide cada 60 s, así que su bitmap vive quieto ese
    minuto entero — y para siempre si el gabinete deja de dar dato nuevo. Con
    el rótulo calculado una sola vez, «AHORA» se quedaba pegado a un dibujo
    cuya última muestra ya tenía una hora. El panel suma a la edad que declaró
    el servidor lo que ha corrido su propio reloj monótono desde la respuesta,
    y ensucia el lienzo cuando el veredicto cambia: no hay un segundo
    mecanismo, son los mismos `age_s`/`stale_after_s`.

    **[T-7.23 · Q1] El escenario cambió con el umbral.** Antes bastaba
    adelantar 30 s, porque el helicorder llevaba el umbral del espectrograma;
    eso era justamente la falsa alarma. Con el umbral propio —que descuenta el
    ciclo de re-pedido entero— un bitmap sólo puede envejecer hasta aquí si el
    gabinete DEJA DE DAR DATO NUEVO, así que el arnés contesta `ocupado` a la
    segunda petición: el kiosco conserva el dibujo bueno, no re-sella su reloj
    y la edad sigue corriendo. Eso es el bitmap congelado de verdad.
    """
    adelanto = int((sismografo.RANCIO_HELI_S + 1.0) * 1000)
    out = _render(
        tmp_path,
        status=_status_con_identidad(),
        search="?view=sismografo",
        helicorder=[
            _heli_payload(),
            _heli_payload(degraded=True, reason="ocupado", segments=[], gaps=[]),
        ],
        now="2026-08-04T10:00:00+00:00",
        clicks=["frame", f"clock:+{adelanto}", "tick", "frame"],
        canvasOps=True,
    )
    pedidos = [f["url"] for f in out["fetches"] if "api/helicorder" in f["url"]]
    assert len(pedidos) == 2, (
        f"el kiosco no volvió a preguntar: este escenario ya no es el del bitmap "
        f"que envejece sin dato nuevo ({pedidos})"
    )
    assert "SIN HELICORDER" not in _txt(out, "sismo-heli-meta"), (
        "un `ocupado` pisó el helicorder bueno que ya estaba en pantalla"
    )
    rotulos = [o["txt"] for o in _ops(out, "heli-canvas", "fillText")]
    assert rotulos, "el último fotograma no repintó el helicorder"
    assert "AHORA" not in rotulos, f"pasado el umbral, el lienzo sigue diciendo «AHORA»: {rotulos}"


def test_el_presupuesto_que_muerde_el_FICHERO_no_recorta_la_VENTANA(supervisor, monkeypatch):
    """[T-7.23 · Q2·bis] Quitar un apagón no puede dejar en su sitio una mentira.

    El arreglo del apagón hizo que, con el testigo de desorden puesto, el
    candidato a leer pase a ser el FICHERO ENTERO en vez de la ventana. La
    bandera del presupuesto seguía significando «mordió la ventana», así que
    desde ese día el helicorder rotulaba `RECORTADO · presupuesto` sobre
    ventanas servidas ENTERAS — y no como caso raro: el fichero EHZ real del
    gabinete pesa 100.2 MB a media tarde contra 48 MiB de presupuesto, o sea en
    cada petición durante más de media jornada.

    Aquí el anillo tiene DOS horas, la ventana pide UNA, el testigo está puesto
    y el presupuesto se baja a una fracción del fichero: muerde el fichero,
    no la ventana. `truncated` tiene que salir `False`, porque su contrato —
    escrito en la §15.4 de la spec— es «lo servido no llega tan atrás», no «la
    lectura costó menos de lo que hay en disco».
    """
    anillo = supervisor.buffer
    arranque = AHORA - timedelta(hours=2)
    for k in range(720):  # dos horas continuas, paso de 10 s
        anillo.append(
            _paquete(
                "EHZ", np.full(1000, 100, dtype=np.int32), arranque + timedelta(seconds=10 * k)
            )
        )
    # El paquete re-entregado que pone el testigo: es lo que hace que el lector
    # deje de fiarse del índice y lea la cola del fichero entero.
    anillo.append(
        _paquete("EHZ", np.full(1000, 7, dtype=np.int32), arranque - timedelta(minutes=1))
    )

    ruta = next(_raiz(supervisor).glob("*EHZ*.mseed"))
    tamano = ruta.stat().st_size
    # Derivado del fichero, no un número mágico: 60 % deja fuera la primera
    # hora larga —o sea el presupuesto MUERDE— y cubre de sobra la última.
    monkeypatch.setattr(sismografo, "PRESUPUESTO_BYTES", int(tamano * 0.6))

    payload = supervisor.local_api.helicorder("EHZ", 1.0, ahora=AHORA)

    assert payload["degraded"] is False, payload["reason"]
    assert payload["ring_unordered"] is True, "el escenario no puso el testigo: no mide lo que dice"
    # Control positivo: sin esto, un `truncated: False` podría venir de que el
    # presupuesto no mordió y la prueba no significaría nada.
    assert payload["bytes_read"] < tamano, (
        f"se leyeron {payload['bytes_read']} de {tamano} B: el presupuesto no mordió y este "
        "escenario no ejercita el defecto"
    )
    primero = datetime.fromisoformat(payload["segments"][0]["start"])
    assert primero <= AHORA - timedelta(hours=1) + timedelta(seconds=sismografo.BUCKET_S), (
        f"lo servido empieza en {primero} y la ventana en {AHORA - timedelta(hours=1)}: "
        "la ventana NO está cubierta y el escenario mide otra cosa"
    )
    assert payload["truncated"] is False and payload["truncated_reason"] is None, (
        f"la ventana está cubierta entera y el panel la rotula {payload['truncated_reason']!r}: "
        "el presupuesto mordió el FICHERO, no la VENTANA"
    )
