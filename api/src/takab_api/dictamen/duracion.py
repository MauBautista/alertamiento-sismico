"""Duración instrumental de la sacudida (T-3.14).

**Medida, no estimada.** Sale de la forma de onda archivada del propio evento, no de una
correlación con la magnitud ni de una tabla — que es lo que la ficha exige y lo que separa
un dato de un adorno.

POR QUÉ D5-95 Y NO LA DURACIÓN «BRACKETED»
──────────────────────────────────────────
Hay dos familias de definición y la elección **no fue de gusto**:

* La **bracketed** —tiempo entre el primer y el último cruce de un umbral, típicamente
  0.05 g— es intuitiva y es la que la gente espera. Y **no se puede calcular aquí**: exige
  unidades absolutas, y lo que archivamos son **cuentas del ADC sin calibrar**. Convertirlas
  a `g` necesita la respuesta instrumental, que este servicio no tiene (lo dice el propio
  lector: *«Convertirlas a g exige la respuesta instrumental»*). Calcularla sin eso sería
  inventarse el umbral.

* La **significativa D5-95** (Trifunac & Brady, 1975) es el intervalo en el que se acumula
  del 5 % al 95 % de la **Intensidad de Arias** —proporcional a ``∫a²dt``—. Y aquí está la
  propiedad que decide: **es una FRACCIÓN, y una fracción es invariante de escala**. El
  factor que convierte cuentas a g se cancela al dividir. O sea que D5-95 se mide **exacta**
  sobre cuentas crudas, sin calibrar nada.

No es que D5-95 sea el premio de consolación: es la definición estándar en ingeniería
sísmica para «cuánto duró la parte que importa», y además la única honesta con los datos que
tenemos. Se declara D5-95 en el reporte, con esas palabras, para que nadie la confunda con
la bracketed y compare peras con manzanas.

QUITAR LA MEDIA NO ES HIGIENE: ES LA DIFERENCIA ENTRE MEDIR Y NO MEDIR
──────────────────────────────────────────────────────────────────────
El waveform crudo del RS4D trae un **offset de continua enorme** —del orden de 3.8 millones
de cuentas, medido en el gabinete el 2026-08-01—. Con ese offset dentro, ``∫a²dt`` está
dominado por una constante: la energía se acumula de forma casi lineal con el tiempo y
D5-95 devuelve **el 90 % de la ventana**, sea cual sea el sismo. El número saldría, parecería
razonable, y describiría la longitud del registro en vez de la sacudida.

Es el mismo motivo por el que `_spectrum` le quita la media antes de transformar, y está
fijado por un test que compara una traza con offset contra la misma sin él.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Fracciones de la Intensidad de Arias que acotan el intervalo. 5–95 % es la convención
#: dominante; 5–75 % existe y da números sistemáticamente menores, así que **cuál se usó
#: viaja con el número** — comparar un D5-95 con un D5-75 es comparar cosas distintas.
INICIO = 0.05
FIN = 0.95

#: Por debajo de esto no hay señal de la que hablar. Una traza plana —el sensor desconectado,
#: o un evento que no llegó a este canal— tiene energía cero y su D5-95 no es «0 s»: es
#: **nada**, y decirlo es lo correcto. Un cero se leería como «no tembló».
_ENERGIA_MINIMA = 1e-9


@dataclass(frozen=True, slots=True)
class Duracion:
    """El intervalo significativo, y de dónde salió."""

    #: Segundos entre el 5 % y el 95 % de la Intensidad de Arias acumulada.
    segundos: float
    #: Instante de inicio, en segundos desde el comienzo de la traza.
    desde_s: float
    #: Instante de fin, ídem.
    hasta_s: float
    #: Canal sobre el que se midió. Va en el dato porque el número depende de él.
    canal: str
    #: Muestras que entraron en la cuenta. Permite auditar que la traza era suficiente.
    muestras: int

    @property
    def etiqueta(self) -> str:
        """Cómo se nombra en el reporte. **Nunca «duración» a secas.**"""
        return f"D5-95 · {self.segundos:.1f} s"


def significativa(samples: list[int], *, sample_rate: float, canal: str) -> Duracion | None:
    """D5-95 de una traza en cuentas. `None` si no hay señal de la que hablar.

    Devolver `None` en vez de `0.0` es deliberado y es la mitad del valor de esta función:
    un cero en un dictamen se lee como «no tembló», y lo que ocurrió fue que **no se pudo
    medir**. Quien llama lo convierte en un literal de ausencia, no en una cifra.
    """
    n = len(samples)
    if n < 2 or sample_rate <= 0:
        return None

    # 1. Fuera la continua. Sin esto, lo que sigue mide la longitud del registro.
    media = sum(samples) / n
    centrada = [s - media for s in samples]

    # 2. Intensidad de Arias acumulada, salvo constantes: ∫a²dt. Las constantes (π/2g y el
    #    factor de calibración) se cancelan al normalizar, que es lo que permite medir esto
    #    sobre cuentas sin calibrar.
    total = 0.0
    acumulada = [0.0] * n
    for i, v in enumerate(centrada):
        total += v * v
        acumulada[i] = total

    if total <= _ENERGIA_MINIMA:
        return None

    # 3. Los dos cruces. Se busca el PRIMER índice que alcanza cada fracción: con `>=` y no
    #    con `>` para que una traza de una sola muestra dominante no caiga fuera.
    objetivo_ini = total * INICIO
    objetivo_fin = total * FIN
    i_ini = next(i for i, a in enumerate(acumulada) if a >= objetivo_ini)
    i_fin = next(i for i, a in enumerate(acumulada) if a >= objetivo_fin)

    desde = i_ini / sample_rate
    hasta = i_fin / sample_rate
    return Duracion(
        segundos=hasta - desde,
        desde_s=desde,
        hasta_s=hasta,
        canal=canal,
        muestras=n,
    )
