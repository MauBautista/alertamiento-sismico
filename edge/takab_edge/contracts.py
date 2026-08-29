"""Contratos internos del edge (Pydantic v2).

Fuente de verdad tipada de los payloads que fluyen entre módulos
(seedlink→signal→rules→actuators/cloud) y de lo que `cloud` publica hacia
AWS IoT Core. En T-1.11 se promueven a JSON Schema versionados en
`shared/schemas/` (blueprint §0.1: "la nube se construye sobre contratos ya
validados en el edge"); aquí viven como su origen tipado.

Reglas de oro relevantes (CLAUDE.md §2):
- Idempotencia: todo evento que cruza edge→nube lleva `event_id` (nonce).
- El camino SASMEX→actuador es determinista; estos modelos no contienen IA.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Timestamp UTC timezone-aware (evita datetimes naive en el contrato)."""
    return datetime.now(UTC)


def new_event_id() -> str:
    """Nonce de evento para idempotencia edge→nube (CLAUDE.md §2.3)."""
    return uuid4().hex


class Tier(StrEnum):
    """Tiers deterministas del motor de reglas (blueprint §4.5)."""

    NORMAL = "normal"
    WATCH = "watch"
    RESTRICTED = "restricted"
    EVACUATE_OR_HOLD = "evacuate_or_hold"
    MANUAL_ONLY = "manual_only"


class AlertSource(StrEnum):
    """Origen de una detección/evento local (blueprint §4.5)."""

    SASMEX = "sasmex"  # WR-1 dry-contact — canal primario y autoritativo
    # Valor = incidents.trigger (db/schema.sql); NO "threshold" — evitaría DLQ en T-1.17.
    THRESHOLD = "local_threshold"  # umbral instrumental local (PGA/PGV)
    MANUAL = "manual"  # disparo manual autorizado


class ActuatorChannel(StrEnum):
    SIREN = "siren"
    STROBE = "strobe"
    GAS_VALVE = "gas_valve"
    ELEVATOR = "elevator"
    DOOR_RETAINER = "door_retainer"
    #: [T-1.59] Canal LÓGICO de comandos de sistema (self_test): no es un relé —
    #: jamás entra a LOCAL_RELAY_CHANNELS/REFLEX_CHANNELS ni al modelo de demandas.
    SYSTEM = "system"


class FailSafeMode(StrEnum):
    """Estado seguro por canal ante falla del Pi (SPOF-07, blueprint §4.7)."""

    NORMALLY_OPEN = "NO"  # sirena: una falla NO la deja sonando
    NORMALLY_CLOSED = "NC"  # retenedor de puerta: una falla LIBERA la puerta
    FAIL_CLOSE = "fail_close"  # válvula de gas: una falla la CIERRA


class ActuatorAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    #: [T-1.59] Autodiagnóstico del gabinete (canal `system`): pulsa los relés NO
    #: audibles con readback; la sirena JAMÁS se energiza en un self-test.
    SELF_TEST = "self_test"
    #: [T-1.60] Simulacro institucional (canal `system`): banner NO-real + voceo
    #: de simulacro si hay audio. CERO relés; una alerta real lo ABORTA.
    DRILL_START = "drill_start"
    DRILL_STOP = "drill_stop"
    #: [T-2.70] Activar una release ya desplegada y verificada (canal `system`).
    #: NO trae código: el artefacto llegó por `deploy.sh` y quedó inerte en
    #: `releases/<id>/`. Esto es la ORDEN de estrenarla, que es lo que la nube
    #: necesita gobernar para hacer un canary por cohortes.
    UPDATE_ACTIVATE = "update_activate"
    #: [T-2.70] Volver a la release anterior. Existe aunque el gabinete revierta
    #: SOLO ante un remojo fallido: el fallo que el remojo no puede ver es el que
    #: se descubre media hora después desde el SOC (latencias raras, un sensor
    #: que dejó de reportar), y ahí la orden tiene que poder venir de fuera.
    UPDATE_ROLLBACK = "update_rollback"


class ActuationCause(StrEnum):
    """[T-2.86.a · hueco `RO-4.e`] POR QUÉ se movió un relé. No es cosmético: es la
    mitad de la bitácora que responde a un perito o a un seguro.

    `ActuatorAck` lleva canal, acción, `event_id`, éxito y latencia — y **no lleva
    actor**; el `audit_log` vivía sólo en la nube. O sea que el caso exacto para el
    que existe el gabinete (regla de oro 2: el edge opera sin nube) era el único que
    no dejaba constancia de quién ordenó cerrar el gas.

    **CAUSA y ACTOR no son lo mismo, y en el edge casi nunca hay una persona.** La
    causa es este enum, cerrado; el actor es una cadena que nombra a quien lo pidió
    (`wr-1`, `edge:rules`, `cloud:<command_id>`, `lan`). El mapeo de cada origen a su
    causa vive en :mod:`takab_edge.audit` y se **deriva** de dos conjuntos que ya
    existían en el código (`AlertSource` y `GPIO_ACTIONS`), no de una lista escrita
    a mano: un origen nuevo entra solo en la comprobación.
    """

    #: Contacto seco del WR-1 — canal primario. Sin persona detrás, por diseño.
    SASMEX = "sasmex"
    #: Umbral instrumental de ESTA estación (visual-only salvo `instrumental_actuation`).
    LOCAL_THRESHOLD = "local_threshold"
    #: Disparo manual autorizado que llega como decisión de tier.
    MANUAL = "manual"
    #: Comando FIRMADO de la nube sin `origin` de quórum: alguien en la consola.
    CLOUD_COMMAND = "cloud_command"
    #: Comando FIRMADO con `origin=quorum`: ≥3 estaciones lo confirmaron (T-2.32).
    NETWORK_QUORUM = "network_quorum"
    #: Autodiagnóstico de relés NO audibles (T-1.59), pedido por comando firmado.
    CABINET_SELF_TEST = "cabinet_self_test"
    #: Acciones del panel LAN (T-1.53/T-1.67/T-1.69) — el operador de pie en el sitio.
    LAN_SILENCE = "lan_silence"
    LAN_SIREN_TEST = "lan_siren_test"
    LAN_ACTUATION_TEST = "lan_actuation_test"
    LAN_TEST_MODE = "lan_test_mode"
    LAN_RESET = "lan_reset"
    #: Nadie declaró la causa. Se ESCRIBE así y se grita: un hueco visible es una
    #: pregunta para quien revisa; un hueco silencioso es el defecto `RO-4.e`.
    UNDECLARED = "undeclared"


class SirenReason(StrEnum):
    """[T-2.49] POR QUÉ suena la sirena. No es cosmético: decide QUÉ se oye.

    Hasta ahora el voceo miraba solo ``gpio.siren_sounding`` —un booleano eléctrico— y
    reproducía el mismo ``siren.wav`` en todos los casos. Consecuencia: el self-test de
    sirena de un operador sonaba **byte a byte idéntico** a un sismo real dentro de un
    edificio con gente. Eso es una falsa alarma provocada por el propio sistema.

    El orden de precedencia importa y es el de la seguridad: si una alerta real llega
    DURANTE una prueba, la razón es ``ALERT``. Nunca al revés.
    """

    ALERT = "alert"  # SASMEX enclavado o demanda de `rules`: es de verdad
    SAFE_STATE = "safe_state"  # estado seguro durable (drive_all_safe)
    TEST = "test"  # self-test de sirena o prueba local de actuación


class UpsStatus(StrEnum):
    LINE = "line"  # RED ELÉCTRICA
    BATTERY = "battery"  # EN BATERÍA
    UNKNOWN = "unknown"


class WaveformPacket(BaseModel):
    """Paquete de muestras de un canal (miniSEED decodificado)."""

    network: str = "AM"
    station: str
    location: str = ""
    channel: str  # EHZ, ENZ, ENN, ENE
    starttime: datetime
    sample_rate: float = 100.0
    samples: list[int]  # counts (el RS4D entrega enteros)

    @property
    def npts(self) -> int:
        return len(self.samples)

    @property
    def endtime(self) -> datetime:
        """Tiempo de la última muestra (para lag y detección de gaps)."""
        if not self.samples or self.sample_rate <= 0:
            return self.starttime
        return self.starttime + timedelta(seconds=(self.npts - 1) / self.sample_rate)

    @property
    def next_starttime(self) -> datetime:
        """Inicio esperado del paquete contiguo siguiente (fin de cobertura)."""
        if self.sample_rate <= 0:
            return self.starttime
        return self.starttime + timedelta(seconds=self.npts / self.sample_rate)


class Feature1s(BaseModel):
    """Features agregadas a 1 s — contrato de salida de `signal` (T-1.6)."""

    station: str
    channel: str
    window_start: datetime
    pga: float  # g
    pgv: float  # cm/s
    rms: float
    sta_lta: float
    clipping: bool = False
    health_score: float = 1.0


class FeatureBatch(BaseModel):
    """Lote de Feature1s de tier `normal` (T-1.56 · batcheo escalonado por tier).

    Solo TELEMETRÍA REPONIBLE: en reposo el gateway acumula ~10 s de features y
    publica 1 mensaje (≈97% menos publishes/SQS); al escalar a `watch`+ se hace
    flush inmediato y se vuelve al 1 Hz individual (`feature_1s`). La detección
    y la actuación JAMÁS pasan por aquí. ``max_length=256`` ≈ 64 KB « 128 KB
    (tope de publish de AWS IoT). Sin ``event_id`` ⇒ sin dedup de spool (como
    los features sueltos); la idempotencia real es la PK ``(ts, sensor_id,
    channel)`` de la nube.
    """

    kind: Literal["feature_batch"] = "feature_batch"
    gateway_id: str
    features: list[Feature1s] = Field(min_length=1, max_length=256)
    batched_at: datetime = Field(default_factory=utcnow)


class SasmexSignal(BaseModel):
    """Estado del contacto seco del WR-1 — canal primario (blueprint §4.5)."""

    active: bool
    source: str = "WR-1"
    is_test: bool = False  # pulso de prueba periódica de CIRES (SPOF-03)
    received_at: datetime = Field(default_factory=utcnow)


class TierDecision(BaseModel):
    """Decisión del motor de reglas (T-1.8). Sin IA — 100% determinista."""

    event_id: str = Field(default_factory=new_event_id)
    tier: Tier
    source: AlertSource
    severity: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utcnow)


class ActuatorCommand(BaseModel):
    channel: ActuatorChannel
    action: ActuatorAction
    event_id: str
    issued_at: datetime = Field(default_factory=utcnow)
    # [T-2.86.a] Quién lo ordenó y por qué. Viajan CON el comando, no por un canal
    # lateral, porque `ActuatorManager._record` —el embudo único por el que pasa
    # toda actuación, suelta o en lote— es donde se escribe la bitácora: si la causa
    # no viene aquí, no hay dónde sacarla sin adivinar.
    #
    # El default es `UNDECLARED` y NO un valor plausible a propósito: un emisor
    # nuevo que no declare su causa deja una fila que dice `undeclared` y un
    # `log.error`, en vez de una fila que miente diciendo «sasmex».
    #
    # Contrato INTERNO del edge: `ActuatorCommand` no está en `MODELS`
    # (`takab_edge/schemas.py`) y por tanto no tiene espejo en `shared/schemas/` —
    # esto no cambia ningún payload que cruce a la nube.
    cause: ActuationCause = ActuationCause.UNDECLARED
    #: Quien lo pidió, tal y como el EDGE puede saberlo. Nunca se inventa una
    #: persona: un comando de nube se identifica por su `command_id` firmado y es
    #: la nube quien lo une a su operador en `commands`.
    actor: str = ""


class ChannelState(BaseModel):
    """[T-2.116] Estado del canal TRAS EL ARBITRAJE de demandas. No es la orden.

    La spec móvil §2.2 (`takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:536`)
    exige que «el resultado real llega en el ``command_ack`` con el estado
    recalculado del relé», y §2.1 lo pide igual para el checklist BMS: «lo
    mostrado es el estado del relé recalculado por el arbitraje de demandas, no
    la última orden enviada». Hasta esta ficha ese campo NO EXISTÍA en ningún
    contrato: los ACKs decían `success=true` y `detail="relay"`, o sea «la orden
    se ejecutó», y la nube no tenía forma de distinguir eso de «el relé cambió».

    La diferencia es exactamente el caso de vida de la spec: un `deactivate` de
    sirena con una alerta vigente RETIRA la demanda manual y se ejecuta con
    éxito, y la sirena **sigue sonando** porque el enclave de SASMEX (o de
    `rules`) la sostiene. Con `success` a secas eso se leía «silenciada».

    El arbitraje que esto declara vive ENTERO en
    :meth:`~takab_edge.gpio.GpioController._desired_energized`: `_safed`,
    `_sasmex_latched`, `_rules_demand`, `_audible_silenced`, `_siren_test_active`
    y `_actuation_test_active`, más la polaridad fail-safe del canal. Aquí no se
    recalcula nada — se TRANSPORTA lo que el dueño de los pines ya decidió,
    leído de una sola instantánea (`GpioLink.snapshot`, un solo lock).

    `activated` es la respuesta a «¿está protegiendo?» y es AGNÓSTICA de la
    polaridad; `energized` es el nivel eléctrico crudo, que para `FAIL_CLOSE`
    (gas) y `NORMALLY_CLOSED` (retenedores) significa lo contrario que para la
    sirena. Van las dos, con su `fail_safe`, para que la afirmación sea
    verificable y no haya que conocer el perfil del gabinete para leerla.
    """

    channel: ActuatorChannel
    #: Nivel ELÉCTRICO del relé tras el recálculo.
    energized: bool
    #: ¿El canal quedó en su estado de PROTECCIÓN? Para la sirena esto es, letra
    #: por letra, `GpioController.siren_sounding` (los dos comparan `energized`
    #: contra `active_energized(fail_safe)`).
    activated: bool
    fail_safe: FailSafeMode
    #: POR QUÉ (T-2.49). Hoy sólo lo declara el canal `siren`, que es el único
    #: para el que el gabinete lo deriva; `None` en el resto significa «este
    #: canal no declara motivo», nunca «sin motivo». Para la sirena, `None` con
    #: `activated=False` es simplemente que no suena.
    reason: SirenReason | None = None
    #: ¿Queda ALGUNA demanda de alerta enclavada (SASMEX o `rules`)? Es lo que
    #: convierte «sigue sonando» en «sigue sonando POR ALGO», sin que el
    #: consumidor tenga que inferirlo de la fase del incidente en la nube.
    alert_latched: bool = False


class ActuatorAck(BaseModel):
    """ACK de ejecución con latencia relativa (T+0.42s, blueprint §4.2)."""

    channel: ActuatorChannel
    action: ActuatorAction
    event_id: str
    success: bool
    latency_s: float  # segundos desde el comando
    executed_at: datetime = Field(default_factory=utcnow)
    detail: str = ""
    #: [T-2.116] Estado del canal TRAS EL ARBITRAJE (schema 1.11.0). ADITIVO y
    #: nullable: `None` = «este driver no puede leer el relé» (BACnet, o la
    #: costura del gabinete caída), jamás «el relé está en reposo». La nube lo
    #: persiste en `incident_actions.payload.channel_state`, que es lo que el
    #: checklist BMS de §2.1 necesita para dejar de pintar la última orden.
    channel_state: ChannelState | None = None

    @property
    def relative_label(self) -> str:
        """Etiqueta legible tipo ``T+0.42s`` para UI/telemetría."""
        return f"T+{self.latency_s:.2f}s"


class ActuationRecord(BaseModel):
    """[T-2.86.a] UNA fila de la bitácora local de actuación, subiendo a la nube.

    Es el otro extremo del cable de `RO-4.e`. El gabinete ya anotaba en disco
    quién movió cada relé y por qué —también sin enlace, que es el caso entero—;
    esto es lo que sube cuando el enlace vuelve.

    **`record_id` lo pone el gabinete y es la clave de idempotencia** (regla de
    oro 3). Lo local NO se borra al subir —el perito lo lee meses después—, así
    que en vez de vaciar un directorio se avanza una marca de agua; si esa marca
    se pierde, el gabinete re-sube filas que la nube ya tiene y el `ON CONFLICT
    DO NOTHING` de la ingesta las absorbe.

    **`channel` y `action` son `str`, no enums, y es deliberado.** El panel del
    gabinete registra su propio vocabulario (`silence`, `siren_test`,
    `arm_test_mode`… de `GPIO_ACTIONS`) además de los canales de relé, y los dos
    conjuntos crecen por su cuenta. En un canal de EVIDENCIA, un enum estrecho no
    protege: convierte una fila que no supimos anticipar en un descarte a DLQ —
    o sea, en la pérdida del registro justo del incidente raro, que es el que
    alguien va a peritar. La causa sí es un enum cerrado porque es la
    clasificación, y esa la controla el edge entero.

    **`online` es tri-estado.** `true` había enlace, `false` no lo había —la fila
    que responde a la pregunta de la ficha—, y `None` «no se pudo saber».
    Colapsar el `None` a `false` sería inventar el dato en el contrato que existe
    para no inventarlo.
    """

    seq: int
    record_id: str
    at: datetime
    gateway_id: str
    tenant_id: str
    site_id: str
    cause: ActuationCause
    actor: str
    channel: str
    action: str
    success: bool
    detail: str = ""
    event_id: str = ""
    online: bool | None = None


class BackfillRequest(BaseModel):
    """Solicitud de URL pre-firmada para backfill/evidencia (T-1.25).

    El edge la publica en ``takab/backfill/request/<thing>``; la nube verifica
    que el thing del topic sea el principal X.509 y responde un
    ``backfill_grant`` por ``takab/backfill/grant/<thing>`` con la KEY CANÓNICA
    (autoridad de la nube) y la URL PUT pre-firmada.
    """

    kind: Literal["backfill_request"] = "backfill_request"
    request_id: str = Field(default_factory=new_event_id)
    #: [T-3.11.b] `cctv_clip`/`cctv_still` reutilizan ESTE contrato y ESTE topic a
    #: propósito. Un topic MQTT nuevo obliga a tocar la política fleet de AWS IoT, y un
    #: topic no autorizado **desconecta al gabinete en cada publish** (medido el
    #: 2026-07-12). Ampliar un enum no toca terraform.
    mode: Literal["backfill", "evidence", "cctv_clip", "cctv_still"]
    #: Ventana temporal de los datos (backfill), del evento (evidence) o del clip
    #: (cctv_clip). Para `cctv_still` los dos extremos son el instante de la captura.
    ts_from: datetime
    ts_to: datetime
    #: Nº de líneas NDJSON (backfill; dimensiona y audita el objeto esperado).
    lines: int = 0
    #: Evento local (== incidents.event_uuid en la nube). Obligatorio en 'evidence' y en
    #: los dos modos de CCTV: es lo que ata el objeto a su incidente.
    event_id: str = ""
    #: sha256 del objeto a subir; la key lo incluye, así que re-subir el MISMO contenido
    #: es idempotente por construcción — igual para el miniSEED que para el clip.
    sha256: str = ""


class CommandAck(BaseModel):
    """ACK de un comando remoto firmado (T-1.23). Viaja por ``takab/acks``: el
    campo ``kind`` es el discriminador frente a ``ActuatorAck`` (contrato
    ``command_ack.schema.json``); la nube transiciona ``commands.status``."""

    kind: Literal["command_ack"] = "command_ack"
    command_id: str
    nonce: str
    channel: ActuatorChannel
    action: ActuatorAction
    success: bool
    latency_s: float = 0.0
    executed_at: datetime = Field(default_factory=utcnow)
    detail: str = ""
    #: [T-1.59] Resultados estructurados del self_test (por relé + salud del
    #: cache); None en acks de activate/deactivate. ADITIVO (schema 1.4.0).
    results: dict | None = None
    #: [T-2.116] EL CAMPO QUE LA SPEC §2.2 EXIGE: el estado del canal tras el
    #: arbitraje de demandas, no la intención del comando. ADITIVO y nullable
    #: (schema 1.11.0): `None` en los acks de RECHAZO —donde no hubo ejecución y
    #: por tanto no hay arbitraje que declarar— y en los de canal `system`, que
    #: no gobierna ningún relé. La nube lo persiste en `commands.ack`.
    channel_state: ChannelState | None = None


class RelayState(BaseModel):
    channel: ActuatorChannel
    energized: bool  # estado eléctrico del relé
    activated: bool = False  # estado lógico de protección (p.ej. gas CERRADO, puerta LIBERADA)
    fail_safe: FailSafeMode


class HealthSnapshot(BaseModel):
    """Snapshot de salud del gabinete (T-1.10; honesto desde T-1.40).

    Los campos de sonda son OPCIONALES: ``None`` = «sin dato» (no hay UPS, no
    hay fuente NTP, cert ilegible) y la nube lo muestra como S/D. Un valor
    presente es una MEDICIÓN — nunca el default optimista de antes (100% de
    batería, 365 días de cert, offset 0.0), que era mentira (regla de oro 7).
    """

    gateway_id: str
    captured_at: datetime = Field(default_factory=utcnow)
    ntp_offset_s: float | None = None
    seedlink_lag_s: float = 0.0
    packet_loss_pct: float = 0.0
    mqtt_rtt_ms: float | None = None
    ups_status: UpsStatus = UpsStatus.UNKNOWN
    battery_pct: float | None = None
    # [T-2.22] Autonomía restante del UPS en SEGUNDOS (P-8). Ya se medía en
    # `UpsReading.runtime_s` y el snapshot la perdía. ADITIVO (schema 1.7.0):
    # None = «sin dato» (UPS ausente o sin reportarla) ⇒ S/D, jamás un número
    # optimista. La nube la persiste en `device_health.battery_min_left` (min).
    ups_runtime_s: float | None = None
    temperature_c: float = 0.0
    cert_days_remaining: int | None = None
    # [T-1.53] % de disco usado (shutil.disk_usage) — None = sin dato (regla de
    # oro 7). ADITIVO (schema 1.2.0): el ingest de la nube lo ignora (sin
    # columna destino), el panel LAN lo muestra.
    disk_used_pct: float | None = None
    # [T-1.74] SHA corto del código desplegado, leído de `FW_VERSION` (lo escribe
    # `deploy/edge/deploy.sh`). ADITIVO (schema 1.6.0). `None` = «este gabinete no
    # sabe qué versión corre» — el caso normal en desarrollo local. La nube lo
    # persiste en `gateways.fw_version` y NUNCA pisa lo que ya tenga con un None:
    # ese campo se llenaba a mano y se habría quedado obsoleto en silencio.
    fw_version: str | None = None
    # [T-2.70] SHA que ESTE PROCESO cargó al arrancar, congelado (no se relee).
    # ADITIVO (schema 1.9.0). `fw_version` de arriba dice qué código hay EN EL
    # DISCO; este dice cuál se está EJECUTANDO. Difieren exactamente cuando un
    # despliegue escribió el código y el reinicio no ocurrió (o falló), que es
    # el estado que una actualización remota tiene que detectar y hasta ahora
    # era invisible desde la nube. `None` = no se puede saber, jamás se rellena
    # con el del disco.
    fw_running: str | None = None
    # [T-2.49] Perfil de tonos EFECTIVO del gabinete: qué IDs de catálogo se
    # aplicaron y cuáles se rechazaron (por desconocidos o reservados). ADITIVO,
    # mismo patrón que `disk_used_pct`: el ingest de la nube lo ignora mientras no
    # haya columna destino, y el panel LAN ya lo muestra. Sirve para responder
    # "¿qué gabinetes se quedaron atrás de un cambio de catálogo?" sin ir uno a uno.
    audio: dict | None = None
    # [T-2.70.a·B1] Censo eléctrico de los relés, y su AUSENCIA. RELAJANTE
    # (schema 1.10.0): un payload 1.9.0 con `[]` o con filas sigue validando.
    #
    # · lista con filas — el censo MEDIDO.
    # · `[]`  — pregunté al dueño de los pines y no hay filas que reportar (el
    #   módulo no corre, o este gabinete no tiene relés cableados). Es un HECHO.
    # · `None` — **no pude preguntar**. Ni sé qué relés hay, ni en qué estado.
    #
    # La tercera no existía, y hasta D3 tampoco hacía falta: el dueño de los
    # pines vivía en este mismo proceso y una lectura suya no tenía transporte
    # que caerse. Desde que `takab-gpio` es un proceso aparte (`gpio_owner=gpio`)
    # el caso es alcanzable en producción, y es el PEOR alcanzable: nadie
    # gobierna la sirena, el gas, los ascensores ni los retenedores mientras
    # `takab-edge` sigue latiendo como si nada. Fundido con `[]`, la nube lo leía
    # como «módulo detenido» y el SOC pintaba verde un edificio sin proteger.
    #
    # `None` es el DEFAULT a propósito (regla de oro 7): un snapshot que no
    # preguntó no puede afirmar que no hay relés.
    relays: list[RelayState] | None = None
    transition_reason: str = "heartbeat"


class LocalEvent(BaseModel):
    """Evento local confirmado — idempotente por `event_id`; cruza a la nube."""

    event_id: str = Field(default_factory=new_event_id)
    tenant_id: str
    site_id: str
    source: AlertSource
    tier: Tier
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceObject(BaseModel):
    """Evidencia inmutable: ventana miniSEED de un evento subida a S3, con sha256.

    Idempotente por (`event_id`, `sha256`): re-subir el mismo contenido = mismo objeto.
    """

    event_id: str
    s3_key: str
    sha256: str
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=utcnow)


class SecondaryCabinetState(BaseModel):
    """[T-2.33] Estado de un gabinete secundario LoRa (ESP32 + sirena/estrobo).

    Es lo que el panel del gabinete pinta por secundario (sección ``lora`` de
    ``/api/status``); el JSON Schema espejo ancla el contrato para el firmware
    ESP32 futuro. ``link``: ``never`` (jamás visto) · ``online`` · ``offline``
    (heartbeat ausente > factor×periodo). ``acked``: estado del último comando
    propagado (``None`` = sin comando pendiente).
    """

    id: int
    name: str
    zone: str = ""
    age_s: float | None = None
    battery_mv: int | None = None
    rssi_dbm: float | None = None
    snr_db: float | None = None
    alarm_active: bool = False
    link: Literal["never", "online", "offline"] = "never"
    acked: bool | None = None
