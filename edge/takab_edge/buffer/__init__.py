"""buffer — ring buffer miniSEED en disco (NVMe) + extracción de ventana de evento.

T-1.7: persiste el waveform crudo como **miniSEED** en archivos por día y canal, con
**retención circular** (poda por antigüedad 7–14 d y por tamaño), y **extrae la
ventana miniSEED** de un evento confirmado para subir a S3 (T-1.11/T-1.25). El
waveform crudo NO se sube en continuo (regla de oro 9): sólo la ventana de eventos.

La lógica de ring/retención/extracción se valida en cualquier filesystem (tests con
tmp); el tamaño real en GB se mide con hardware (gate #3).
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path

from takab_edge.config import BufferConfig
from takab_edge.contracts import WaveformPacket
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.buffer")

#: Cada cuántos append se ejecuta la poda (evita podar en cada paquete).
_PRUNE_EVERY = 1000

#: [T-7.23 · M2] Sufijo del testigo de DESORDEN de un fichero de día.
#:
#: Quien lee el anillo por desplazamiento de bytes —el helicorder del panel—
#: hace búsqueda binaria sobre las cabeceras miniSEED, y eso EXIGE que el
#: fichero esté escrito en orden cronológico. Este `append` escribe lo que
#: llegue: la deduplicación de SeedLink es un `deque` acotado, así que tras una
#: reconexión larga el Shake puede re-entregar un bloque que el deque ya olvidó
#: y aquí se appendea al final, más viejo que su vecino. A partir de ahí la
#: búsqueda binaria puede devolver cualquier cosa y **perder dato en silencio**.
#:
#: **Este testigo AVISA; no es la garantía.** [T-7.23 · V1] Sólo ve el desorden
#: que ESTE proceso presenció, y el caso que más importa es justo el otro: al
#: arrancar, `_ultimo_escrito` siembra el listón con el ÚLTIMO REGISTRO del
#: fichero, que en un fichero ya desordenado es el re-entregado —el más viejo—,
#: así que todo lo que venga detrás parece «más nuevo» y no se marca nada. Antes
#: de T-7.23 eso perdía dato en silencio; con el testigo solo, además se
#: afirmaba que el anillo estaba ordenado. La GARANTÍA vive en el lector y es
#: una comprobación de COBERTURA sobre dato ya decodificado
#: (`sismografo.helicorder`: si la primera muestra servida es posterior al
#: inicio de la ventana, se declara `truncated`). Esto se queda porque es barato
#: —una comparación por paquete— y avisa antes, con su propia razón.
#:
#: **[T-7.23 · Q2] Y lo que hace el lector con el testigo ya NO es apagarse.**
#: Degradaba la respuesta entera, y como el testigo se borra con su fichero y no
#: al rodar el día, eso dejaba la pantalla del sismógrafo en blanco unas 30 h
#: por un paquete duplicado. Ahora el testigo cambia CÓMO se lee —se sirve la
#: cola acotada por el presupuesto, sin fiarse del índice— y la respuesta viaja
#: marcada con `ring_unordered`. Servir lo que haya y declarar lo que no se
#: sabe.
#:
#: Detectarlo AQUÍ barriendo el fichero costaría 25.2 µs por cabecera [MEDIDO ·
#: equipo de desarrollo x86-64 · 2026-09-20], que sobre las ~24 500 de un
#: fichero EHZ de 100 MB son 0.62 s aquí y del orden de 2.5 s en el Pi 4 — más
#: caro que la lectura entera que se quiere hacer.
#:
#: No se toca el fichero de dato: el testigo es un fichero hermano, así que ni
#: `extract_window` ni la poda ni el glob de canales lo ven como miniSEED.
_DESORDEN_SUFIJO = ".desorden"


def to_miniseed_bytes(packet: WaveformPacket) -> bytes:
    """Codifica un `WaveformPacket` a un registro miniSEED (int32 = counts del RS4D)."""
    import numpy as np
    from obspy import Stream, Trace, UTCDateTime

    trace = Trace(np.asarray(packet.samples, dtype=np.int32))
    trace.stats.network = packet.network
    trace.stats.station = packet.station
    trace.stats.location = packet.location
    trace.stats.channel = packet.channel
    trace.stats.sampling_rate = packet.sample_rate
    trace.stats.starttime = UTCDateTime(packet.starttime)
    buf = BytesIO()
    Stream([trace]).write(buf, format="MSEED")
    return buf.getvalue()


class RingBuffer(EdgeModule):
    """Ring buffer miniSEED en disco: archivos `<net>.<sta>.<loc>.<cha>.<YYYYMMDD>.mseed`."""

    name = "buffer"
    depends_on = ("seedlink",)

    def __init__(self, config: BufferConfig | None = None) -> None:
        super().__init__()
        self.config = config or BufferConfig()
        self.root = (
            Path(self.config.root)
            if self.config.root
            else Path(tempfile.mkdtemp(prefix="takab-buffer-"))
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._appended = 0
        self._newest: date | None = None  # fecha del dato más reciente (poda relativa al dato)
        self._since_prune = 0
        # [T-7.23 · M2] Último `starttime` escrito en cada fichero de día. Se
        # siembra del propio fichero la primera vez que este proceso lo toca:
        # sin eso, el primer paquete tras un reinicio no tendría contra qué
        # compararse y el desorden más probable —el que llega justo al
        # reconectar— sería el único que no se vería.
        self._last_start: dict[Path, datetime] = {}
        # [T-7.23 · N2] Ficheros a los que este proceso YA les puso el testigo.
        # El hecho que importa —«este fichero perdió la monotonía»— ocurre UNA
        # vez; lo que llega por ráfagas son sus síntomas. Esto corre en el hilo
        # de ingesta de SeedLink y justo durante una reconexión, que es cuando
        # el Shake re-entrega bloques a puñados: un `log.warning` y una
        # reescritura del testigo POR PAQUETE convertían una transición en un
        # intervalo (regla de oro 10) y se comían la cota de log de T-7.47.
        self._desordenados: set[Path] = set()

    # --- Escritura ---
    def append(self, packet: WaveformPacket) -> None:
        if not packet.samples:
            return
        destino = self._dayfile(packet)
        self._vigilar_el_orden(destino, packet.starttime)
        with open(destino, "ab") as fh:
            fh.write(to_miniseed_bytes(packet))
        self._appended += 1
        pdate = packet.starttime.date()
        if self._newest is None or pdate > self._newest:
            self._newest = pdate
        self._since_prune += 1
        if self._since_prune >= _PRUNE_EVERY:
            self._since_prune = 0
            self.prune()

    def _vigilar_el_orden(self, destino: Path, arranque: datetime) -> None:
        """Marca el fichero si este paquete llega ANTES que el anterior.

        El testigo no se borra al rodar el día: se borra con su fichero (en
        `prune`). Un anillo que perdió la monotonía la perdió hasta que ese
        fichero desaparezca — la búsqueda binaria del lector no vuelve a ser
        fiable sólo porque el siguiente paquete llegue en orden.
        """
        anterior = self._last_start.get(destino)
        if anterior is None:
            anterior = self._ultimo_escrito(destino)
        if anterior is not None and arranque < anterior:
            self._marcar_desorden(destino, arranque, anterior)
        # El puntero se queda en el MÁS NUEVO visto: si no, un bloque
        # re-entregado dejaría el listón bajo y los paquetes buenos que vienen
        # detrás se contarían como desorden ellos también.
        if anterior is None or arranque > anterior:
            self._last_start[destino] = arranque
        else:
            self._last_start[destino] = anterior

    @staticmethod
    def _ultimo_escrito(destino: Path) -> datetime | None:
        """`starttime` del ÚLTIMO registro ya escrito, o None si no hay fichero.

        UNA lectura de cabecera (25.2 µs medidos) por fichero y por proceso.
        """
        try:
            tamano = destino.stat().st_size
        except OSError:
            return None
        if tamano == 0:
            return None
        from obspy.io.mseed.util import get_record_information

        try:
            with open(destino, "rb") as fh:
                reclen = int(get_record_information(fh, offset=0).get("record_length") or 4096)
                ultimo = (tamano // reclen - 1) * reclen
                if ultimo < 0:
                    return None
                info = get_record_information(fh, offset=ultimo)
            return info["starttime"].datetime.replace(tzinfo=UTC)
        except Exception:  # noqa: BLE001 — un anillo ilegible ya lo declara el lector
            log.warning("no se pudo leer la última cabecera de %s", destino, exc_info=True)
            return None

    def _marcar_desorden(self, destino: Path, arranque: datetime, anterior: datetime) -> None:
        """Escribe el testigo y avisa UNA vez por fichero, no una vez por paquete.

        Lo que el testigo dice —«este fichero ya no está en orden»— no cambia
        porque lleguen diez bloques re-entregados en vez de uno: el lector lo
        lee en O(1) por existencia y cambia igual su forma de leer [T-7.23 ·
        Q2]. Contarlos obligaba a releer, reescribir y volver a registrar
        dentro del hilo de ingesta de SeedLink, en la peor ráfaga posible.
        """
        if destino in self._desordenados:
            return
        self._desordenados.add(destino)
        marca = destino.with_name(destino.name + _DESORDEN_SUFIJO)
        if marca.exists():
            # El testigo sobrevivió a un reinicio: el hecho ya está registrado
            # y ya se avisó en su día. Anotarlo otra vez sería contar el mismo
            # suceso una vez por arranque del edge.
            return
        try:
            marca.write_text(
                json.dumps(
                    {
                        "desde": arranque.isoformat(),
                        "ultimo_en_orden": anterior.isoformat(),
                    }
                ),
                "utf-8",
            )
        except OSError:
            log.warning("no se pudo escribir el testigo de desorden %s", marca, exc_info=True)
        log.warning(
            "anillo: %s perdió el orden cronológico (%s < %s); el helicorder del panel "
            "no puede localizar por búsqueda binaria en este fichero",
            destino.name,
            arranque.isoformat(),
            anterior.isoformat(),
        )

    @staticmethod
    def hay_desorden(dayfile: Path) -> bool:
        """¿Este fichero de día perdió el orden cronológico? Lectura O(1)."""
        return dayfile.with_name(dayfile.name + _DESORDEN_SUFIJO).exists()

    def _dayfile(self, packet: WaveformPacket) -> Path:
        stamp = packet.starttime.date().strftime("%Y%m%d")
        name = f"{packet.network}.{packet.station}.{packet.location}.{packet.channel}.{stamp}.mseed"
        return self.root / name

    # --- Poda circular ---
    def prune(self) -> None:
        """Elimina archivos más viejos que la retención y, si sobra tamaño, los más antiguos."""
        if self._newest is not None:
            cutoff = self._newest - timedelta(days=self.config.retention_days)
            for path, fdate, _size in self._files():
                if fdate < cutoff:
                    self._borrar(path)
        files = self._files()
        total = sum(size for _, _, size in files)
        for path, _fdate, size in files:  # más antiguos primero
            if total <= self.config.max_bytes:
                break
            self._borrar(path)
            total -= size

    def _borrar(self, path: Path) -> None:
        """Un fichero de día se va con su testigo de desorden y con su puntero.

        Dejar el testigo huérfano condenaría al helicorder del día SIGUIENTE si
        alguna vez se reciclara el nombre, y dejar el puntero en memoria haría
        que el primer paquete de un fichero recién nacido se comparase contra
        el último de uno que ya no existe.
        """
        path.unlink(missing_ok=True)
        path.with_name(path.name + _DESORDEN_SUFIJO).unlink(missing_ok=True)
        self._last_start.pop(path, None)
        # …y la marca en memoria: si el nombre se reciclara, el fichero nuevo
        # tiene derecho a que se le vuelva a poner su testigo.
        self._desordenados.discard(path)

    def _files(self) -> list[tuple[Path, date, int]]:
        out: list[tuple[Path, date, int]] = []
        for path in self.root.glob("*.mseed"):
            fdate = self._date_of(path)
            if fdate is not None:
                out.append((path, fdate, path.stat().st_size))
        out.sort(key=lambda item: item[1])  # por fecha ascendente
        return out

    @staticmethod
    def _date_of(path: Path) -> date | None:
        try:
            return datetime.strptime(path.stem.split(".")[-1], "%Y%m%d").date()
        except (ValueError, IndexError):
            return None

    def total_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.root.glob("*.mseed"))

    # --- Extracción de la ventana de evento ---
    def extract_window(self, start: datetime, end: datetime) -> bytes:
        """miniSEED de la ventana [start, end] de un evento confirmado (para S3)."""
        from obspy import Stream, UTCDateTime, read

        stream = Stream()
        day = start.date()
        while day <= end.date():
            for path in self.root.glob(f"*.{day.strftime('%Y%m%d')}.mseed"):
                try:
                    stream += read(str(path))
                except Exception:  # noqa: BLE001 — archivo dañado: sáltalo, no bloquees el evento
                    log.warning("miniSEED ilegible, omitido: %s", path.name)
            day += timedelta(days=1)
        if len(stream) == 0:
            return b""
        stream.trim(UTCDateTime(start), UTCDateTime(end))
        stream.merge(method=1)
        # [T-2.67.c] `merge` deja un array ENMASCARADO en cuanto la ventana tiene
        # un hueco, y `write(MSEED)` lo rechaza con `NotImplementedError`. Sin
        # esto, el pendiente ni sube ni se descarta: se reintenta cada dos minutos
        # PARA SIEMPRE. Medido en `gw-dev-0001`: 20 evidencias de sismos reales
        # atascadas, la más vieja de 9 días, y creciendo.
        #
        # `split()` y NO `fill_value=0`: rellenar con ceros escribe «el suelo
        # estuvo quieto» justo donde no hubo medición, dentro de un fichero que
        # es prueba forense. miniSEED admite tramos no contiguos del mismo canal,
        # así que el hueco puede seguir siendo un hueco y no cuesta una mentira.
        stream = stream.split()
        if len(stream) == 0:
            # Toda la ventana era hueco. Devolver b"" enruta al camino de «sin
            # datos en el ring» del llamador, que ya lo declara; escribir aquí
            # levantaría `ObsPyException: Can not write empty stream to file`.
            return b""
        buf = BytesIO()
        stream.write(buf, format="MSEED")
        return buf.getvalue()

    def __len__(self) -> int:
        """Número de paquetes escritos desde el arranque (métrica de ingesta)."""
        return self._appended

    def _on_start(self) -> None:
        log.info(
            "ring buffer en %s (retención %d d, tope %d MB)",
            self.root,
            self.config.retention_days,
            self.config.max_bytes // 1024**2,
        )
