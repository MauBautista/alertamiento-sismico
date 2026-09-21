"""[T-7.23] Espectrograma y helicorder de la vista SISMÓGRAFO del panel.

Dos lecturas de sólo lectura, cada una sobre un anillo distinto y por razones
distintas (ver `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md §15`):

- **Espectrograma** — sale del anillo de RAM (`WaveformRing`, 60 s por canal,
  muestras crudas). `scipy.signal.spectrogram` sobre 60 s a 100 sps cuesta 2.4 ms
  con `nperseg=128` y 1.1 ms con 256 [PROTOTIPO · Pi 4 · 2026-09-20]. A 1 Hz es
  ruido.

  **El import SÍ cuesta, y la cifra anterior era falsa.** Aquí decía «0 MB:
  `obspy` ya arrastra `scipy` y ambos están mapeados». Lo que arrastra `obspy`
  es `scipy.integrate` y `scipy.fft`, NO `scipy.signal`: tras cargar lo que
  carga el arranque del edge, `scipy.signal` no está en `sys.modules` y el
  primer `from scipy import signal` cuesta **0.39 s y lleva el RSS de 94.3 a
  118.6 MB (+24.3 MB)** [MEDIDO · equipo de desarrollo x86-64 · Python 3.12 ·
  2026-09-20; el mismo día el escéptico midió 0.41 s y +24 MB]. Falta medirlo en
  el Pi, donde será igual o peor. Lo comprueba
  `test_scipy_signal_no_esta_cargado_tras_el_arranque_y_su_import_no_es_gratis`.

  **Y aun así el import se queda PEREZOSO, a sabiendas.** La primera petición a
  `/api/spectrogram` paga esos 0.39 s y esos +24 MB, una vez y para siempre, en
  el mismo proceso que corre SeedLink y las reglas. Se paga ahí y no en el
  arranque porque un gabinete que nunca abre esta vista —que son casi todos—
  no tiene por qué llevar 24 MB residentes en un Pi con ~260 MiB libres. Lo que
  ese cuarto de segundo NO puede tocar es la ruta de disparo: SASMEX→relé vive
  en OTRO proceso (`takab-gpio`, regla de oro 4), así que el peor efecto de la
  pausa es un tick del panel tarde y un segundo de SeedLink en el búfer del
  socket.

- **Helicorder** — sale del anillo de disco (miniSEED por día y canal). Aquí está
  la trampa que da forma a todo este módulo: `RingBuffer.extract_window()` hace
  `obspy.read()` del fichero del día ENTERO, y eso son **2.9 s y 159 MB de RSS
  pico** sobre el EHZ del 2026-09-20 (100.2 MB a media tarde), u **8.75 s y
  421 MB** sobre uno de 287 MB [PROTOTIPO · Pi 4 · 2026-09-20]. El Pi 4 tiene
  905.7 MiB de RAM y ~260 MiB libres en reposo: una pantalla no puede costar eso.
  Este módulo abre su propio camino ACOTADO —búsqueda binaria sobre las cabeceras
  miniSEED y lectura de la cola por desplazamiento de bytes— y lo medido es
  0.17 s leyendo 5.8 MB para 1 h y 0.89 s leyendo 34.5 MB para 6 h
  [PROTOTIPO · Pi 4 · 2026-09-20].

Y las dos reglas que gobiernan la forma del resultado.

**La cobertura se comprueba sobre el dato, no sobre el índice.** Lo que se
sirve puede no ser lo que se pidió —porque el anillo no llega tan atrás, porque
el presupuesto mordió, o porque la búsqueda binaria saltó mal sobre un fichero
desordenado que este proceso no vio desordenarse— y entonces se declara
(`truncated` con su razón) en vez de pintar media ventana como si fuera entera.
Y cuando el desorden SÍ se vio, la ventana sale marcada (`ring_unordered`) y el
helicorder **sigue dibujando**: apagar una pantalla de sismógrafo 30 h porque un
paquete llegó dos veces no protege a nadie [T-7.23 · Q2].
Se mide sobre el primer `segment`, que ya está decodificado: no cuesta nada y
no se puede confundir con la cabecera a la que saltó el índice, que es lo que
antes se comparaba y lo que deja de significar nada en cuanto hay desorden.

**Los huecos se cortan y se declaran.** El 2026-09-20 el anillo cubría 20.93 h
en siete tramos con seis huecos, así que una ventana de 1–6 h cruza un hueco
casi con seguridad. Rellenar con ceros escribiría «el suelo estuvo quieto»
justo donde no hubo medición, e interpolar inventaría movimiento; las dos
cosas, dentro de la pantalla de un sismógrafo. El hueco se queda en blanco y
sale rotulado — y el de COLA se declara en cuanto pasa de un bucket, porque es
dato que falta a la derecha del dibujo. Que ese hueco de cola signifique además
«el sensor calló» es OTRA pregunta y tiene su propio umbral (`RANCIO_HELI_S`):
un hueco de cola de unos segundos es la cadencia del anillo, no una avería.

Nada de aquí toca reglas, relés ni la ruta SASMEX→actuador (reglas de oro 1 y 4):
el dueño de los pines es otro proceso (`takab-gpio`) y este módulo no le habla.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import numpy as np

log = logging.getLogger("takab_edge.local_api.sismografo")

# --------------------------------------------------------------- espectrograma

#: Ventanas FFT admitidas. Son dos y no un rango porque cada una da una forma de
#: matriz medida y acotada (65×92 y 129×45 sobre 60 s a 100 sps): un `nperseg`
#: libre dejaría al kiosco elegir cuánta memoria reserva el gabinete.
NPERSEG_PERMITIDOS = (128, 256)
NPERSEG_DEFAULT = 128

#: Ventana de la escala en dB, rel. counts²/Hz. Es FIJA a propósito y sale de los
#: extremos del propio instrumento, no del gusto de nadie:
#:
#:   · el ADC del RS4D es de 24 bits ⇒ counts hasta ~8.4·10⁶. A 100 sps, una
#:     señal a fondo de escala concentra ~10¹² counts²/Hz, o sea ~120 dB;
#:   · 1 count rms repartido en la banda cae cerca de −17 dB.
#:
#: De ahí [−20, +130]: cubre el rango completo del sensor con holgura por los dos
#: lados. Que sea fija es lo que permite comparar: con una escala automática por
#: petición, dos columnas pintadas con un minuto de diferencia dejarían de
#: significar lo mismo, que es justo para lo que sirve un espectrograma. Lo que
#: se sale se CUENTA (`below_scale`/`above_scale`), no se disimula.
ESCALA_DB_MIN = -20.0
ESCALA_DB_MAX = 130.0

#: Suelo numérico antes del logaritmo. No es un umbral físico: es lo que impide
#: un `-inf` en una celda donde la densidad dio exactamente cero.
_PSD_MINIMA = 1e-12

#: [T-7.23 · A2] A partir de aquí un dibujo DEJA DE PRESENTARSE COMO «ahora».
#: Hacía falta porque `WaveformRing` sólo poda al appendear: con el sensor
#: callado el último tramo se queda en RAM indefinidamente, y el endpoint lo
#: servía con `degraded: false` y la pantalla lo rotulaba «últimos 60 s ·
#: AHORA» con dato de hace horas. Regla de oro 7, del revés, en la pantalla de
#: un sismógrafo.
#:
#: [T-7.23 · V2] **Los cuatro campos son los mismos para los dos lienzos; el
#: NÚMERO no.** Se llamaba `ESPECTRO_RANCIO_S` y sólo lo aplicaba el
#: espectrograma; el helicorder rotulaba «AHORA» en su borde derecho con dato
#: de cualquier edad y, como su lienzo sólo se repinta cuando llega dato nuevo,
#: ese rótulo se quedaba puesto en un bitmap de hace una hora. El helicorder
#: declara desde entonces los MISMOS cuatro campos (`last_sample_at`, `age_s`,
#: `stale`, `stale_after_s`) y el panel los pinta con la misma función.
#:
#: **[T-7.23 · Q1] Lo que NO podía compartir es el umbral, y compartirlo costó
#: una falsa alarma en el muro.** Este número mide el retraso del anillo de
#: RAM, que se re-pide a 1 Hz; el helicorder sale del anillo de DISCO y se
#: re-pide cada 60 s. Con los dos lienzos a 10 s, medido con el arnés y el
#: sensor al día (`age_s = 1.0 s`), la tarjeta del helicorder estaba bien a
#: t=0 y t=9 s y ya gritaba «EL SENSOR NO ENTREGA MUESTRAS NUEVAS» a t=11 s:
#: unos 50 de cada 60 segundos en rojo con el gabinete sano. El umbral del
#: helicorder es otro y se deriva de SU cadencia (`RANCIO_HELI_S`).
#:
#: El número NO se inventa aquí: son los MISMOS 10 s con los que el panel ya
#: pinta en rojo el «Retraso del sensor» (`col(h.seedlink_lag_s, 2, 10)` en
#: `renderSalud`). Las dos superficies que miden lo MISMO —el retraso del dato
#: que llega por SeedLink— tienen que decir lo mismo, y por eso este número es
#: uno solo. El helicorder mide otra cosa; ahí la exigencia no es compartir el
#: número, es DERIVARLO (`RANCIO_HELI_S`, que arranca justo de éste). Por
#: debajo de eso el retraso normal del enlace —~0.4 s medidos en el gabinete—
#: cabe con holgura y el rótulo no parpadea.
#:
#: No es `degraded`: hay dibujo y es cierto, lo que ya no es cierto es el rótulo
#: del borde derecho. Por eso viaja como estado propio (`stale`) con su edad, y
#: no como un color más pálido.
RANCIO_S = 10.0

# ------------------------------------------------------------------ helicorder

#: [T-7.23 · Q1] Cada cuánto RE-PIDE el panel el helicorder. No es una cifra de
#: adorno: es el sumando MAYOR del umbral de abajo. El panel lo tiene en
#: `HELI_REFRESH_MS` y aquí se declara en segundos porque el servidor es quien
#: sirve el umbral; que los dos números sigan siendo el mismo lo comprueba
#: `test_el_umbral_del_helicorder_se_deriva_de_su_cadencia_y_de_la_del_anillo`,
#: que lo lee del panel en vez de teclearlo dos veces.
REFRESCO_HELI_S = 60.0

#: [T-7.23 · Q1] Segundos de dato que cubre UN registro del anillo de disco.
#:
#: El anillo no escribe muestra a muestra: `RingBuffer.append` vuelca cada
#: paquete de SeedLink como un registro miniSEED completo, así que entre dos
#: escrituras la última muestra EN DISCO se queda quieta. Eso no es el sensor
#: callándose: es la granularidad de la escritura, y hay que descontarla antes
#: de acusar a nadie.
#:
#: Sale de contar los registros del fichero EHZ real de un día del anillo del
#: gabinete: **26 305 registros para 86 400 s** [MEDIDO · fichero EHZ de un día
#: del anillo de `gw-dev-0001` · 2026-09-20], o sea 3.28 s por registro. Se
#: escribe la DIVISIÓN y no el cociente para que la cifra que se teclea sea la
#: que se contó, y no una que alguien redondeó por el camino.
_REGISTROS_POR_DIA_MEDIDOS = 26305
GRANULARIDAD_ANILLO_S = 86400.0 / _REGISTROS_POR_DIA_MEDIDOS

#: [T-7.23 · Q1] «EL SENSOR NO ENTREGA MUESTRAS NUEVAS», PARA EL HELICORDER.
#:
#: Hay DOS hechos distintos y estaban mezclados en uno:
#:
#:   (a) «este dibujo se calculó hace N s» — lo declara la tarjeta
#:       (`CALCULADO HACE …`) y es NORMAL que crezca hasta un minuto entero:
#:       el helicorder se re-pide cada `REFRESCO_HELI_S`;
#:   (b) «el sensor dejó de entregar» — una propiedad del DATO, que la tabla
#:       de salud ya mide a 1 Hz por otro camino (`seedlink_lag_s`).
#:
#: Aplicarle a (b) el umbral del espectrograma —`RANCIO_S`, que mide el retraso
#: del anillo de RAM— ponía la tarjeta en rojo unos 50 de cada 60 segundos con
#: el sensor sanísimo. El umbral de aquí se DERIVA de las tres cosas que, con
#: el gabinete sano, separan la última muestra del reloj del kiosco:
#:
#:   RANCIO_S              el retraso que el panel ya tolera al enlace (10 s)
#: + GRANULARIDAD_ANILLO_S el registro que el anillo todavía no ha escrito
#: + REFRESCO_HELI_S       lo que el panel tarda en volver a preguntar
#:
#: Por debajo de esa suma, un helicorder viejo es lo esperado y no se acusa a
#: nadie; por encima, ya no cabe explicarlo con la cadencia y lo que queda es
#: que el sensor calló. Lo sirve el servidor en `stale_after_s` y el panel le
#: suma lo que ha corrido su propio reloj monótono, igual que antes: lo que
#: cambia es el número, no el mecanismo.
RANCIO_HELI_S = RANCIO_S + GRANULARIDAD_ANILLO_S + REFRESCO_HELI_S


#: Banda de horas servibles. El techo es presupuesto de memoria del Pi, no
#: estética: 6 h de un canal son ~34.5 MB leídos [PROTOTIPO · Pi 4 ·
#: 2026-09-20], y obspy pide alrededor de vez y media eso en RSS mientras parsea.
HORAS_MIN = 1.0
HORAS_MAX = 6.0
HORAS_DEFAULT = 1.0

#: Tope duro de lectura por petición. **Re-derivado con los 24 MB de
#: `scipy.signal` DENTRO de la cuenta**: la cifra vieja se calculó creyendo que
#: importarlo era gratis, y no lo es (ver el docstring del módulo). La cuenta
#: entera, con todo medido el 2026-09-20:
#:
#:   Pi 4, 905.7 MiB de RAM, ~260 MiB libres en reposo [PROTOTIPO · Pi 4]
#:   − 24.3 MB  `scipy.signal`, residentes desde la primera petición de la vista
#:              [MEDIDO · equipo de desarrollo x86-64]
#:   = ~236 MiB libres con la vista SISMÓGRAFO abierta
#:   − ~76 MB   pico de RSS de una lectura de 48 MiB (obspy pide ~1.5× lo leído)
#:   = ~160 MiB libres en el peor instante
#:
#: Y el número NO baja, porque no lo ata la memoria sino el dato: 6 h de EHZ
#: midieron 34.5 MB [PROTOTIPO · Pi 4 · 2026-09-20], así que cualquier tope por
#: debajo de ~35 MB convertiría `truncated_reason: "presupuesto"` en el
#: desenlace NORMAL de una ventana de 6 h sobre el anillo real. 48 MiB es esos
#: 34.5 MB con 1.46× de holgura para un anillo más denso, y sigue dejando
#: ~160 MiB libres en el peor instante. Por encima, la ventana se recorta POR EL
#: PRINCIPIO —se conserva lo nuevo— y se declara `truncated_reason:
#: "presupuesto"`.
PRESUPUESTO_BYTES = 48 * 1024 * 1024

#: Un par mín/máx por segundo. Es la cadencia clásica del helicorder y la que
#: hace que 6 h quepan en una pantalla sin decimar otra vez.
BUCKET_S = 1.0

#: Longitud de registro de respaldo cuando la cabecera no la declara. El anillo
#: escribe con el valor por defecto de obspy (4096 B, verificado en el gabinete),
#: pero el número REAL se lee del fichero: un anillo escrito con otra longitud
#: dejaría todos los desplazamientos desalineados en silencio.
_RECLEN_DE_RESPALDO = 4096


def _mseed():
    """Import perezoso de obspy. El módulo se importa en el arranque del panel."""
    from obspy import Stream, UTCDateTime, read
    from obspy.io.mseed.util import get_record_information

    return Stream, UTCDateTime, read, get_record_information


def _degradado_espectro(razon: str, *, canal_pedido: str | None, nperseg: int) -> dict:
    """La forma degradada del espectrograma: 200 con su razón, jamás un 500."""
    return {
        "degraded": True,
        "reason": razon,
        "channel": None,
        "requested_channel": canal_pedido,
        "sample_rate": None,
        "nperseg": nperseg,
        "noverlap": nperseg // 2,
        "window": "hann",
        "freq_hz": [],
        "t_offset_s": [],
        "first_sample_at": None,
        # [T-7.23 · A2] Los tres campos de la EDAD viajan también en la forma
        # degradada: un consumidor que sólo los leyera en la buena tendría que
        # inventarse qué significa su ausencia.
        "last_sample_at": None,
        "age_s": None,
        "stale": False,
        "stale_after_s": RANCIO_S,
        "gap_before": False,
        "dc_counts": None,
        "db_min": ESCALA_DB_MIN,
        "db_max": ESCALA_DB_MAX,
        "rows": [],
        "below_scale": 0,
        "above_scale": 0,
    }


def acotar_nperseg(pedido: int | None) -> int:
    """Ilegal ⇒ default, jamás un 400 al kiosco (doctrina de `_waveform_params`)."""
    return pedido if pedido in NPERSEG_PERMITIDOS else NPERSEG_DEFAULT


def acotar_horas(pedidas: float | None) -> float:
    if pedidas is None or not math.isfinite(pedidas):
        return HORAS_DEFAULT
    return float(min(HORAS_MAX, max(HORAS_MIN, pedidas)))


def elegir_canal(disponibles: list[str], pedido: str | None) -> str | None:
    """El pedido si existe; si no, EHZ (el geófono) y en último término el primero.

    Sustituir en vez de devolver 400 es deliberado: el kiosco pinta algo y el
    rótulo dice qué canal es de verdad. Lo que no puede pasar es que el panel
    nombre el canal PEDIDO sobre una traza que es de otro.
    """
    if not disponibles:
        return None
    if pedido in disponibles:
        return pedido
    return "EHZ" if "EHZ" in disponibles else disponibles[0]


def espectrograma(
    ring,
    canal_pedido: str | None,
    nperseg_pedido: int | None,
    ahora: datetime | None = None,
) -> dict:
    """Matriz `uint8` del espectrograma del último tramo continuo de un canal.

    `ahora` es el reloj con el que se mide la EDAD del dato; lo inyectan las
    pruebas. Sin él no hay forma de escribir una guarda del estado `stale` que
    no dependa de esperar diez segundos de reloj de pared.
    """
    # Import PEREZOSO, a sabiendas: 0.39 s y +24.3 MB la primera vez [MEDIDO ·
    # equipo de desarrollo x86-64 · 2026-09-20]. Ver el docstring del módulo:
    # quien no abre esta vista no paga los 24 MB, y la ruta de disparo vive en
    # otro proceso, así que la pausa no puede tocar un relé.
    from scipy import signal as _senal

    nperseg = acotar_nperseg(nperseg_pedido)
    if ring is None:
        return _degradado_espectro("sin_anillo", canal_pedido=canal_pedido, nperseg=nperseg)

    canal = elegir_canal(ring.canales(), canal_pedido)
    if canal is None:
        return _degradado_espectro("canal_sin_muestras", canal_pedido=canal_pedido, nperseg=nperseg)
    tramo = ring.tramo_crudo(canal)
    if tramo is None or tramo["samples"].size == 0:
        return _degradado_espectro("canal_sin_muestras", canal_pedido=canal_pedido, nperseg=nperseg)
    if tramo["samples"].size < nperseg:
        return _degradado_espectro(
            "muestras_insuficientes", canal_pedido=canal_pedido, nperseg=nperseg
        )

    muestras = tramo["samples"].astype(np.float64)
    # La media se resta AQUÍ y se publica: el acelerómetro lleva ~1 g de continua
    # en ENZ y un bias de fábrica en ENN/ENE, y sin quitarlo la primera fila del
    # espectrograma se come toda la escala. `detrend=False` a propósito — con el
    # detrend por ventana de scipy, `dc_counts` sólo contaría parte de la verdad.
    dc = float(muestras.mean())
    muestras -= dc
    sr = float(tramo["sample_rate"])
    freqs, tiempos, densidad = _senal.spectrogram(
        muestras,
        fs=sr,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend=False,
        scaling="density",
        mode="psd",
    )
    db = 10.0 * np.log10(np.maximum(densidad, _PSD_MINIMA))
    debajo = int((db < ESCALA_DB_MIN).sum())
    encima = int((db > ESCALA_DB_MAX).sum())
    escala = 255.0 / (ESCALA_DB_MAX - ESCALA_DB_MIN)
    matriz = np.clip(np.rint((db - ESCALA_DB_MIN) * escala), 0, 255).astype(np.uint8)
    # [T-7.23 · A2] La EDAD del dato, que es lo que decide si el borde derecho
    # puede seguir diciendo «AHORA». No hay monotónico compartido entre el Shake
    # y el Pi, así que pared es lo correcto aquí y no se puede mejorar: un salto
    # de NTP mueve la edad, no la inventa, y es la misma pareja de relojes con
    # la que el panel ya mide el «Retraso del sensor».
    ultima = tramo["last_sample_at"]
    referencia = (ahora or datetime.now(UTC)).astimezone(UTC)
    # reloj: ajeno — `ultima` es una cabecera miniSEED sellada por el Shake.
    edad = (referencia - ultima).total_seconds()
    return {
        "degraded": False,
        "reason": None,
        "channel": canal,
        "requested_channel": canal_pedido,
        "sample_rate": sr,
        "nperseg": nperseg,
        "noverlap": nperseg // 2,
        "window": "hann",
        "freq_hz": [float(f) for f in freqs],
        "t_offset_s": [float(t) for t in tiempos],
        "first_sample_at": tramo["first_sample_at"].isoformat(),
        "last_sample_at": ultima.isoformat(),
        "age_s": edad,
        "stale": bool(edad > RANCIO_S),
        "stale_after_s": RANCIO_S,
        "gap_before": bool(tramo["gap_before"]),
        "dc_counts": dc,
        "db_min": ESCALA_DB_MIN,
        "db_max": ESCALA_DB_MAX,
        "rows": matriz.tolist(),
        "below_scale": debajo,
        "above_scale": encima,
    }


# --------------------------------------------------------------- el anillo


def canales_del_anillo(raiz: Path) -> list[str]:
    """Canales presentes en el anillo de disco, DERIVADOS de los nombres.

    Enumerarlos a mano (o leerlos de la config de SeedLink) diría qué canales
    DEBERÍA haber, no cuáles hay: un canal que el sensor dejó de entregar hace
    tres días seguiría ofreciéndose en la pantalla.
    """
    canales: set[str] = set()
    for ruta in raiz.glob("*.mseed"):
        partes = ruta.stem.split(".")
        if len(partes) >= 5:
            canales.add(partes[-2])
    return sorted(canales)


def _fichero_del_dia(raiz: Path, canal: str, dia: datetime) -> Path | None:
    encontrados = sorted(raiz.glob(f"*.{canal}.{dia.strftime('%Y%m%d')}.mseed"))
    return encontrados[0] if encontrados else None


#: [T-7.23 · Q2] Ficheros de los que este proceso YA avisó al leer.
#:
#: El desorden dura lo que dura el fichero del día —unas 30 h— y el kiosco
#: pregunta cada 60 s, así que un `log.warning` por lectura son ~1800 líneas
#: sobre un hecho que ocurrió UNA vez: un intervalo disfrazado de evento (regla
#: de oro 10) contra la cota de log de T-7.47. Antes no se notaba porque la
#: respuesta era degradada y nadie miraba la pantalla mucho rato; ahora el
#: helicorder sigue sirviendo y el kiosco se queda abierto.
#:
#: No es el mismo registro que el del escritor (`RingBuffer._marcar_desorden`):
#: aquél anota la TRANSICIÓN en el instante en que la presencia, y se le escapa
#: justo el fichero que ya llegó desordenado —de otro proceso, o del de antes
#: del reinicio—, donde el testigo existe y nadie lo anotó nunca. Éste cubre
#: ese caso, y por eso no sobra.
_DESORDEN_AVISADO: set[Path] = set()


def _avisar_del_desorden(ruta: Path) -> None:
    if ruta in _DESORDEN_AVISADO:
        return
    _DESORDEN_AVISADO.add(ruta)
    log.warning(
        "panel LAN: %s tiene registros fuera de orden; el helicorder sirve la cola "
        "por presupuesto y declara la cobertura",
        ruta.name,
    )


def _hay_desorden(ruta: Path) -> bool:
    """¿El escritor marcó este fichero como fuera de orden? (`M2`)

    Se importa el anillo AQUÍ y no arriba para no atar el módulo de la pantalla
    al del disco: el panel jamás escribe en el anillo y esto es lo único que le
    pregunta.
    """
    from takab_edge.buffer import RingBuffer

    return RingBuffer.hay_desorden(ruta)


def _indice_del_instante(fh, get_record_information, reclen: int, nrec: int, objetivo) -> int:
    """Índice del ÚLTIMO registro que empieza en o antes de `objetivo` (0 si ninguno).

    Búsqueda binaria sobre las CABECERAS: con el fichero escrito en orden
    cronológico y registros de longitud fija, el índice es una función monótona
    del tiempo y hacen falta ~log2(N) lecturas de cabecera —15 para un fichero
    de 100 MB— en vez de parsear el día entero.

    **Esa precondición no se SUPONE, y tampoco basta con avisar de ella.**
    Decía «el anillo sólo appendea» como si appendear implicara orden, y no lo
    implica: `RingBuffer.append` escribe lo que llegue y la deduplicación de
    SeedLink es un `deque` acotado, así que tras una reconexión larga el Shake
    puede re-entregar un bloque que el deque ya olvidó. Con el fichero
    desordenado esta función devuelve cualquier cosa y la cola que se lee a
    partir de ahí **pierde dato sin decirlo**. Dos cosas la vigilan, y no son
    lo mismo:

    - **el AVISO**, del escritor: quien llama mira primero el testigo
      `RingBuffer.hay_desorden` y, si está puesto, **ni siquiera llama aquí**:
      sirve la cola por presupuesto y marca la respuesta con `ring_unordered`
      [T-7.23 · Q2]. Cuesta una comparación por paquete y llega antes, pero
      **sólo ve el desorden que ese proceso presenció** — ver
      `_DESORDEN_SUFIJO` en `takab_edge/buffer`;
    - **la GARANTÍA**, del lector: pase lo que pase aquí, `helicorder()`
      compara la PRIMERA MUESTRA DECODIFICADA con el inicio de la ventana y
      declara `truncated` si no llega tan atrás. Es la que cubre un fichero que
      ya llegó desordenado, que es justo el que el testigo no ve.
    """
    bajo, alto, respuesta = 0, nrec - 1, 0
    while bajo <= alto:
        medio = (bajo + alto) // 2
        inicio = get_record_information(fh, offset=medio * reclen)["starttime"]
        if inicio <= objetivo:
            respuesta = medio
            bajo = medio + 1
        else:
            alto = medio - 1
    return respuesta


def _rango_de_bytes(ruta: Path, desde, get_record_information) -> tuple[int, int] | None:
    """`(offset, fin)` de la cola de `ruta` que cubre desde `desde`.

    `fin` descarta un registro a medio escribir al final del fichero: el anillo
    se appendea mientras esto lee, y pasarle a obspy media cabecera es un error
    que no distingue de un fichero corrupto.

    **`desde=None` = no hay índice en el que confiar** [T-7.23 · Q2]. Es lo que
    pasa el llamador cuando el fichero lleva el testigo de desorden: con el
    fichero fuera de orden la búsqueda binaria devuelve cualquier cosa, así que
    en vez de localizar se declara candidato el fichero ENTERO y que lo recorte
    el presupuesto, por la cola, que es donde vive lo reciente. Cuesta más
    disco que localizar —hasta `PRESUPUESTO_BYTES` en vez de los 5.8 MB de una
    hora [PROTOTIPO · Pi 4 · 2026-09-20]— y ese es exactamente el precio de
    seguir dibujando en vez de apagar la pantalla.

    **[T-7.23 · V1] Ya no devuelve el instante de la cabecera elegida.** Lo
    devolvía, y quien llama lo usaba para decidir si la ventana iba `truncated`.
    Es justo el dato que MIENTE cuando el fichero está desordenado: la búsqueda
    binaria salta a un registro cualquiera y su cabecera puede ser anterior a
    `desde` aunque el dato que de verdad se sirva empiece mucho después. La
    cobertura se mide ahora sobre lo DECODIFICADO, no sobre el índice.
    """
    tamano = ruta.stat().st_size
    if tamano == 0:
        return None
    with open(ruta, "rb") as fh:
        cabecera = get_record_information(fh, offset=0)
        reclen = int(cabecera.get("record_length") or _RECLEN_DE_RESPALDO)
        fin = tamano - (tamano % reclen)
        if fin <= 0:
            return None
        if desde is None:
            return 0, fin
        nrec = fin // reclen
        indice = _indice_del_instante(fh, get_record_information, reclen, nrec, desde)
    return indice * reclen, fin


def _degradado_heli(
    razon: str,
    *,
    canal: str | None,
    canal_pedido: str | None,
    horas: float,
    horas_pedidas: float | None,
    ventana: tuple[datetime, datetime] | None = None,
    desordenado: bool = False,
) -> dict:
    return {
        "degraded": True,
        "reason": razon,
        "channel": canal,
        "requested_channel": canal_pedido,
        "hours": horas,
        "requested_hours": horas_pedidas,
        "window_start": ventana[0].isoformat() if ventana else None,
        "window_end": ventana[1].isoformat() if ventana else None,
        "sample_rate": None,
        "bucket_s": BUCKET_S,
        # [T-7.23 · V2] Los cuatro campos de la EDAD viajan también en la forma
        # degradada, por la misma razón que en el espectrograma: un consumidor
        # que sólo los leyera en la buena tendría que inventarse qué significa
        # su ausencia.
        "last_sample_at": None,
        "age_s": None,
        "stale": False,
        "stale_after_s": RANCIO_HELI_S,
        "segments": [],
        "gaps": [],
        "bytes_read": 0,
        "files": [],
        "truncated": False,
        "truncated_reason": None,
        # [T-7.23 · Q2] Viaja también aquí: una ventana sin dato sobre un anillo
        # que perdió la monotonía y otra sobre un anillo sano son dos cosas
        # distintas, y el operador tiene que poder distinguirlas.
        "ring_unordered": desordenado,
    }


def _minmax_por_segundo(muestras: np.ndarray, por_bucket: int) -> list[int]:
    """Pares APLANADOS `[mín0, máx0, …]`, uno por segundo.

    Mismo formato y misma razón que la decimación de `/api/waveform`: un
    submuestreo se salta el pico y dibuja un sismo más chico del que fue. El
    último bucket incompleto se rellena repitiendo la última muestra, que no
    inventa amplitud (su mín y su máx no cambian).
    """
    n = muestras.size
    buckets = math.ceil(n / por_bucket)
    sobra = buckets * por_bucket - n
    if sobra:
        muestras = np.concatenate([muestras, np.full(sobra, muestras[-1], dtype=muestras.dtype)])
    rejilla = muestras.reshape(buckets, por_bucket)
    salida = np.empty(buckets * 2, dtype=np.int64)
    salida[0::2] = rejilla.min(axis=1)
    salida[1::2] = rejilla.max(axis=1)
    return [int(v) for v in salida]


def helicorder(
    raiz: Path,
    canal_pedido: str | None,
    horas_pedidas: float | None,
    ahora: datetime,
) -> dict:
    """1–6 h del anillo de disco en mín/máx a 1 Hz, cortadas por cada hueco."""
    Stream, UTCDateTime, read, get_record_information = _mseed()

    horas = acotar_horas(horas_pedidas)
    fin = ahora.astimezone(UTC)
    inicio = fin - timedelta(hours=horas)
    ventana = (inicio, fin)

    canales = canales_del_anillo(raiz)
    canal = elegir_canal(canales, canal_pedido)
    if canal is None:
        return _degradado_heli(
            "canal_sin_ficheros",
            canal=None,
            canal_pedido=canal_pedido,
            horas=horas,
            horas_pedidas=horas_pedidas,
            ventana=ventana,
        )

    # Los días se recorren del MÁS NUEVO al más viejo: si el presupuesto muerde,
    # lo que se conserva tiene que ser lo reciente. Después se re-ordena.
    dias: list[datetime] = []
    dia = datetime(fin.year, fin.month, fin.day, tzinfo=UTC)
    limite = datetime(inicio.year, inicio.month, inicio.day, tzinfo=UTC)
    while dia >= limite:
        dias.append(dia)
        dia -= timedelta(days=1)

    presupuesto = PRESUPUESTO_BYTES
    leidos = 0
    recortado_por_presupuesto = False
    desordenado = False
    trozos: list[tuple[datetime, bytes]] = []
    ficheros: list[str] = []
    try:
        for dia in dias:
            if presupuesto <= 0:
                recortado_por_presupuesto = True
                break
            ruta = _fichero_del_dia(raiz, canal, dia)
            if ruta is None:
                continue
            # [T-7.23 · Q2] EL DESORDEN ES UNA ADVERTENCIA SOBRE LA VENTANA, NO
            # UN APAGADO. Esto devolvía `degraded: anillo_desordenado` y dejaba
            # la pantalla del sismógrafo en blanco hasta que ese fichero del día
            # saliera del anillo — unas 30 h — porque un paquete había llegado
            # dos veces. Es peor que el defecto que arreglaba: una reconexión
            # larga de SeedLink re-entrega bloques por diseño (ver
            # `_DESORDEN_SUFIJO` en `takab_edge.buffer`), y una pantalla apagada
            # no protege a nadie. Se sirve lo que haya y se declara lo que no se
            # sabe: sin índice fiable la ventana candidata es el fichero entero
            # (`desde=None`), el presupuesto la recorta por la cola y la
            # cobertura real la mide el lector sobre dato ya decodificado
            # (`truncated`). Apagar es una decisión del operador, no del anillo.
            sin_orden = _hay_desorden(ruta)
            if sin_orden:
                desordenado = True
                _avisar_del_desorden(ruta)
            rango = _rango_de_bytes(
                ruta,
                None if sin_orden else UTCDateTime(inicio),
                get_record_information,
            )
            if rango is None:
                continue
            desplazamiento, tope = rango
            cuanto = tope - desplazamiento
            if cuanto > presupuesto:
                # Se recorta POR EL PRINCIPIO: el operador quiere lo de ahora.
                # El corte se alinea al registro para no partir una cabecera.
                with open(ruta, "rb") as fh:
                    cabecera = get_record_information(fh, offset=0)
                reclen = int(cabecera.get("record_length") or _RECLEN_DE_RESPALDO)
                registros = max(1, presupuesto // reclen)
                desplazamiento = tope - registros * reclen
                cuanto = tope - desplazamiento
                recortado_por_presupuesto = True
            with open(ruta, "rb") as fh:
                fh.seek(desplazamiento)
                datos = fh.read(cuanto)
            leidos += len(datos)
            presupuesto -= len(datos)
            trozos.append((dia, datos))
            ficheros.append(ruta.name)

        if not trozos:
            return _degradado_heli(
                "canal_sin_ficheros",
                canal=canal,
                canal_pedido=canal_pedido,
                horas=horas,
                horas_pedidas=horas_pedidas,
                ventana=ventana,
                desordenado=desordenado,
            )

        flujo = Stream()
        for _dia, datos in sorted(trozos, key=lambda par: par[0]):
            flujo += read(BytesIO(datos))
        flujo = flujo.select(channel=canal)
        flujo.trim(UTCDateTime(inicio), UTCDateTime(fin))
        flujo.merge(method=1)
        # `split()` y NUNCA `fill_value`: rellenar el hueco con ceros escribiría
        # «el suelo estuvo quieto» donde no hubo medición. Misma decisión y misma
        # razón que en `RingBuffer.extract_window` (T-2.67.c).
        flujo = flujo.split()
        flujo.sort(keys=["starttime"])
    except Exception:  # noqa: BLE001 — pantalla no-crítica: se declara, no revienta
        log.warning("panel LAN: anillo ilegible para el helicorder (%s)", canal, exc_info=True)
        return _degradado_heli(
            "anillo_ilegible",
            canal=canal,
            canal_pedido=canal_pedido,
            horas=horas,
            horas_pedidas=horas_pedidas,
            ventana=ventana,
            desordenado=desordenado,
        )

    segmentos: list[dict] = []
    huecos: list[dict] = []
    sr: float | None = None
    fin_anterior: datetime | None = None
    for traza in flujo:
        if traza.stats.npts == 0:
            continue
        sr = float(traza.stats.sampling_rate)
        por_bucket = max(1, int(round(sr * BUCKET_S)))
        muestras = np.asarray(traza.data, dtype=np.int64)
        arranque = traza.stats.starttime.datetime.replace(tzinfo=UTC)
        if fin_anterior is not None and arranque > fin_anterior:
            huecos.append(
                {
                    "start": fin_anterior.isoformat(),
                    "end": arranque.isoformat(),
                    # reloj: datos — los dos extremos son cabeceras miniSEED, o
                    # sea el eje de muestras del propio sensor. El hueco mide
                    # dato que falta, no tiempo que pasó aquí.
                    "seconds": (arranque - fin_anterior).total_seconds(),
                }
            )
        pares = _minmax_por_segundo(muestras, por_bucket)
        segmentos.append(
            {
                "start": arranque.isoformat(),
                "buckets": len(pares) // 2,
                "dc_counts": float(muestras.mean()),
                "minmax": pares,
            }
        )
        fin_anterior = traza.stats.endtime.datetime.replace(tzinfo=UTC)

    # Hay fichero y se leyó, pero dentro de la ventana no cayó ni una muestra:
    # el sensor llevaba horas callado o el anillo sólo guarda dato más viejo. Es
    # un desenlace DISTINTO de «no hay ficheros» y de «un hueco en medio», y
    # servirlo como respuesta buena con la lista vacía dejaría a la tarjeta
    # diciendo «0 huecos» sobre una pantalla en blanco.
    if not segmentos:
        return _degradado_heli(
            "sin_dato_en_la_ventana",
            canal=canal,
            canal_pedido=canal_pedido,
            horas=horas,
            horas_pedidas=horas_pedidas,
            ventana=ventana,
            desordenado=desordenado,
        )

    # El hueco de COLA es un hecho distinto del recorte de cabeza: significa que
    # el sensor calló hace un rato, y el panel tiene que dejarlo en blanco a la
    # derecha en vez de estirar el último tramo hasta el borde.
    # reloj: ajeno — `fin` es el reloj del Pi y `fin_anterior` la cabecera del
    # último registro, que la selló el Shake: no hay monotónico compartido entre
    # las dos máquinas, así que pared es lo correcto aquí y no se puede mejorar.
    edad = (fin - fin_anterior).total_seconds()
    if edad > BUCKET_S:
        huecos.append(
            {
                "start": fin_anterior.isoformat(),
                "end": fin.isoformat(),
                # reloj: ajeno — ver el bloque de arriba
                "seconds": edad,
            }
        )

    # [T-7.23 · V1] LA COBERTURA SE COMPRUEBA SOBRE EL DATO YA DECODIFICADO.
    #
    # Esto salía antes de `cubierto_desde`: el `starttime` de la CABECERA a la
    # que saltó la búsqueda binaria. Es el peor sitio posible para medirlo,
    # porque es justo lo que deja de significar nada cuando el fichero está
    # desordenado —y el testigo del escritor sólo ve el desorden que ese
    # proceso presenció (ver `_DESORDEN_SUFIJO` en `takab_edge.buffer`)—: la
    # cabecera podía ser anterior a `inicio` mientras el dato servido empezaba
    # media hora después, y la ventana salía como completa.
    #
    # `segmentos[0]` ya está decodificado, ya está recortado a la ventana y ya
    # está ordenado por `starttime`, así que es la PRIMERA MUESTRA QUE SE
    # SIRVE. No cuesta nada más y no se puede confundir con otra cosa: si
    # empieza después de `inicio`, la cobertura no es la que se pidió y se
    # declara. `truncated` sigue sin ser «hay un hueco al principio»: es «lo
    # servido no llega tan atrás», y sus dos causas mandan al operador a sitios
    # distintos —a esperar a que el anillo se llene, o a pedir menos horas—,
    # así que se separan.
    desde_real = datetime.fromisoformat(segmentos[0]["start"])
    #
    # [T-7.23 · Q2·bis] `recortado` sale SÓLO de la cobertura. Aquí había una
    # rama de más —«si el presupuesto mordió, declara recortado aunque la
    # ventana esté cubierta»— que era cierta mientras el candidato ERA la
    # ventana, y dejó de serlo con el arreglo de arriba: sin índice fiable el
    # candidato es el FICHERO ENTERO, así que el presupuesto muerde el fichero
    # y no la ventana. MEDIDO: el fichero EHZ real del gabinete pesa 100.2 MB a
    # media tarde y el presupuesto son 48 MiB [PROTOTIPO · Pi 4 · 2026-09-20],
    # o sea que con el testigo puesto la rama se cumplía en CADA petición
    # durante más de media jornada, rotulando «RECORTADO · presupuesto» sobre
    # ventanas servidas enteras. Quitar un apagón para poner una afirmación
    # falsa en la misma tarjeta es el mismo pecado de la regla de oro 7 por el
    # otro lado. Que el presupuesto mordiera se sigue publicando donde
    # corresponde —`bytes_read`—: es un hecho sobre lo que costó leer, no sobre
    # lo que se sirvió.
    #
    # reloj: ajeno — `desde_real` sale de una cabecera miniSEED (reloj del Shake)
    # e `inicio` del reloj del Pi. Un salto de NTP aquí sólo desplaza el rótulo
    # de «recortado» un segundo arriba o abajo; no hay forma de medirlo mejor.
    recortado = (desde_real - inicio).total_seconds() > BUCKET_S
    razon_recorte = None
    if recortado:
        razon_recorte = "presupuesto" if recortado_por_presupuesto else "anillo"

    return {
        "degraded": False,
        "reason": None,
        "channel": canal,
        "requested_channel": canal_pedido,
        "hours": horas,
        "requested_hours": horas_pedidas,
        "window_start": inicio.isoformat(),
        "window_end": fin.isoformat(),
        "sample_rate": sr,
        "bucket_s": BUCKET_S,
        # [T-7.23 · V2] La EDAD de la última muestra servida, con los MISMOS
        # cuatro campos que el espectrograma. Es la misma resta que mide el
        # hueco de cola, publicada: sin ella el borde derecho del lienzo decía
        # «AHORA» con dato de cualquier edad, y ese bitmap se queda en pantalla
        # hasta que llegue otro (se re-pide cada 60 s, o nunca si el gabinete
        # deja de contestar).
        #
        # [T-7.23 · Q1] El UMBRAL, en cambio, es el suyo y no el del
        # espectrograma: `RANCIO_HELI_S` descuenta la cadencia de esta vista y
        # el registro que el anillo todavía no ha escrito. Con el del
        # espectrograma, la tarjeta gritaba unos 50 de cada 60 segundos con el
        # sensor sano.
        "last_sample_at": fin_anterior.isoformat(),
        "age_s": edad,
        "stale": bool(edad > RANCIO_HELI_S),
        "stale_after_s": RANCIO_HELI_S,
        "segments": segmentos,
        "gaps": huecos,
        "bytes_read": leidos,
        "files": ficheros,
        "truncated": recortado,
        "truncated_reason": razon_recorte,
        # [T-7.23 · Q2] «Esta ventana puede estar incompleta: el anillo perdió
        # la monotonía». Es una advertencia sobre la VENTANA y convive con el
        # dibujo; la cobertura que de verdad se sirvió la dice `truncated`.
        "ring_unordered": desordenado,
    }


__all__ = [
    "BUCKET_S",
    "ESCALA_DB_MAX",
    "ESCALA_DB_MIN",
    "GRANULARIDAD_ANILLO_S",
    "HORAS_MAX",
    "HORAS_MIN",
    "NPERSEG_DEFAULT",
    "NPERSEG_PERMITIDOS",
    "PRESUPUESTO_BYTES",
    "RANCIO_HELI_S",
    "RANCIO_S",
    "REFRESCO_HELI_S",
    "acotar_horas",
    "acotar_nperseg",
    "canales_del_anillo",
    "elegir_canal",
    "espectrograma",
    "helicorder",
]
