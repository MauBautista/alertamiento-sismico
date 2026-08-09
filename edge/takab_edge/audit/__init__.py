"""audit — la bitácora LOCAL de actuación del gabinete (T-2.86.a · hueco `RO-4.e`).

**El defecto que cierra.** `ActuatorAck` lleva canal, acción, `event_id`, éxito y
latencia — y **no lleva actor**. Y no existía ningún `audit_log` en todo el edge: la
bitácora vivía **sólo** en la nube. O sea que el caso exacto para el que existe el
gabinete —**regla de oro 2, el edge opera sin nube**— era precisamente el que no
dejaba constancia. Si el gas se cierra durante un corte de internet, después nadie
puede decir quién lo ordenó ni con qué causa. Es lo primero que pide un perito o un
seguro, y es la mitad no construida de la **regla de oro 4**: «el proceso GPIO es
mínimo *y auditable*».

CÓMO SE DERIVA EL CONJUNTO DE CAUSAS (y por qué así)
----------------------------------------------------
No se inventa: se saca de conjuntos que **ya estaban cerrados en el código**, de modo
que un origen nuevo entre en la comprobación **solo**, sin que nadie se acuerde:

* :data:`CAUSE_BY_ALERT_SOURCE` — un mapeo TOTAL sobre
  :class:`~takab_edge.contracts.AlertSource`, que es lo que hace que `rules` ordene
  una secuencia de tier (SASMEX, umbral instrumental, manual).
* :data:`CAUSE_BY_GPIO_ACTION` — un mapeo TOTAL sobre
  :data:`~takab_edge.gpio_link.GPIO_ACTIONS`, la **lista blanca** de la costura: lo
  que no está ahí no se puede pedir al dueño de los pines, así que es el censo
  autoritativo de los orígenes «de operador».
* :data:`CAUSE_BY_COMMAND_ORIGIN` — los dos valores de `origin` que viajan DENTRO de
  la firma de un comando de nube (T-2.32). No hay un enum que censar, así que este
  es el único mapeo enumerado a mano, y por eso el default (`None`) también está
  declarado en vez de caer a `UNDECLARED` por accidente.

`tests/test_actuation_ledger.py` exige la TOTALIDAD de los dos primeros: añadir un
miembro a `AlertSource` o una acción a `GPIO_ACTIONS` sin declarar su causa pone el
build en rojo. Lo que queda FUERA por construcción está dicho abajo, con todas las
letras.

LO QUE ESTA BITÁCORA **NO** VE, DECLARADO
------------------------------------------
El **reflejo SASMEX→sirena+estrobo** vive ENTERO dentro del dueño de los pines
(`gpio._dispatch_sasmex`, gate #6) y **no cruza la costura**: no pasa por
`ActuatorManager` ni por `GpioLink.apply`, así que este módulo no lo puede registrar
desde aquí. Lo que sí queda escrito del mismo episodio es la secuencia NO refleja que
`rules` ordena a continuación (sirena incluida, que es idempotente con el reflejo),
con `cause=sasmex`. Registrar el reflejo mismo exige escribir dentro del proceso
`takab-gpio`, que tiene su propio presupuesto de dependencias (regla de oro 4) y es
tarea aparte.

CÓMO SOBREVIVE AL REINICIO (y por qué no repite la trampa de `T-2.67.b`)
-------------------------------------------------------------------------
Aquella cola «durable» se perdía entera al reiniciar porque nadie fijaba su
directorio: sin `TAKAB_EDGE_CLOUD_SPOOL_DIR` —que `provision_gateway.sh` **no
escribe**— `_tmp_spool()`/`_default_pending_dir()` hacen un **`mkdtemp` NUEVO en cada
arranque**. Aquí el directorio se **deriva** y es estable:

* con `cloud_spool_dir` → hermano del spool, y **durable de verdad** (NVMe del Pi);
* sin él → `<tmp>/takab-audit-<uid>-<gateway_id>`, que es el MISMO patrón que
  `EdgeSettings.gpio_lock_file`: sobrevive al reinicio del PROCESO siempre, y se
  **declara `durable=False`** porque un directorio temporal no sobrevive
  necesariamente al reinicio del SISTEMA. Declararlo es lo que impide leer un
  «0 actuaciones» como un hecho cuando es una amnesia.

El `gateway_id` va en el nombre porque el agravante fichado en `T-2.67.b` era
justamente un `/tmp/backfill-pending` **compartido** entre procesos y corridas.

QUÉ PASA SI NO SE PUEDE ESCRIBIR
---------------------------------
La sirena suena igual. Ni el constructor ni :meth:`ActuationLedger.record` lanzan
jamás: misma doctrina que el registro del cerrojo, que es informativo a propósito.
Pero «no tumbar» no es «callar»: el fallo se cuenta (`write_failures`), se nombra
(`last_error`) y sale en :meth:`state`, que es lo que lee el panel del gabinete.

CÓMO SUBE SIN DUPLICARSE (regla de oro 3)
------------------------------------------
Igual que la evidencia: constancia durable en disco + drenado al volver el enlace.
La diferencia es que aquí **lo local no se borra al subir** (el perito lo lee meses
después), así que en vez de vaciar un directorio se avanza una **marca de agua**
(`uploaded.seq`, escritura atómica + fsync). Reiniciar no re-sube nada. Y cada fila
lleva su `record_id` para que la nube pueda hacer `ON CONFLICT DO NOTHING` aunque la
marca se pierda.

**El `sink` es `None` por defecto, y eso es deliberado.** La política IoT del fleet
lista los topics **uno a uno, sin comodines**: publicar en un topic no autorizado
hace que el broker **desconecte al gabinete en cada publish** (visto en producción el
2026-07-12, flapping cada 10 s, `infra/terraform/modules/iot-core/main.tf`). Hasta
que exista la mitad de nube —topic autorizado, regla IoT, tabla e ingesta— subir
sería cambiar un hueco de auditoría por un gabinete mudo. El mecanismo está entero y
probado; lo que falta es el permiso.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from takab_edge.contracts import (
    ActuationCause,
    ActuatorAction,
    ActuatorChannel,
    AlertSource,
    utcnow,
)
from takab_edge.gpio_link import GPIO_ACTIONS

if TYPE_CHECKING:
    from takab_edge.config import EdgeSettings

log = logging.getLogger("takab_edge.audit")

#: Nombre del archivo vivo; los rotados llevan sufijo `.1`, `.2`… (más viejo = mayor).
_LEDGER_NAME = "actuation.ndjson"
#: Marca de agua de subida: último `seq` que la nube confirmó.
_WATERMARK_NAME = "uploaded.seq"
#: Tamaño máximo del archivo vivo antes de rotar. 1 MiB ≈ 4 000 actuaciones.
_MAX_BYTES = 1 << 20
#: Archivos conservados (vivo + rotados). 4 MiB ≈ 16 000 actuaciones: un gabinete no
#: actúa tantas veces en la vida útil de un despliegue, así que la rotación es una
#: red de seguridad contra el disco lleno, no un régimen de retención.
_KEEP = 4


# --------------------------------------------------------------------------- causas

#: Origen de detección → causa. TOTAL sobre `AlertSource` (lo exige un test).
CAUSE_BY_ALERT_SOURCE: dict[AlertSource, ActuationCause] = {
    AlertSource.SASMEX: ActuationCause.SASMEX,
    AlertSource.THRESHOLD: ActuationCause.LOCAL_THRESHOLD,
    AlertSource.MANUAL: ActuationCause.MANUAL,
}

#: Acción de la costura → causa. TOTAL sobre `GPIO_ACTIONS` (lo exige un test).
#: `arm/disarm_test_mode` no mueve un relé por sí solo, pero cambia lo que el
#: gabinete hará con el siguiente disparo real: para un perito eso es parte del
#: relato y por eso se registra igual.
CAUSE_BY_GPIO_ACTION: dict[str, ActuationCause] = {
    "silence": ActuationCause.LAN_SILENCE,
    "siren_test": ActuationCause.LAN_SIREN_TEST,
    "actuation_test": ActuationCause.LAN_ACTUATION_TEST,
    "arm_test_mode": ActuationCause.LAN_TEST_MODE,
    "disarm_test_mode": ActuationCause.LAN_TEST_MODE,
    "reset": ActuationCause.LAN_RESET,
    "cabinet_self_test": ActuationCause.CABINET_SELF_TEST,
}

#: `origin` DENTRO de la firma de un comando de nube → causa (T-2.32). `None` = la
#: firma no declaró origen: sigue siendo un comando de nube legítimo, no un hueco.
CAUSE_BY_COMMAND_ORIGIN: dict[str | None, ActuationCause] = {
    "quorum": ActuationCause.NETWORK_QUORUM,
    None: ActuationCause.CLOUD_COMMAND,
}

#: Acciones de la costura que nadie mapeó — **DERIVADO**, no escrito a mano. El test
#: exige que esté vacío; existe además como valor del módulo (y se grita al importar)
#: para que el hueco se vea también EN EL GABINETE y no sólo en un job de CI, que es
#: la diferencia entre una guarda y un adorno.
GPIO_ACTIONS_SIN_CAUSA: frozenset[str] = frozenset(GPIO_ACTIONS) - frozenset(CAUSE_BY_GPIO_ACTION)
ALERT_SOURCES_SIN_CAUSA: frozenset[AlertSource] = frozenset(AlertSource) - frozenset(
    CAUSE_BY_ALERT_SOURCE
)
if GPIO_ACTIONS_SIN_CAUSA or ALERT_SOURCES_SIN_CAUSA:  # pragma: no cover — guarda
    log.error(
        "hay orígenes de actuación sin causa declarada: acciones=%s orígenes=%s. "
        "Actuarán, y su fila de bitácora dirá 'undeclared'.",
        sorted(GPIO_ACTIONS_SIN_CAUSA),
        sorted(str(s) for s in ALERT_SOURCES_SIN_CAUSA),
    )

#: Actores canónicos. No son personas: en el edge casi nunca hay una.
ACTOR_WR1 = "wr-1"  # contacto seco del receptor SASMEX
ACTOR_RULES = "edge:rules"  # motor de reglas determinista de ESTE gabinete
ACTOR_LAN = "lan"  # panel del gabinete (PIN compartido: sin identidad de persona)


def cause_for_alert_source(source: AlertSource) -> ActuationCause:
    """Causa de una decisión de tier. Un origen sin declarar sale `UNDECLARED` y grita."""
    causa = CAUSE_BY_ALERT_SOURCE.get(source)
    if causa is None:
        log.error("origen de alerta %r sin causa declarada; la fila dirá 'undeclared'", source)
        return ActuationCause.UNDECLARED
    return causa


def cause_for_gpio_action(action: str) -> ActuationCause:
    """Causa de una acción de la costura. Idem: sin declarar, se escribe y se grita."""
    causa = CAUSE_BY_GPIO_ACTION.get(action)
    if causa is None:
        log.error("acción de la costura %r sin causa declarada; la fila dirá 'undeclared'", action)
        return ActuationCause.UNDECLARED
    return causa


def cause_for_command_origin(origin: object) -> ActuationCause:
    """Causa de un comando FIRMADO, según el `origin` que viaja dentro de la firma."""
    clave = origin if isinstance(origin, str) else None
    causa = CAUSE_BY_COMMAND_ORIGIN.get(clave)
    if causa is None:
        log.error("comando firmado con origin=%r sin causa declarada", origin)
        return ActuationCause.UNDECLARED
    return causa


# -------------------------------------------------------------------------- registro


def ledger_dir_for(settings: EdgeSettings) -> Path:
    """Directorio DERIVADO y ESTABLE de la bitácora (ver la trampa de `T-2.67.b`).

    Con `cloud_spool_dir` es hermano del spool; sin él, un nombre derivado del uid y
    del `gateway_id` bajo el temporal del sistema — **jamás un `mkdtemp`**, que es lo
    que hace que la cola de evidencia se evapore en cada arranque del Pi real.
    """
    if settings.cloud_spool_dir:
        return Path(settings.cloud_spool_dir).parent / "actuation-ledger"
    gabinete = settings.gateway_id or "sin-id"
    return Path(tempfile.gettempdir()) / f"takab-audit-{os.getuid()}-{gabinete}"


class ActuationLedger:
    """Bitácora local de actuación: append-only, durable, con actor y causa.

    JAMÁS lanza desde `record()`: el camino de vida no puede caerse porque el disco
    esté lleno. Los fallos se cuentan y se declaran en :meth:`state`.
    """

    def __init__(
        self,
        settings: EdgeSettings,
        *,
        directory: str | Path | None = None,
        sink: Callable[[dict], bool] | None = None,
        online: Callable[[], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
        max_bytes: int = _MAX_BYTES,
        keep: int = _KEEP,
    ) -> None:
        self._settings = settings
        self.directory = Path(directory) if directory else ledger_dir_for(settings)
        #: Callable que entrega UNA fila a la nube y devuelve si se confirmó.
        #: `None` = sin subida (ver la nota sobre la política IoT en el módulo).
        self.sink = sink
        #: Sonda de enlace. Va en el LEDGER y no en cada llamador a propósito: si
        #: cada origen tuviera que acordarse de pasarlo, el que se olvidara sería
        #: justo el que actuó a oscuras. `None` ⇒ la fila dice `online: null`, que
        #: es «no se pudo saber», nunca un `false` inventado (regla de oro 7).
        self._online = online
        self._clock = clock or utcnow
        self._max_bytes = max_bytes
        self._keep = max(1, keep)
        self._lock = threading.Lock()
        self._seq = 0
        self._write_failures = 0
        self._last_error: str = ""
        self._writable = True
        self._dropped_unsent = 0
        self._unreadable_lines = 0
        #: Durable de VERDAD sólo con un directorio fijado: un temporal del sistema
        #: sobrevive al reinicio del proceso, no necesariamente al de la máquina.
        self._durable = bool(directory or settings.cloud_spool_dir)
        self._durable_reason = (
            ""
            if self._durable
            else (
                "sin `cloud_spool_dir`: la bitácora vive en el temporal del sistema; "
                "sobrevive al reinicio del PROCESO, no al del sistema"
            )
        )
        self._prepare()

    # ------------------------------------------------------------------ interno

    def _prepare(self) -> None:
        """Crea el directorio y recupera el contador. Nunca lanza (corre en `build()`)."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._fail(f"no se pudo crear el directorio de la bitácora: {exc}", contar=False)
            return
        try:
            self._seq = max((r.get("seq", 0) for r in self._read_all_unlocked()), default=0)
        except OSError as exc:  # pragma: no cover — el read ya degrada por archivo
            self._fail(f"no se pudo releer la bitácora al arrancar: {exc}", contar=False)

    def _fail(self, mensaje: str, *, contar: bool = True) -> None:
        self._last_error = mensaje
        self._writable = False
        if contar:
            self._write_failures += 1
        log.error("bitácora de actuación: %s", mensaje)

    @property
    def _live(self) -> Path:
        return self.directory / _LEDGER_NAME

    @property
    def _watermark_path(self) -> Path:
        return self.directory / _WATERMARK_NAME

    def _files_oldest_first(self) -> list[Path]:
        """Rotados (mayor sufijo = más viejo) y luego el vivo."""
        rotados: list[tuple[int, Path]] = []
        for ruta in self.directory.glob(f"{_LEDGER_NAME}.*"):
            try:
                rotados.append((int(ruta.suffix.lstrip(".")), ruta))
            except ValueError:
                continue
        return [ruta for _n, ruta in sorted(rotados, reverse=True)] + [self._live]

    def _rotate_if_needed(self) -> None:
        vivo = self._live
        try:
            if not vivo.exists() or vivo.stat().st_size < self._max_bytes:
                return
        except OSError:
            return
        marca = self._read_watermark()
        # El más viejo se cae del borde: si llevaba filas SIN subir, se declara.
        caduco = self.directory / f"{_LEDGER_NAME}.{self._keep - 1}"
        if caduco.exists():
            sin_subir = sum(1 for r in self._read_file(caduco) if r.get("seq", 0) > marca)
            if sin_subir:
                self._dropped_unsent += sin_subir
                log.error(
                    "la rotación de la bitácora se llevó %d fila(s) que nunca subieron "
                    "(%s). El registro local es finito por diseño: la copia permanente "
                    "es la de la nube.",
                    sin_subir,
                    caduco.name,
                )
            caduco.unlink(missing_ok=True)
        for n in range(self._keep - 2, 0, -1):
            origen = self.directory / f"{_LEDGER_NAME}.{n}"
            if origen.exists():
                origen.replace(self.directory / f"{_LEDGER_NAME}.{n + 1}")
        vivo.replace(self.directory / f"{_LEDGER_NAME}.1")

    def _fsync_dir(self) -> None:
        fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    # -------------------------------------------------------------------- escritura

    def record(
        self,
        *,
        cause: ActuationCause,
        actor: str,
        channel: ActuatorChannel | str,
        action: ActuatorAction | str,
        success: bool = True,
        detail: str = "",
        event_id: str = "",
        online: bool | None = None,
    ) -> None:
        """Anota UNA actuación. **Nunca lanza** (el camino de vida no se puede caer).

        `online` es «¿había enlace cuando ocurrió?». Es el dato que convierte esta
        fila en la respuesta al caso de `RO-4.e`: la actuación que ocurrió a oscuras.
        """
        if cause is ActuationCause.UNDECLARED:
            log.error(
                "actuación %s/%s registrada SIN causa declarada (actor=%r, event_id=%r): "
                "el origen no dijo por qué actuó",
                getattr(channel, "value", channel),
                getattr(action, "value", action),
                actor,
                event_id,
            )
        if online is None and self._online is not None:
            try:
                online = bool(self._online())
            except Exception:  # noqa: BLE001 — sin dato antes que un dato inventado
                online = None
        try:
            with self._lock:
                self._seq += 1
                fila = {
                    "seq": self._seq,
                    "record_id": uuid4().hex,
                    "at": self._clock().isoformat(),
                    "gateway_id": self._settings.gateway_id,
                    "tenant_id": self._settings.tenant_id,
                    "site_id": self._settings.site_id,
                    "cause": str(getattr(cause, "value", cause)),
                    "actor": actor,
                    "channel": str(getattr(channel, "value", channel)),
                    "action": str(getattr(action, "value", action)),
                    "success": bool(success),
                    "detail": detail,
                    "event_id": event_id,
                    "online": online,
                }
                self._rotate_if_needed()
                # `ensure_ascii=False` NO: la fila viaja por MQTT y por `grep` en el
                # gabinete; ASCII puro evita sorpresas de codificación en el journal.
                linea = json.dumps(fila, separators=(",", ":"), sort_keys=True)
                assert "\n" not in linea  # noqa: S101 — NDJSON: una fila, una línea
                with open(self._live, "a", encoding="utf-8") as fh:
                    fh.write(linea + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())  # un sismo suele cortar la luz al Pi
                self._fsync_dir()
                self._writable = True
        except Exception as exc:  # noqa: BLE001 — vida: la sirena suena igual
            self._fail(f"no se pudo escribir la fila ({type(exc).__name__}: {exc})")

    def record_ack(self, command, ack, *, online: bool | None = None) -> None:
        """Anota a partir de un `ActuatorCommand` + su `ActuatorAck` — el embudo real."""
        self.record(
            cause=command.cause,
            actor=command.actor or ACTOR_RULES,
            channel=ack.channel,
            action=ack.action,
            success=ack.success,
            detail=ack.detail,
            event_id=ack.event_id,
            online=online,
        )

    # --------------------------------------------------------------------- lectura

    def _read_file(self, ruta: Path) -> list[dict]:
        filas: list[dict] = []
        try:
            crudo = ruta.read_text("utf-8")
        except OSError:
            return filas
        for linea in crudo.splitlines():
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except ValueError:
                # Corte de energía a mitad de escritura: la línea rota NO puede
                # cegar el resto de la bitácora (criterio de `DurableSpool`).
                self._unreadable_lines += 1
                continue
            if isinstance(fila, dict) and "seq" in fila:
                filas.append(fila)
            else:
                self._unreadable_lines += 1
        return filas

    def _read_all_unlocked(self) -> list[dict]:
        self._unreadable_lines = 0
        filas = [f for ruta in self._files_oldest_first() for f in self._read_file(ruta)]
        filas.sort(key=lambda f: f.get("seq", 0))
        return filas

    def read_all(self) -> list[dict]:
        """Todas las filas conservadas, del más viejo al más nuevo. Nunca lanza."""
        try:
            with self._lock:
                return self._read_all_unlocked()
        except Exception:  # noqa: BLE001 — una lectura forense no tumba nada
            log.exception("bitácora de actuación: no se pudo leer")
            return []

    # ---------------------------------------------------------------------- subida

    def _read_watermark(self) -> int:
        try:
            return int(self._watermark_path.read_text("utf-8").strip() or 0)
        except (OSError, ValueError):
            return 0

    def _write_watermark(self, seq: int) -> None:
        tmp = self._watermark_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(seq))
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self._watermark_path)  # atómico: la marca nunca queda a medias
        self._fsync_dir()

    def pending(self) -> list[dict]:
        """Filas que la nube todavía no confirmó (más viejas primero)."""
        marca = self._read_watermark()
        return [f for f in self.read_all() if f.get("seq", 0) > marca]

    def drain(self) -> int:
        """Entrega los pendientes por el `sink` y avanza la marca. Nunca lanza.

        La marca sólo avanza sobre filas CONFIRMADAS y en orden: un sink a medias
        deja lo no entregado pendiente en vez de darlo por subido. Reiniciar no
        re-sube nada, que es la mitad «sin duplicarse» de la regla de oro 3.
        """
        if self.sink is None:
            return 0
        subidos = 0
        try:
            with self._lock:
                marca = self._read_watermark()
                pendientes = [f for f in self._read_all_unlocked() if f.get("seq", 0) > marca]
                for fila in pendientes:
                    try:
                        ok = bool(self.sink(fila))
                    except Exception:  # noqa: BLE001 — el transporte no tumba el drenado
                        log.exception("bitácora: el sink lanzó; el pendiente sigue pendiente")
                        break
                    if not ok:
                        break
                    marca = fila.get("seq", marca)
                    subidos += 1
                if subidos:
                    self._write_watermark(marca)
        except Exception:  # noqa: BLE001 — jamás al hilo que la llama
            log.exception("bitácora de actuación: el drenado falló")
        if subidos:
            log.info("bitácora de actuación: %d fila(s) confirmadas por la nube", subidos)
        return subidos

    # ---------------------------------------------------------------------- estado

    def state(self) -> dict:
        """Lo que el panel del gabinete necesita saber, incluido lo que NO se puede."""
        filas = self.read_all()
        marca = self._read_watermark()
        return {
            "path": str(self.directory),
            "durable": self._durable,
            "durable_reason": self._durable_reason,
            "writable": self._writable,
            "records": len(filas),
            "pending": sum(1 for f in filas if f.get("seq", 0) > marca),
            "uploads_enabled": self.sink is not None,
            "write_failures": self._write_failures,
            "last_error": self._last_error,
            "dropped_unsent": self._dropped_unsent,
            "unreadable_lines": self._unreadable_lines,
            "last_at": filas[-1]["at"] if filas else None,
        }
