"""Grabador de anillo, clip del evento y goteo de capturas (T-3.11).

LO QUE SE GUARDA, Y LO QUE SE TIRA
──────────────────────────────────
El requisito es literal: *«que grabe 1 min antes de la señal y 10 después, saca capturas,
y todo lo demás que grabe se puede ir borrando para no generar espacio»*. Eso son tres
cosas distintas y conviene no confundirlas:

* el **anillo** graba siempre y se autopoda — nunca sale del gabinete;
* el **clip** es la ventana del evento recortada del anillo — es lo único de vídeo que sube;
* el **goteo** son JPEG sueltos DESPUÉS del clip, hasta que se detecta el reingreso.

El goteo existe porque las dos ventanas no se parecen en nada: el clip dura once minutos
y **un dictamen tarda horas**. La foto del reingreso casi nunca cae dentro del clip, y la
alternativa —grabar vídeo hasta que alguien vuelva a entrar— sería vídeo continuo, que es
justo lo que la regla de oro 9 prohíbe.

ESTE MÓDULO NO DECIDE QUÉ FOTOGRAMA IMPORTA
───────────────────────────────────────────
El gabinete graba y gotea; **la nube elige** las cuatro capturas del reporte, ya con la
curva de aforo en la mano. Meter esa heurística aquí sería poner visión por computador en
la caja que no puede permitirse el CPU, para decidir algo que se decide mejor después.

LA CUOTA NO ES HIGIENE
──────────────────────
La microSD del gabinete es **de la que arranca el camino de vida**. Un clip que no
consigue subir —porque no hay internet, que es exactamente cuando hay un sismo— no puede
llenarla. Por eso hay dos topes independientes (bytes y número de clips) y por eso el que
muere es el **más viejo**: ante disco lleno, la evidencia reciente vale más que la rancia.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger("takab_edge.cctv")

#: Duración de cada segmento del anillo. Es el grano con el que se poda y con el que se
#: recorta: más corto afina el recorte y multiplica ficheros; más largo hace lo contrario.
#: 10 s da un recorte con error máximo de 10 s sobre una ventana de 660 s.
SEGMENTO_S = 10.0

#: `%Y%m%dT%H%M%S` en el nombre — el anillo se ordena por NOMBRE y no por mtime, que
#: cambia al copiar y miente después de un `rsync` o un restore.
_PATRON = re.compile(r"^seg-(\d{8}T\d{6})Z\.mp4$")
_FORMATO = "%Y%m%dT%H%M%S"


@dataclass(frozen=True)
class Segmento:
    """Un trozo del anillo, con su ventana temporal derivada del nombre."""

    ruta: Path
    inicio: datetime
    duracion_s: float = SEGMENTO_S

    @property
    def fin(self) -> datetime:
        return self.inicio + timedelta(seconds=self.duracion_s)

    def solapa(self, desde: datetime, hasta: datetime) -> bool:
        """¿Este segmento aporta algo a la ventana [desde, hasta]?

        Comparación semiabierta en los dos extremos: un segmento que **termina** justo
        cuando empieza la ventana no aporta un solo fotograma, y meterlo hincharía el clip
        con un preámbulo que nadie pidió.
        """
        return self.inicio < hasta and self.fin > desde


def nombre_de(inicio: datetime) -> str:
    """Nombre canónico de un segmento. UTC siempre: el gabinete puede cambiar de huso."""
    return f"seg-{inicio.astimezone(UTC).strftime(_FORMATO)}Z.mp4"


def leer_anillo(directorio: Path, *, duracion_s: float = SEGMENTO_S) -> list[Segmento]:
    """Segmentos presentes, ordenados por tiempo. Ignora en silencio lo que no reconoce.

    Lo desconocido se ignora **a propósito**: en ese directorio también aterrizan el
    fichero a medio escribir de ffmpeg y los clips ya recortados. Confundir cualquiera de
    los dos con un segmento del anillo haría que la poda borrase evidencia.
    """
    encontrados: list[Segmento] = []
    for ruta in directorio.glob("seg-*.mp4"):
        m = _PATRON.match(ruta.name)
        if m is None:
            continue
        try:
            inicio = datetime.strptime(m.group(1), _FORMATO).replace(tzinfo=UTC)
        except ValueError:
            # El patrón acepta `20261399T999999`: ocho dígitos y seis lo son. Sin este
            # `except`, UN nombre imposible tumba la lectura del anillo ENTERO y el
            # gabinete se queda sin clip en el siguiente evento. Se salta el fichero, no
            # el directorio — misma disciplina que la cuarentena del spool de la nube.
            log.warning("cctv: nombre de segmento ilegible, se ignora: %s", ruta.name)
            continue
        encontrados.append(Segmento(ruta=ruta, inicio=inicio, duracion_s=duracion_s))
    return sorted(encontrados, key=lambda s: s.inicio)


def segmentos_de_la_ventana(
    segmentos: list[Segmento], desde: datetime, hasta: datetime
) -> list[Segmento]:
    """Los segmentos que hay que concatenar para cubrir [desde, hasta]."""
    return [s for s in segmentos if s.solapa(desde, hasta)]


def cobertura(segmentos: list[Segmento], desde: datetime, hasta: datetime) -> float:
    """Fracción [0..1] de la ventana pedida que el anillo puede cubrir de verdad.

    Existe para que el clip **declare lo que le falta** en vez de aparentar estar completo.
    Un clip que empieza 12 s tarde porque el gabinete arrancó hace un minuto sigue siendo
    evidencia útil; uno que dice cubrir `T−60 s` sin cubrirlo es una mentira en un reporte.
    """
    total = (hasta - desde).total_seconds()
    if total <= 0:
        return 0.0
    cubierto = 0.0
    for s in segmentos_de_la_ventana(segmentos, desde, hasta):
        ini = max(s.inicio, desde)
        fin = min(s.fin, hasta)
        cubierto += max(0.0, (fin - ini).total_seconds())
    return min(1.0, cubierto / total)


def podar_anillo(
    segmentos: list[Segmento], *, ahora: datetime, ring_s: float, cuota_bytes: int
) -> list[Segmento]:
    """Qué segmentos del anillo hay que **borrar**. No borra: decide.

    Dos criterios, y el de cuota se aplica DESPUÉS del de edad porque son distintos: la
    edad es la política («guardo tres minutos»), la cuota es el suelo de seguridad («pase
    lo que pase, no lleno la tarjeta»). Si se aplicaran al revés, un pico de bitrate
    borraría por cuota segmentos que la política aún quería.
    """
    corte = ahora - timedelta(seconds=ring_s)
    viejos = [s for s in segmentos if s.fin <= corte]
    vivos = [s for s in segmentos if s.fin > corte]

    total = sum(_tam(s.ruta) for s in vivos)
    por_cuota: list[Segmento] = []
    for s in sorted(vivos, key=lambda x: x.inicio):  # el más viejo muere primero
        if total <= cuota_bytes:
            break
        total -= _tam(s.ruta)
        por_cuota.append(s)
    if por_cuota:
        log.warning(
            "cctv: la cuota de disco (%d MB) obliga a soltar %d segmento(s) del anillo",
            cuota_bytes // (1024 * 1024),
            len(por_cuota),
        )
    return viejos + por_cuota


def clips_a_soltar(pendientes: list[Path], *, maximo: int) -> list[Path]:
    """Clips pendientes de subir que sobran, del más viejo al más nuevo.

    Sin este tope, un gabinete sin internet acumula un clip por evento hasta llenar la
    tarjeta de la que arranca el camino de vida. Y sin internet es **exactamente** cuando
    hay sismos, así que el caso no es hipotético: es el caso.
    """
    if len(pendientes) <= maximo:
        return []
    por_nombre = sorted(pendientes, key=lambda p: p.name)
    sobran = por_nombre[: len(por_nombre) - maximo]
    log.warning(
        "cctv: %d clip(s) pendientes supera el tope de %d; se sueltan los más viejos: %s",
        len(pendientes),
        maximo,
        ", ".join(p.name for p in sobran),
    )
    return sobran


def _tam(ruta: Path) -> int:
    try:
        return ruta.stat().st_size
    except OSError:
        return 0


# ------------------------------------------------------------------ comandos
#
# Se construyen como listas y se devuelven, en vez de ejecutarse aquí: así el test
# comprueba EXACTAMENTE lo que se le va a pedir a ffmpeg sin necesitar un ffmpeg. Las
# banderas de este archivo son la diferencia entre costar un 3 % de un núcleo y costar
# el gabinete entero, así que merecen quedar fijadas por un test.


def cmd_anillo(
    ffmpeg: str, rtsp_url: str, directorio: Path, *, segmento_s: float = SEGMENTO_S
) -> list[str]:
    """ffmpeg que mantiene el anillo. **`-c copy`: no decodifica un solo fotograma.**"""
    return [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "warning",
        # TCP y no UDP: sobre WiFi de edificio el UDP pierde paquetes y el clip sale
        # con bloques corruptos justo en el minuto que importa.
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        f"{segmento_s:g}",
        # Cortar en keyframe: sin esto un segmento puede empezar sin fotograma de
        # referencia y el recorte del clip arranca en gris.
        "-segment_format",
        "mp4",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        str(directorio / "seg-%Y%m%dT%H%M%SZ.mp4"),
    ]


def cmd_clip(
    ffmpeg: str, lista_concat: Path, salida: Path, *, recorte_s: float, duracion_s: float
) -> list[str]:
    """ffmpeg que recorta el clip del anillo. También `-c copy`: coser, no recomprimir."""
    return [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "warning",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lista_concat),
        "-ss",
        f"{recorte_s:g}",
        "-t",
        f"{duracion_s:g}",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(salida),
    ]


def cmd_captura(ffmpeg: str, fuente: str, salida: Path) -> list[str]:
    """Un JPEG suelto. Es lo único de este módulo que decodifica, y decodifica UN frame."""
    return [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        fuente,
        "-frames:v",
        "1",
        "-q:v",
        "4",
        "-y",
        str(salida),
    ]


def escribir_lista_concat(segmentos: list[Segmento], destino: Path) -> Path:
    """Fichero de lista del demuxer `concat`. Rutas citadas: un path con espacios lo rompe."""
    lineas = [f"file '{s.ruta.as_posix()}'" for s in segmentos]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino
