"""Qué reloj usar para qué, en una máquina cuyo reloj SALTA.

**Por qué existe, medido y no supuesto** (`T-7.60`): el 2026-09-19 el panel del
gabinete real decía `uptime_s: 77851` (21.6 h) mientras el kernel decía 30 323 s
(8.4 h). El Raspberry Pi 4 **no tiene RTC** —`timedatectl` responde
`RTC time: n/a`—, así que al arrancar restaura la última hora guardada y sigue
con ella hasta que NTP contesta:

    2026-09-18T18:14:05  kernel: Booting Linux              ← hora restaurada, falsa
    2026-09-19T07:39:30  systemd-timesyncd: Initial clock synchronization

Trece horas y veinticinco minutos de salto, hacia adelante, en un instante. Toda
duración calculada restando dos marcas del reloj de pared se llevó el salto
entero dentro. El censo encontró **17 sitios** así, y el uptime era el menos
grave: el peor contaba el silencio que declara TERMINADO un episodio sísmico.

## La regla, y es lo único que hay que saber para tocar esto

**¿La duración mide tiempo transcurrido en ESTA máquina?** Entonces va con
`mono()`. Un cronómetro, un backoff, un cooldown, un uptime, la edad de algo que
sellamos nosotros hace un rato. El reloj monotónico no retrocede y no salta: es
un contador desde un origen arbitrario, y sólo sirve para restarlo consigo
mismo, que es exactamente lo que hace falta.

**¿La duración compara con una fecha AJENA?** Entonces va con el reloj de
pared, y cambiarla lo ROMPERÍA. La marca de tiempo de un paquete del sismógrafo,
el `ts_device` de la app, el sello de un catálogo, la validez de un certificado:
la otra mitad de la resta viene de fuera de esta máquina y no hay monotónico
compartido con ella.

## ⚠️ Y el tercer caso, que es el que no tiene respuesta bonita

La edad de algo **heredado del disco** —una evidencia pendiente que quedó de
antes del reinicio, un registro en el spool— no se puede medir con monotónico:
el origen del contador de la vida anterior murió con el proceso. Y con pared se
mide mal si el reloj saltó.

Aquí no se inventa un número: se DECLARA. `EdadIncierta` distingue «hace 40 s,
medido» de «no lo sé, y esto es lo que el reloj de pared sugiere». Quien lo
enseñe o lo vigile decide qué hacer con la duda; lo que no puede es no saber que
la hay. Es la misma doctrina del resto del sistema —un fallback no puede ser
`ok`— aplicada al tiempo.

## Cómo se marca en el código

Toda resta de instantes de `takab_edge/` lleva un marcador en su línea o en la
inmediatamente anterior, y `tests/test_reloj.py` lo exige:

    # reloj: monotonico  — duración de esta máquina
    # reloj: ajeno       — la otra mitad viene de fuera
    # reloj: datos       — los dos extremos van en el eje de muestras
    # reloj: heredado    — cruza un reinicio; se declara la incertidumbre

La clasificación **no es decidible leyendo el código** (`now - x` no dice de
dónde salió `x`), así que no se adivina: se exige declararla. Un sitio nuevo sin
marcador rompe CI, que es lo que convierte esto en una propiedad del árbol y no
en una lista que alguien mantiene a mano — la quinta vez que este repositorio
aprende lo mismo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


def mono() -> float:
    """Segundos desde un origen arbitrario que NO salta ni retrocede.

    Es la que hay que usar para cualquier duración medida en esta máquina. El
    valor absoluto no significa nada: sólo sirve restado consigo mismo.
    """
    return time.monotonic()


@dataclass(frozen=True)
class EdadIncierta:
    """Una edad que cruza un reinicio, con su duda declarada al lado.

    `segundos` es lo que dice el reloj de pared. `fiable` es `False` cuando ese
    número pudo nacer de un salto de reloj y no del paso del tiempo — porque la
    marca se selló antes de este arranque, o porque el reloj aún no ha
    sincronizado.

    No se redondea a cero ni se oculta: una evidencia que lleva horas esperando
    sigue siendo un problema aunque no sepamos cuántas. Lo que cambia es que
    quien la vigile puede distinguir «vieja» de «no lo sé».
    """

    segundos: float
    fiable: bool

    def __float__(self) -> float:
        return self.segundos


class Cronometro:
    """Mide cuánto ha pasado desde que se armó. Inmune a los saltos de reloj.

    Existe para que las pruebas puedan inyectar el tiempo sin parchear módulos:
    el gabinete tiene ya demasiados `monkeypatch` sobre relojes globales, y cada
    uno es un sitio donde una prueba mide otra cosa que el código.
    """

    def __init__(self, fuente=mono) -> None:  # noqa: ANN001 - callable() -> float
        self._fuente = fuente
        self._origen = fuente()

    def transcurrido(self) -> float:
        """Segundos desde que se armó. Nunca negativo, nunca un salto."""
        return max(0.0, self._fuente() - self._origen)

    def rearmar(self) -> None:
        self._origen = self._fuente()
