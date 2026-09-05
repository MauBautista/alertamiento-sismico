"""Espectrograma del dictamen técnico (T-5.23): tiempo × frecuencia.

QUÉ AÑADE, Y PARA QUIÉN
------------------------
Lo que había era **un solo espectro de amplitud de la ventana entera**. Para un
cliente no técnico eso ya es demasiado: es una figura que exige formación y
compite con el croquis y el semáforo, que son lo que decide si se ocupa el
edificio. **Para el pericial, en cambio, el espectro global no basta**: separar
la llegada de la onda P de la S, y ver si el edificio respondió en su periodo
fundamental, es exactamente lo que un promedio sobre toda la ventana esconde.

Por eso esta figura va **solo en la variante técnica**, junto a la onda cruda, y
no en el resumen ejecutivo.

LO QUE ESTA FIGURA NO PROMETE
------------------------------
**La escala es RELATIVA y lo dice.** El waveform del RS4D llega en cuentas del
ADC y la calibración instrumental es un paso pendiente (`blueprint §4.4`), así
que aquí no hay dB referenciados a nada físico: hay energía normalizada al máximo
de la propia ventana. Pintar una escala absoluta sería prometer una calibración
que no existe — la misma guarda que ya vigila el mapa de sacudida.

Y **cada eje trae su unidad y la ventana va declarada**: un espectrograma sin
decir su ventana no se puede reproducir ni comparar con otro.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Muestras por ventana de análisis. A 100 sps son 1.28 s, que resuelve ~0.8 Hz —
#: suficiente para separar el contenido de baja frecuencia de un edificio del de
#: la llegada de la onda, y corto para que la llegada no se difumine.
VENTANA_MUESTRAS = 128
#: Solape entre ventanas. La mitad es el compromiso habitual: sin solape, un
#: transitorio que caiga en el borde se reparte entre dos columnas y se diluye.
SOLAPE = 0.5
#: Cuántas columnas caben en 180 mm de papel sin que se conviertan en ruido.
MAX_COLUMNAS = 120
#: …y cuántas filas. Por encima, dos filas comparten pixel y la figura miente.
MAX_FILAS = 48


@dataclass(frozen=True)
class Espectrograma:
    """Matriz tiempo × frecuencia, normalizada al máximo de la propia ventana.

    `celdas[t][f]` ∈ [0, 1]. Es energía **relativa**: no hay unidad física
    detrás, y por eso la figura no pinta una escala absoluta.
    """

    celdas: list[list[float]]
    #: Instante central de cada columna, en segundos desde el inicio de la traza.
    tiempos_s: list[float]
    #: Frecuencia de cada fila, en Hz.
    frecuencias_hz: list[float]
    #: Ventana y solape usados, para que la figura sea reproducible.
    ventana_muestras: int
    solape: float
    canal: str

    @property
    def duracion_s(self) -> float:
        return self.tiempos_s[-1] if self.tiempos_s else 0.0


def calcular(
    samples: list[int] | list[float],
    rate: float,
    canal: str,
    *,
    max_muestras: int | None = None,
) -> Espectrograma | None:
    """Espectrograma de una traza, o `None` si no hay traza suficiente.

    `None` **no es un cero**: es que no había de qué transformar, y quien lo
    llama tiene que decirlo con el mismo texto de ausencia que la onda cruda.
    """
    import numpy as np  # noqa: PLC0415 - import perezoso: solo el técnico lo necesita

    datos = np.asarray(samples[: max_muestras or len(samples)], dtype=np.float64)
    if rate <= 0 or datos.size < VENTANA_MUESTRAS * 2:
        return None

    # La media se quita ANTES, igual que en el espectro global: el crudo del RS4D
    # trae una continua enorme (millones de cuentas) que sin restarla domina cada
    # ventana y aplana la figura entera. Es el hallazgo de `T-2.25`, por ventana.
    datos = datos - datos.mean()

    paso = max(1, int(VENTANA_MUESTRAS * (1.0 - SOLAPE)))
    inicios = list(range(0, datos.size - VENTANA_MUESTRAS + 1, paso))
    if not inicios:
        return None
    # Se diezma en TIEMPO tomando columnas equiespaciadas, no truncando: truncar
    # dejaría fuera el final del registro, que es donde vive la coda.
    if len(inicios) > MAX_COLUMNAS:
        salto = len(inicios) / MAX_COLUMNAS
        inicios = [inicios[int(i * salto)] for i in range(MAX_COLUMNAS)]

    ventana = np.hanning(VENTANA_MUESTRAS)
    columnas = [np.abs(np.fft.rfft(datos[i : i + VENTANA_MUESTRAS] * ventana)) for i in inicios]
    freqs = np.fft.rfftfreq(VENTANA_MUESTRAS, d=1.0 / rate)

    matriz = np.asarray(columnas)  # (tiempo, frecuencia)
    # Se descarta la fila DC: no es una frecuencia, y tras restar la media es ruido.
    matriz, freqs = matriz[:, 1:], freqs[1:]
    if matriz.size == 0:
        return None

    if freqs.size > MAX_FILAS:
        salto = freqs.size / MAX_FILAS
        idx = [int(i * salto) for i in range(MAX_FILAS)]
        matriz, freqs = matriz[:, idx], freqs[idx]

    pico = float(matriz.max())
    # Normalización al máximo de la PROPIA ventana. Con la matriz plana a cero
    # —una traza muerta— se devuelven ceros en vez de dividir por cero: una
    # figura toda encendida sobre ruido sería la mentira más cara de las dos.
    celdas = (matriz / pico) if pico > 0 else np.zeros_like(matriz)

    return Espectrograma(
        celdas=[[round(float(v), 4) for v in fila] for fila in celdas],
        tiempos_s=[round((i + VENTANA_MUESTRAS / 2) / rate, 3) for i in inicios],
        frecuencias_hz=[round(float(f), 3) for f in freqs],
        ventana_muestras=VENTANA_MUESTRAS,
        solape=SOLAPE,
        canal=canal,
    )


def leyenda(esp: Espectrograma) -> str:
    """El pie de la figura. Función aparte y no una f-string en el trazado.

    El flujo de contenido de un PDF va comprimido, así que un test que quisiera
    comprobar el rótulo tendría que descomprimirlo — y acabaría probando `fpdf2`
    en vez del enunciado. Aquí el enunciado se puede leer.

    **Lo que este texto tiene que decir siempre**: que la escala es RELATIVA. El
    crudo está en cuentas del ADC y la calibración instrumental sigue pendiente
    (`blueprint §4.4`); una leyenda con unidades prometería una calibración que
    nadie hizo.
    """
    return (
        f"0 – {esp.duracion_s:.1f} s · ventana {esp.ventana_muestras} muestras, "
        f"solape {esp.solape * 100:.0f} % · color = energía RELATIVA al máximo de "
        "esta ventana (el crudo está en cuentas del ADC: no hay escala absoluta)"
    )
