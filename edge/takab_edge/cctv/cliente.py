"""El cliente CCTV del gabinete: anillo, clip del evento y goteo de capturas (T-3.11).

Es un proceso **aparte** de `takab-edge` y **cliente** suyo: sondea `GET /api/status` y no
recibe llamadas de nadie. Esa dirección es la que sostiene el invariante `B.1` —si esto
muere, se cuelga o satura la red, el gabinete no se entera— y no depende de que nadie sea
disciplinado.

QUÉ HACE Y DÓNDE SE DETIENE
───────────────────────────
Graba el anillo, recorta el clip del evento y gotea capturas. **No sube nada**: deja los
ficheros en `pendientes/` con su metadato al lado. La subida es su propia ficha
(`T-3.11.b`) porque cruza a la nube, pide un grant firmado y tiene que auditarse; mezclarla
aquí haría que un fallo de red pareciera un fallo de grabación.

**Tampoco cuenta personas.** El conteo autoritativo vive en la nube (`D-24`), y el
preliminar local está **aplazado hasta que exista el equipo de campo** —Pi 5 de 8 GB o
Pi 4 de 8 GB, todavía sin comprar— porque `B.2` no se puede medir en una máquina que no es
la que va a ejecutar.

POR QUÉ EL GOTEO SE PARA POR TOPE Y NO POR REINGRESO
────────────────────────────────────────────────────
El diseño dice «gotea hasta que la gente empiece a volver a entrar». Detectar eso exige
contar, y aquí no se cuenta. Así que el gabinete gotea hasta agotar `max_stills` y **la
nube encuentra `t_reingreso` dentro de la serie** que le llega. El resultado para el
reporte es el mismo; lo que cambia es quién lo decide, y lo decide el que tiene el modelo.

Con los valores de fábrica el goteo cubre **cinco horas** (600 capturas × 30 s), que es
holgura de sobra para un dictamen. Un evento nuevo también cierra la sesión anterior: si
hay una réplica, la evidencia que importa es la de la réplica.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from takab_edge.cctv.disparo import Disparo, disparo_en
from takab_edge.cctv.onvif import Fuentes, sin_credenciales
from takab_edge.cctv.recorder import (
    SEGMENTO_S,
    clips_a_soltar,
    cmd_captura,
    cmd_clip,
    cobertura,
    escribir_lista_concat,
    leer_anillo,
    podar_anillo,
    segmentos_de_la_ventana,
)
from takab_edge.config.settings import CctvConfig

log = logging.getLogger("takab_edge.cctv")

#: Cuántos `event_id` recordamos para no re-disparar. Acotado a propósito: un `set` que
#: crece para siempre en un proceso que vive meses es una fuga lenta, y una fuga de memoria
#: en el gabinete sí alcanza el camino de vida por la vía del OOM killer.
_MEMORIA_EVENTOS = 256


class Fase(StrEnum):
    OCIOSO = "ocioso"
    CLIP = "clip"
    GOTEO = "goteo"


@dataclass
class Sesion:
    """Un evento en curso: su ventana de clip y su goteo posterior."""

    disparo: Disparo
    fin_clip: datetime
    proxima_captura: datetime
    capturas: int = 0
    clip_cortado: bool = False


@dataclass
class ClienteCctv:
    """Orquesta el anillo, el clip y el goteo. Todo el I/O entra por parámetro.

    `leer_status`, `correr` y `reloj` se inyectan por constructor —como todos los dobles de
    este árbol— para que la máquina de estados se pruebe sin cámara, sin ffmpeg y sin edge.
    """

    config: CctvConfig
    fuentes: Fuentes
    directorio: Path
    leer_status: Callable[[], dict]
    correr: Callable[[list[str]], int]
    reloj: Callable[[], datetime] = lambda: datetime.now(UTC)

    fase: Fase = Fase.OCIOSO
    sesion: Sesion | None = None
    _vistos: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ ciclo

    def paso(self) -> Fase:
        """Un tick del cliente. **Nunca lanza**: devuelve la fase en la que quedó.

        Un tick que revienta no puede matar el bucle —el proceso quedaría vivo y mudo, que
        es peor que caído porque nadie lo reinicia—. Cada trozo va aislado y el error se
        registra entero.
        """
        ahora = self.reloj()
        try:
            self._podar(ahora)
        except OSError:
            log.exception("cctv: la poda del anillo falló (¿disco?)")

        try:
            estado = self.leer_status()
        except Exception:  # noqa: BLE001 — el edge puede estar reiniciándose; no es asunto nuestro
            log.warning("cctv: no se pudo leer /api/status; se sigue grabando el anillo")
            estado = {}

        try:
            self._avanzar(estado, ahora)
        except Exception:  # noqa: BLE001
            log.exception("cctv: el tick falló; el anillo sigue y se reintenta al siguiente")
        return self.fase

    def _avanzar(self, estado: dict, ahora: datetime) -> None:
        nuevo = disparo_en(estado, ya_vistos=frozenset(self._vistos))
        if nuevo is not None:
            self._abrir_sesion(nuevo, ahora)

        if self.sesion is None:
            self.fase = Fase.OCIOSO
            return

        # El clip se corta UNA vez, cuando su ventana ya pasó entera. Cortarlo antes daría
        # un fichero al que le falta el final justo del minuto que importa.
        if not self.sesion.clip_cortado and ahora >= self.sesion.fin_clip:
            self._cortar_clip(self.sesion)
            self.sesion.clip_cortado = True
            self.fase = Fase.GOTEO

        if self.sesion.clip_cortado:
            self._gotear(self.sesion, ahora)
            if self.sesion.capturas >= self.config.max_stills:
                log.info(
                    "cctv: goteo del evento %s agotado (%d capturas); la nube ubicará el reingreso",
                    self.sesion.disparo.event_id,
                    self.sesion.capturas,
                )
                self.sesion = None
                self.fase = Fase.OCIOSO
        else:
            self.fase = Fase.CLIP

    def _abrir_sesion(self, disparo: Disparo, ahora: datetime) -> None:
        if self.sesion is not None:
            # Réplica: la evidencia que importa es la nueva. Se cierra la anterior sin
            # ceremonia —su clip ya está cortado o ya no llegará— en vez de intercalar dos
            # goteos que se pisarían el intervalo.
            log.warning(
                "cctv: evento %s llega con %s en curso; se cierra el anterior",
                disparo.event_id,
                self.sesion.disparo.event_id,
            )
        self._vistos.append(disparo.event_id)
        del self._vistos[:-_MEMORIA_EVENTOS]
        self.sesion = Sesion(
            disparo=disparo,
            fin_clip=disparo.t0 + timedelta(seconds=self.config.clip_post_s),
            proxima_captura=disparo.t0 + timedelta(seconds=self.config.clip_post_s),
        )
        self.fase = Fase.CLIP

    # ----------------------------------------------------------------- trozos

    def _pendientes(self) -> Path:
        destino = self.directorio / "pendientes"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def _cortar_clip(self, sesion: Sesion) -> None:
        """Recorta [t0−pre, t0+post] del anillo y lo deja en `pendientes/`."""
        desde = sesion.disparo.t0 - timedelta(seconds=self.config.clip_pre_s)
        hasta = sesion.fin_clip
        segmentos = leer_anillo(self.directorio)
        trozos = segmentos_de_la_ventana(segmentos, desde, hasta)
        if not trozos:
            log.error(
                "cctv: el anillo no cubre nada de la ventana del evento %s; no hay clip",
                sesion.disparo.event_id,
            )
            return

        cubierto = cobertura(segmentos, desde, hasta)
        if cubierto < 0.99:
            # Se corta igual y se DECLARA: un clip que empieza tarde porque el gabinete
            # arrancó hace un minuto sigue siendo evidencia útil. Uno que dice cubrir
            # T−60 s sin cubrirlo es una mentira en un reporte.
            log.warning(
                "cctv: el clip de %s cubre el %.0f%% de su ventana (el anillo no llega más atrás)",
                sesion.disparo.event_id,
                cubierto * 100,
            )

        base = f"clip-{sesion.disparo.t0.strftime('%Y%m%dT%H%M%SZ')}-{sesion.disparo.event_id}"
        salida = self._pendientes() / f"{base}.mp4"
        lista = self.directorio / f".{base}.concat"
        escribir_lista_concat(trozos, lista)
        # El primer segmento casi nunca empieza justo en `desde`: `-ss` descuenta ese sobrante.
        recorte = max(0.0, (desde - trozos[0].inicio).total_seconds())
        codigo = self.correr(
            cmd_clip(
                self.config.ffmpeg_path,
                lista,
                salida,
                recorte_s=recorte,
                duracion_s=(hasta - desde).total_seconds(),
            )
        )
        lista.unlink(missing_ok=True)
        if codigo != 0:
            log.error(
                "cctv: ffmpeg falló al recortar el clip de %s (código %d)",
                sesion.disparo.event_id,
                codigo,
            )
            salida.unlink(missing_ok=True)
            return

        self._escribir_metadato(base, sesion, cubierto, desde, hasta)
        log.warning("cctv: clip listo para subir: %s", salida.name)

    def _escribir_metadato(
        self, base: str, sesion: Sesion, cubierto: float, desde: datetime, hasta: datetime
    ) -> None:
        """El JSON que el subidor necesita. Va al lado del clip y **sin credenciales**."""
        (self._pendientes() / f"{base}.json").write_text(
            json.dumps(
                {
                    "event_id": sesion.disparo.event_id,
                    "tier": sesion.disparo.tier,
                    "source": sesion.disparo.source,
                    "t0": sesion.disparo.t0.isoformat(),
                    "desde": desde.isoformat(),
                    "hasta": hasta.isoformat(),
                    "cobertura": round(cubierto, 4),
                    "perfil": self.config.perfil_efectivo,
                    "fuente": sin_credenciales(self.fuentes.rtsp(self.config.perfil_efectivo)),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _gotear(self, sesion: Sesion, ahora: datetime) -> None:
        if ahora < sesion.proxima_captura:
            return
        sesion.proxima_captura = ahora + timedelta(seconds=self.config.still_interval_s)
        origen = self.fuentes.snapshot or self.fuentes.rtsp(self.config.perfil_efectivo)
        salida = (
            self._pendientes()
            / f"still-{ahora.strftime('%Y%m%dT%H%M%SZ')}-{sesion.disparo.event_id}.jpg"
        )
        if self.correr(cmd_captura(self.config.ffmpeg_path, origen, salida)) != 0:
            log.warning("cctv: no se pudo tomar la captura %s", salida.name)
            salida.unlink(missing_ok=True)
            return
        sesion.capturas += 1

    def _podar(self, ahora: datetime) -> None:
        """Anillo por edad y cuota, y clips pendientes por número. En cada tick."""
        for seg in podar_anillo(
            leer_anillo(self.directorio),
            ahora=ahora,
            ring_s=max(self.config.ring_s, self.config.clip_pre_s + 2 * SEGMENTO_S),
            cuota_bytes=self.config.disk_quota_mb * 1024 * 1024,
        ):
            seg.ruta.unlink(missing_ok=True)

        pendientes = sorted(self._pendientes().glob("clip-*.mp4"))
        for clip in clips_a_soltar(pendientes, maximo=self.config.max_clips_pendientes):
            clip.unlink(missing_ok=True)
            clip.with_suffix(".json").unlink(missing_ok=True)
