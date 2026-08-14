"""T-2.71 · Qué alarma puede callarse durante una ventana de mantenimiento.

Este módulo es la mitad peligrosa de la tarea. Todo lo demás (una fila, un
banner) es contabilidad; aquí se decide **qué vigilancia se apaga**, y una
decisión de más produce un sistema que parece vigilado sin estarlo.

**De dónde salen los hechos de AWS que se citan aquí.** Del modelo de servicio
que trae el CLI instalado (``CLI_SERVICE_MODEL``), que se lee SIN credenciales y
sin red. Lo que no está ahí no se afirma: este archivo llegó a justificar su
decisión central con una frase entrecomillada como si fuera de la documentación
de AWS que **no existe en la documentación de AWS**, y una razón que no se
sostiene obliga a volver a tomar la decisión, no a reescribir la frase.

Y porque una cita verdadera SIN ANCLAR es la siguiente cita inventada esperando
su turno, toda frase de AWS que se escriba aquí va **en cursiva entrecomillada**
(la marca que el escáner de tests reconoce) y además declarada en ``AWS_CITAS``,
que se confronta palabra por palabra contra el modelo de servicio. Sin ese
eslabón, cambiar un «will trigger» por un «will NOT trigger» dentro de
``delete_mute`` dejaba la suite entera en verde: el test comparaba el modelo con
su PROPIA copia de la frase, no con la que el código enseña a quien lo lee.

Cinco decisiones, con su porqué:

1. **El mecanismo es ``PutAlarmMuteRule``, no ``actions_enabled``, ni dejar de
   publicar la métrica, ni un filtro SNS.** Cuatro razones, las cuatro
   comprobables de primera mano:

   - **La decisiva: una mute rule no puede no vencer.** ``Schedule`` declara
     ``required = ["Expression", "Duration"]``, y ``Duration`` es *"The length of
     time that alarms remain muted when the schedule activates."* El vencimiento
     no es una promesa nuestra: es un campo obligatorio del contrato.
     ``actions_enabled = false`` no tiene vencimiento de ninguna clase — se queda
     apagada hasta que alguien se acuerde, y aquí no hay worker que se acuerde (a
     propósito, ver el punto 2).
   - **Se deshace en la dirección segura, y eso sí está escrito.**
     ``DeleteAlarmMuteRule``: *"any alarms that are currently being muted by that
     rule are immediately unmuted. If those alarms are in an ALARM state, their
     configured actions will trigger. This operation is idempotent."* Cerrar
     antes de tiempo hace que el correo pendiente SALGA. Volver a poner
     ``actions_enabled = true`` no promete nada equivalente en ninguna parte.
   - **IAM queda como segunda línea de defensa sobre las intocables.**
     ``PutAlarmMuteRule`` exige el permiso *"on two types of resources: the alarm
     mute rule resource itself, and each alarm that the rule targets"*. La vía
     ``actions_enabled`` pasaría por ``PutMetricAlarm``, cuyo permiso además
     permite reescribir umbral, métrica y acciones: radio de daño incomparable
     para conseguir lo mismo.
   - **No muta la alarma.** Su configuración queda intacta, así que no hay estado
     a medio cambiar que un ``terraform apply`` tenga que reconciliar —y
     ``actions_enabled`` sí es atributo gestionado por Terraform, o sea drift.

   Y la cuarta alternativa, dejar de publicar la métrica, **no silencia: pagina**.
   ``gateway_offline`` vive en ``treat_missing_data = "breaching"``: el silencio
   de ``Takab/Sensor/<gw>`` ES la condición de alarma.

   **EL AGUJERO, dicho en voz alta porque no se puede tapar offline.** El modelo
   de servicio describe qué pasa mientras la regla está activa (*"targeted alarms
   continue to evaluate metrics and transition between states, but their
   configured actions (such as Amazon SNS notifications or Auto Scaling actions)
   are muted"*) y qué pasa al BORRARLA (se re-disparan). **No
   dice nada de qué pasa cuando la ventana vence sola.** Así que aquí se trata
   como que NO re-dispara: una ventana que se deja expirar puede dejar una alarma
   en ALARM sin que salga el correo, porque las acciones de CloudWatch disparan
   en TRANSICIÓN y esa transición ya ocurrió con la regla activa. Dos
   consecuencias, y ninguna es cosmética:
     · operativa — **cerrar la ventana explícitamente**, que es la única vía con
       re-disparo documentado, en vez de dejarla expirar;
     · acotada — el daño máximo es ``MAX_WINDOW_S`` (4 h) y la alarma sigue
       visible en ALARM en CloudWatch, mientras que ``actions_enabled = false``
       no tiene techo.
   Medirlo contra la cuenta real es **pendiente de gate `HUMANO-AWS`**, junto con
   la disponibilidad de la API en us-east-2. Hasta entonces esto es una decisión
   tomada con lo que se puede leer, no un hecho comprobado en producción.

2. **No hay proceso de vencimiento porque no hay proceso.** El tope de la casa
   (``MAX_WINDOW_S``) está muy por debajo del máximo de AWS (``P15D``): una
   ventana de mantenimiento que necesita quince días no es una ventana. La
   pregunta "¿y si el job de vencimiento muere?" se contesta borrando el job.

3. **Nada de ventanas recurrentes.** ``Rule.Schedule.Expression`` es OBLIGATORIA
   y admite dos formatos: ``cron(...)`` recurrente y ``at(yyyy-MM-ddThh:mm)`` de
   una sola vez. Una regla recurrente **no expira jamás** salvo que se le ponga
   ``ExpireDate`` — el modo de fallo que el criterio 3 existe para evitar,
   disfrazado de comodidad. Aquí la expresión no se acepta de nadie: se DERIVA
   del reloj y solo puede salir un ``at()``.

4. **Los nombres se DERIVAN, jamás se aceptan.** Las alarmas de CloudWatch se
   identifican por nombre y NO llevan dimensión de tenant: si el cuerpo de una
   petición pudiera traer nombres, un tenant silenciaría los del vecino, o los de
   plataforma. La frontera multi-tenant de esta superficie es el ORIGEN de la
   lista, no un check que alguien pueda olvidar.

5. **Un éxito a medias se cuenta como silencio, no como fracaso — pero la duda
   tiene que ser real.** Si la llamada que silencia llega y la que lo comprueba
   no, las alarmas están MUDAS. Decir ``0/N`` ahí es afirmar que la vigilancia
   sigue viva con la vigilancia apagada, y —peor— tirar el nombre de la regla,
   que es lo único con lo que se puede deshacer. Ante la duda se asume el estado
   más PELIGROSO y se conserva lo necesario para revertirlo; el acuse lo marca
   como NO verificado para que nadie lea esa cifra como medida.

   Ahora bien, hay **tres** familias de fallo, no dos, y la tercera no tiene
   ninguna duda dentro: la petición que **ni salió** (sin credenciales, endpoint
   sin resolver, conexión que no llegó a abrirse, parámetro rechazado por el
   propio cliente). Contarla como silencio sería la inferencia inválida de esta
   fase con el signo cambiado —antes se daba por entregado lo publicado; aquí se
   daría por silenciado lo que ni se envió— y pintaría "vigilancia apagada" con
   las alarmas sonando. Ver ``apply_mute``, ``aws_rechazo_definitivo`` y
   ``peticion_nunca_salio``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

#: Dónde se comprueban, sin credenciales ni red, las citas de AWS de este módulo.
#: Es el modelo de servicio que el propio CLI usa para construir las llamadas, o
#: sea la fuente de la que sale el comportamiento, no una página que lo describe.
#: Se cita la RUTA y no el texto para que quien dude vaya a leerlo:
#:
#:   python3 -c "import json;d=json.load(open(CLI_SERVICE_MODEL));\
#:               print(d['operations']['DeleteAlarmMuteRule']['documentation'])"
CLI_SERVICE_MODEL = (
    "/usr/local/aws-cli/v2/<version>/dist/awscli/botocore/data/cloudwatch/2010-08-01/service-2.json"
)


@dataclass(frozen=True)
class CitaAws:
    """Una frase de AWS que este código cita, con DÓNDE se comprueba.

    ``donde`` es la ruta dentro de ``CLI_SERVICE_MODEL``; ``texto`` es literal —
    ni parafraseado ni recortado por el medio con puntos suspensivos, porque una
    cita con elipsis no se puede confrontar por máquina y vuelve a depender de que
    alguien se acuerde.
    """

    donde: tuple[str, ...]
    texto: str


#: Toda cita de AWS del código de la ventana, declarada. El test que la confronta
#: contra el modelo de servicio no lee esta tabla y ya: exige además que cada
#: entrada aparezca LITERAL en la prosa y que cada cita de la prosa esté aquí. Sin
#: los dos sentidos el ancla no sujeta nada — que es exactamente lo que pasaba.
AWS_CITAS: tuple[CitaAws, ...] = (
    CitaAws(
        donde=("shapes", "Schedule", "members", "Duration", "documentation"),
        texto=("The length of time that alarms remain muted when the schedule activates."),
    ),
    CitaAws(
        donde=("operations", "DeleteAlarmMuteRule", "documentation"),
        texto=(
            "any alarms that are currently being muted by that rule are immediately "
            "unmuted. If those alarms are in an ALARM state, their configured actions "
            "will trigger. This operation is idempotent."
        ),
    ),
    CitaAws(
        donde=("operations", "DeleteAlarmMuteRule", "documentation"),
        texto=(
            "any alarms that are currently being muted by that rule are immediately "
            "unmuted. If those alarms are in an ALARM state, their configured actions "
            "will trigger. This operation is idempotent. If you delete a mute rule that "
            "does not exist, the operation succeeds without returning an error."
        ),
    ),
    CitaAws(
        donde=("operations", "PutAlarmMuteRule", "documentation"),
        texto=(
            "on two types of resources: the alarm mute rule resource itself, and each "
            "alarm that the rule targets"
        ),
    ),
    CitaAws(
        donde=("operations", "PutAlarmMuteRule", "documentation"),
        texto=(
            "targeted alarms continue to evaluate metrics and transition between states, "
            "but their configured actions (such as Amazon SNS notifications or Auto "
            "Scaling actions) are muted"
        ),
    ),
)

#: Silenciable en una ventana de GABINETE (acto del dueño del sitio).
GATEWAY = "gateway"
#: Silenciable en una ventana de PLATAFORMA (acto del dueño de la plataforma).
PLATFORM = "platform"
#: JAMÁS silenciable. El default seguro para toda alarma nueva.
NEVER = "never"

#: Mínimo de la CASA: 5 min. El de AWS es ``PT1M``; por debajo de esto una
#: "ventana" no da tiempo ni a llegar al gabinete, y sí a olvidarse de cerrarla.
MIN_WINDOW_S = 300
#: Tope de la casa: 4 h. AWS acepta hasta P15D; eso no es una ventana, es un
#: sistema apagado. Dentro de la ventana la alarma está muda en los TRES estados
#: (OK, ALARM e INSUFFICIENT_DATA), así que corta por política, no solo por AWS.
MAX_WINDOW_S = 4 * 3600


@dataclass(frozen=True)
class AlarmKind:
    """Una alarma del módulo ``observability`` y su clasificación.

    ``name_template`` es el ``alarm_name`` del recurso Terraform con ``{env}``
    en lugar del prefijo y ``{thing}`` en lugar del ``each.value``. Es la única
    forma de que este módulo y el Terraform hablen del mismo objeto: si divergen,
    la ventana silencia un nombre inexistente (el acuse lo dirá) y —mucho peor—
    el guardia deja de reconocer a las intocables.
    """

    resource: str
    scope: str
    name_template: str
    why: str


ALARM_CATALOG: tuple[AlarmKind, ...] = (
    # --- Silenciables SOLO sobre el gabinete intervenido -----------------------
    AlarmKind(
        resource="gateway_offline",
        scope=GATEWAY,
        name_template="takab-dev-gateway-offline-{thing}",
        why=(
            "El técnico que va físicamente al gabinete lo desconecta. >10 min sin latido "
            "es exactamente lo esperado mientras dure la intervención."
        ),
    ),
    AlarmKind(
        resource="sensor_mute",
        scope=GATEWAY,
        name_template="takab-dev-sensor-mudo-{thing}",
        why=(
            "Tocar el Shake o su cable de red corta el stream: el lag pasa de 120 s en el "
            "acto. Es el síntoma esperado de la intervención, no un hallazgo."
        ),
    ),
    # --- Silenciables SOLO en una ventana de PLATAFORMA ------------------------
    AlarmKind(
        resource="ec2_status",
        scope=PLATFORM,
        name_template="takab-dev-ec2-status-check",
        why="Un `make cloud-stop` deliberado o un ensayo de restore paran la instancia.",
    ),
    AlarmKind(
        resource="ec2_cpu",
        scope=PLATFORM,
        name_template="takab-dev-ec2-cpu-sostenida",
        why="Un restore de DB clava la CPU al 90 % durante minutos: ruido esperado.",
    ),
    # --- JAMÁS silenciables ----------------------------------------------------
    AlarmKind(
        resource="dlq_depth",
        scope=NEVER,
        name_template="takab-dev-dlq-{thing}",
        why=(
            "Es el INSTRUMENTO del canary de T-2.70: una actualización de flota que rompa "
            "el contrato de payload se manifiesta EXACTAMENTE aquí. Silenciarla durante un "
            "despliegue es apagar el detector del fallo que el despliegue puede causar — y "
            "T-2.70 pide rollback automático 'con criterio medible': esta es el criterio."
        ),
    ),
    AlarmKind(
        resource="iot_rule_errors",
        scope=NEVER,
        name_template="takab-dev-iot-rule-errors",
        why=(
            "El otro extremo del mismo instrumento: un payload que la regla IoT ya no sabe "
            "encaminar aparece aquí antes que en ningún otro sitio. Si el despliegue rompe "
            "la ingesta, esta alarma es la única que lo dice mientras se puede revertir."
        ),
    ),
    AlarmKind(
        resource="ghost_gateways",
        scope=NEVER,
        name_template="takab-dev-gateway-retirado-sigue-reportando",
        why=(
            "Vigila al vigilante. No es un síntoma operativo sino una CONTRADICCIÓN DE "
            "INVENTARIO con ventana propia de 1 h sostenida, y su insufficient_data_actions "
            "es la única señal de que el worker que cuenta está muerto (el bug de "
            "count_ghosts del 2026-08-04). Callarla recrea el punto ciego que T-2.60.a "
            "existe para cerrar."
        ),
    ),
    AlarmKind(
        resource="wal_archive_stalled",
        scope=NEVER,
        name_template="takab-dev-wal-archivado-atascado",
        why=(
            "[T-2.72] Es el ÚNICO instrumento que acota el RPO. El número que publica "
            "`terraform output rpo_seconds` no lo garantiza la configuración de Postgres: "
            "lo garantiza que esta alarma suene. Silenciarla no pausa el riesgo — lo "
            "vuelve invisible mientras sigue creciendo, y el RPO real pasa a ser "
            "ilimitado durante toda la ventana. "
            "EL CONTRAARGUMENTO, tomado en serio: durante un mantenimiento planificado "
            "de la DB el archivado SE PARA legítimamente (la instancia baja, el "
            "contenedor se recrea, un ensayo de restore la ocupa), así que esta alarma "
            "VA A SONAR y el operador va a recibir un correo por algo que él mismo "
            "provocó. Aun así es intocable, por tres razones. (1) El momento más "
            "probable de que el archivado se rompa PARA SIEMPRE es justo después de una "
            "ventana: config revertida, contenedor recreado sin `archive_mode`, "
            "credenciales que ya no resuelven. Callarla durante la ventana es callar "
            "exactamente la señal de que la ventana rompió el respaldo — el mismo "
            "argumento que hace intocables a dlq_depth e iot_rule_errors frente al "
            "canary de T-2.70. (2) El ruido es acotado y se cierra solo: un correo al "
            "entrar en ALARM y otro al volver a OK cuando el archivado se reanuda. Si "
            "el correo de OK NO llega, eso ES el hallazgo, y es la única forma barata "
            "de tenerlo. (3) La asimetría del daño: el ruido cuesta un correo de más; "
            "el silencio cuesta descubrir en el peor momento posible que el respaldo "
            "llevaba semanas sin funcionar — que es literalmente el estado que la "
            "Fase 2.6 existe para dejar atrás (`RUNBOOK-backup-restore-db.md:3`)."
        ),
    ),
    AlarmKind(
        resource="base_backup_missing",
        scope=NEVER,
        name_template="takab-dev-backup-base-ausente",
        why=(
            "[T-2.72.b] `wal_archive_stalled` vigila la CADENA de WAL; ésta vigila su ANCLA. "
            "Son cosas distintas y el modo de fallo de aquí es el peor de los dos: un backup "
            "base que falla cada semana **no se nota** —la cadena sigue archivando tan ricamente— "
            "hasta el día del restore, que es exactamente el estado que la Fase 2.6 existe para "
            "eliminar. Sin ancla, toda esa cadena no recupera nada. "
            "Y hay una razón de instrumento para que sea intocable: el que publica la métrica y "
            "el que hace el respaldo son EL MISMO host, así que si ésta calla, lo más probable es "
            "que tampoco esté corriendo `barman-cloud-backup`. Silenciarla es callar a la vez el "
            "síntoma y el detector. "
            "NACE EN ALARM a propósito, y no es un defecto: el día del apply todavía no hay "
            "backup base. El correo de OK al terminar el primero ES el acuse de que la cadena "
            "consiguió ancla — si no llega, eso es el hallazgo."
        ),
    ),
    AlarmKind(
        resource="db_disk_space",
        scope=NEVER,
        name_template="takab-dev-disco-datos-lleno",
        why=(
            "[T-2.72.c] El PITR trajo un modo de fallo que antes no existía: con el archivado "
            "atascado Postgres NO RECICLA su WAL, y `pg_wal` crece ~16 MiB/min sobre el mismo "
            "volumen de 40 GiB donde viven los datos — menos de dos días hasta llenar el disco y "
            "tumbar la base. Hoy eso lo cubre POR ACCIDENTE la alarma de atasco, y un accidente "
            "no es una vigilancia. "
            "Intocable porque el disco no distingue mantenimiento de avería: llenarse durante una "
            "ventana planificada tumba la DB exactamente igual, y encima una ventana es cuando más "
            "probable es que se llene (un ensayo de restore duplica el volumen). "
            "A diferencia de `base_backup_missing`, ésta trata la ausencia de dato como `missing` "
            "y no como `breaching`: su correo AFIRMA UNA MEDIDA («el disco pasó del 80 %»), y sin "
            "datapoint esa medida no existe — afirmarla sería la falta que T-2.60.a rechaza por "
            "escrito. La ceguera no queda tapada: si la instancia cae lo dice `ec2_status`, y si "
            "muere el cron que publica lo dice `wal_archive_stalled`, las dos `breaching` sobre el "
            "mismo `/etc/cron.d/takab-pitr`."
        ),
    ),
)


class ProtectedAlarmError(ValueError):
    """Se intentó silenciar una alarma que jamás debe callarse."""


def _kinds(scope: str) -> tuple[AlarmKind, ...]:
    return tuple(k for k in ALARM_CATALOG if k.scope == scope)


def _render(template: str, *, env: str, thing: str | None = None) -> str:
    name = template.replace("takab-dev-", f"{env}-", 1)
    if thing is not None:
        name = name.replace("{thing}", thing)
    return name


def mute_names_for_gateways(*, env: str, things: Iterable[str | None]) -> tuple[str, ...]:
    """Nombres de alarma de N gabinetes, derivados de su ``iot_thing``.

    Un gabinete sin ``iot_thing`` (dado de alta pero aún sin certificado) no
    aporta ningún nombre: no tiene alarmas que callar. Es un no-op explícito, no
    un error — la consola lo rotula aparte como SIN ALARMA EXISTENTE, que es un
    hecho distinto de "no acusó" (la lección de T-2.48).
    """
    out: list[str] = []
    for thing in things:
        if not thing or not thing.strip():
            continue
        for kind in _kinds(GATEWAY):
            out.append(_render(kind.name_template, env=env, thing=thing.strip()))
    return tuple(out)


def mute_names_for_platform(*, env: str) -> tuple[str, ...]:
    return tuple(_render(k.name_template, env=env) for k in _kinds(PLATFORM))


def protected_alarm_names(*, env: str) -> tuple[str, ...]:
    """Nombres (o prefijos, para las de ``for_each``) que nunca pueden callarse."""
    return tuple(_render(k.name_template, env=env).replace("{thing}", "") for k in _kinds(NEVER))


def assert_not_protected(names: Iterable[str], *, env: str) -> None:
    """Cinturón y tirantes sobre la derivación.

    Hoy los nombres nacen de filas de la DB y este guardia no puede dispararse.
    Existe para el día en que alguien abra un camino que los acepte: entonces
    esta línea es la única que separa "silenciar mi gabinete" de "apagar el
    detector de fallos de toda la plataforma".
    """
    prefijos = protected_alarm_names(env=env)
    for name in names:
        for prefijo in prefijos:
            if name.startswith(prefijo):
                raise ProtectedAlarmError(
                    f"la alarma {name!r} JAMÁS se silencia: coincide con {prefijo!r}. "
                    "Ver ALARM_CATALOG para la razón escrita."
                )


def iso8601_duration(seconds: int) -> str:
    """Duración ISO-8601 en minutos, con el rango de la casa validado aquí.

    Se valida en la traducción a propósito: es el último punto por el que pasa
    cualquier camino hacia AWS, así que un rango fuera de tope no puede colarse
    por una ruta que olvidara comprobarlo.
    """
    if not MIN_WINDOW_S <= seconds <= MAX_WINDOW_S:
        raise ValueError(
            f"duración fuera de rango: {seconds}s (permitido {MIN_WINDOW_S}..{MAX_WINDOW_S})"
        )
    if seconds % 60:
        raise ValueError(f"la duración debe ser múltiplo de 60 s: {seconds}")
    return f"PT{seconds // 60}M"


def mute_start(now: datetime) -> datetime:
    """Minuto (UTC) en el que la mute rule se activa: SIEMPRE el siguiente.

    ``at()`` tiene granularidad de minuto. Se redondea hacia ARRIBA porque un
    ``at()`` apuntando a un minuto ya empezado puede no activarse nunca, y
    entonces la fila diría "ventana abierta" con las alarmas vivas. Ese lado de
    la divergencia es el seguro —suenan— pero un retraso acotado a ≤60 s es
    preferible a un silencio del que no se sabe si existe.

    Este instante es también el que la fila guarda como ``starts_at``: la
    consola y AWS cuentan desde el MISMO borde, así que el "TERMINA HH:MM UTC"
    del banner no es una aproximación.
    """
    base = now.astimezone(UTC).replace(second=0, microsecond=0)
    return base + timedelta(minutes=1)


def at_expression(starts_at: datetime) -> str:
    """Expresión de UNA SOLA VEZ. Nunca sale un ``cron(...)`` de aquí."""
    return f"at({starts_at.astimezone(UTC).strftime('%Y-%m-%dT%H:%M')})"


@dataclass(frozen=True)
class MuteAck:
    """El acuse. ``PutAlarmMuteRule`` devolviendo 200 NO es "silenciado".

    ``silenced`` cuenta las alarmas que a la vez (a) EXISTEN en CloudWatch y (b)
    figuran en los objetivos que la regla guardó de verdad, releída. ``missing``
    es todo lo demás, y se rotula aparte: "no había alarma que silenciar" es un
    hecho distinto de "no se silenció" (mismo criterio que ``commandable`` en el
    simulacro — regla de oro 7).

    ``verified`` dice si esas cifras se MIDIERON. Cuando es ``False`` la llamada
    que silencia se emitió pero la que comprueba no pudo leerse, así que las
    cifras son una SUPOSICIÓN deliberadamente pesimista —se asume silencio, que
    es el estado peligroso— y ``rule_name`` es lo que permite deshacerlo. Un
    consumidor que ignore este campo estará leyendo una suposición como si fuera
    una medida, que es la familia de mentira que esta tarea existe para no
    cometer.
    """

    requested: int
    silenced: int
    missing_names: tuple[str, ...]
    rule_name: str | None = None
    verified: bool = True

    @property
    def missing(self) -> int:
        return len(self.missing_names)

    @property
    def complete(self) -> bool:
        return self.requested > 0 and self.silenced == self.requested


def aws_rechazo_definitivo(exc: BaseException) -> bool:
    """¿AWS **contestó** rechazando la llamada? Entonces no se silenció nada.

    Una de las dos formas de saber que NO hay nada mudo (la otra es
    ``peticion_nunca_salio``), y de ellas depende hacia qué lado se cae en la duda:

    - un 4xx es una negativa del servicio: la petición llegó, se evaluó y se
      rechazó (permiso, validación, throttling). La regla NO existe y las alarmas
      SUENAN — decir lo contrario mandaría a la consola a pintar "vigilancia
      apagada" con la vigilancia encendida, y nadie iría a mirar;
    - un 5xx, un corte a mitad o un timeout de LECTURA son AMBIGUOS: la petición
      pudo llegar y aplicarse antes de que se perdiera la respuesta.

    Se comprueba por FORMA (``exc.response``, como lo expone
    ``botocore.exceptions.ClientError``) y no importando botocore: aunque boto3 es
    hoy dependencia declarada de esta API, un ``import`` aquí convertiría el
    discriminador en un ``ImportError`` el día que un despliegue recortado —o un
    test— se quede sin él, y sería justo cuando hace falta. Que los nombres del
    otro discriminador sean REALES lo ancla el test contra ``botocore.exceptions``.
    """
    respuesta = getattr(exc, "response", None)
    if not isinstance(respuesta, dict):
        return False
    metadatos = respuesta.get("ResponseMetadata")
    if not isinstance(metadatos, dict):
        return False
    status = metadatos.get("HTTPStatusCode")
    return isinstance(status, int) and 400 <= status < 500


#: Excepciones de botocore que prueban que la petición **no llegó a salir**.
#:
#: El criterio para entrar aquí es estrecho y de un solo sentido: solo el fallo
#: que ocurre ANTES de escribir la petición en el cable. Si el error pudo ocurrir
#: con la petición ya enviada —``ConnectionClosedError`` (se cerró esperando
#: respuesta), ``ReadTimeoutError`` (se agotó la LECTURA), ``SSLError`` (el TLS
#: puede reventar leyendo, no solo en el saludo)— **no entra**: ahí la duda es
#: real y ante la duda se asume silencio. Equivocarse por este lado es declarar
#: "no silenciado" con el edificio mudo, que es el bloqueante que esta fase cerró.
#:
#: Los nombres se comparan por FORMA, igual que ``exc.response``, y se anclan
#: contra ``botocore.exceptions`` en el test: un nombre inventado no coincidiría
#: con nada y ese fallo volvería a contarse como silencio, en silencio.
AWS_PREVUELO: frozenset[str] = frozenset(
    {
        # No hubo con qué firmar: no se emitió ninguna petición.
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
        # No se supo a dónde: la URL del endpoint ni se construyó.
        "NoRegionError",
        "InvalidRegionError",
        "EndpointResolutionError",
        # El cliente rechazó los parámetros antes de serializar nada.
        "ParamValidationError",
        # La conexión no llegó a abrirse (TCP/proxy), así que nada viajó.
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ProxyConnectionError",
    }
)


def peticion_nunca_salio(exc: BaseException) -> bool:
    """¿Se SABE que la petición no llegó a enviarse? Entonces no hay nada mudo.

    La tercera familia, la que el discriminador por ``exc.response`` no veía:
    preguntar "¿contestó AWS?" parte el mundo en dos y mete en el saco ambiguo un
    fallo del que se sabe con certeza que no silenció nada. Ahí ``0/N`` está
    MEDIDO y el acuse puede decirlo sin fingir.
    """
    return type(exc).__name__ in AWS_PREVUELO


def no_se_silencio_nada(exc: BaseException) -> bool:
    """Las dos maneras de SABER que las alarmas siguen sonando.

    Todo lo que no cae en una de las dos es duda auténtica, y la duda se resuelve
    hacia el estado más peligroso: silenciado.
    """
    return aws_rechazo_definitivo(exc) or peticion_nunca_salio(exc)


class MuteClient(Protocol):
    """Lo mínimo de CloudWatch que este módulo usa (boto3-compatible)."""

    def put_alarm_mute_rule(self, **kwargs: Any) -> Any: ...

    def get_alarm_mute_rule(self, **kwargs: Any) -> Any: ...

    def delete_alarm_mute_rule(self, **kwargs: Any) -> Any: ...

    def describe_alarms(self, **kwargs: Any) -> Any: ...


def _ack_a_ciegas(rule_name: str, alarm_names: Sequence[str]) -> MuteAck:
    """El acuse de cuando NO se sabe: se asume silencio y se guarda cómo deshacerlo.

    Las dos mitades importan por igual. ``silenced = requested`` porque el estado
    peligroso es "mudo" y en la duda se asume el peligroso; ``rule_name`` porque
    sin él el cierre anticipado no tiene qué borrar y el edificio se queda sin
    vigilancia hasta que expire la ``Duration`` — hasta ``MAX_WINDOW_S``.
    """
    return MuteAck(
        requested=len(alarm_names),
        silenced=len(alarm_names),
        missing_names=(),
        rule_name=rule_name,
        verified=False,
    )


def apply_mute(
    client: MuteClient,
    *,
    rule_name: str,
    alarm_names: Sequence[str],
    duration_s: int,
    starts_at: datetime,
    env: str,
) -> MuteAck:
    """Emite la mute rule y devuelve lo que de VERDAD quedó silenciado.

    El orden importa por dos motivos distintos:

    - se valida contra el catálogo ANTES de tocar AWS, así que una alarma
      intocable ni siquiera llega a viajar por la red;
    - a partir del ``PutAlarmMuteRule`` **el nombre de la regla ya no se puede
      perder**. Cualquier fallo posterior deja alarmas potencialmente mudas, y el
      nombre es lo único que permite desilenciarlas antes de tiempo. Por eso la
      comprobación va en su propio ``try`` y no arrastra al acuse entero.

    Levanta la excepción original SOLO cuando se SABE que no hay nada silenciado
    (``no_se_silencio_nada``: AWS contestó rechazando, o la petición ni salió).
    Ahí el llamante puede declarar ``0/N`` honestamente.
    """
    assert_not_protected(alarm_names, env=env)
    duracion = iso8601_duration(duration_s)  # valida el rango aunque no haya objetivos
    if not alarm_names:
        # Sin objetivos no se crea nada: una mute rule vacía sería un objeto
        # huérfano en AWS que además ocultaría el hecho de que no había nada.
        return MuteAck(requested=0, silenced=0, missing_names=(), rule_name=None)

    try:
        client.put_alarm_mute_rule(
            Name=rule_name,
            MuteTargets={"AlarmNames": list(alarm_names)},
            Rule={"Schedule": {"Expression": at_expression(starts_at), "Duration": duracion}},
        )
    except Exception as exc:
        if no_se_silencio_nada(exc):
            raise
        # No se sabe si la petición llegó a aplicarse. Se asume que SÍ.
        return _ack_a_ciegas(rule_name, alarm_names)

    # --- PUBLICADO ≠ ENTREGADO: se relee, no se cree al 200. ------------------
    # Y si la relectura falla, el problema es de la MEDIDA, no del silencio: la
    # regla existe. Devolver aquí `0/N` con `rule_name=None` sería reportar un
    # éxito parcial como fracaso total y dejar el sistema callado y sin marcha
    # atrás, que es justo el modo de fallo que el punto 5 de la cabecera describe.
    try:
        regla = client.get_alarm_mute_rule(AlarmMuteRuleName=rule_name) or {}
        guardadas: set[str] = set(regla.get("MuteTargets", {}).get("AlarmNames", []))

        existentes: set[str] = set()
        descripcion = client.describe_alarms(AlarmNames=list(alarm_names)) or {}
        for alarma in descripcion.get("MetricAlarms", []):
            existentes.add(alarma["AlarmName"])
    except Exception:
        return _ack_a_ciegas(rule_name, alarm_names)

    silenciadas = {n for n in alarm_names if n in guardadas and n in existentes}
    faltantes = tuple(sorted(n for n in alarm_names if n not in silenciadas))
    return MuteAck(
        requested=len(alarm_names),
        silenced=len(silenciadas),
        missing_names=faltantes,
        rule_name=rule_name,
    )


def delete_mute(client: MuteClient, *, rule_name: str | None) -> None:
    """Cierre ANTICIPADO: borra la regla y desilencia en el acto.

    ``DeleteAlarmMuteRule``, literal en ``CLI_SERVICE_MODEL``: *"any alarms that
    are currently being muted by that rule are immediately unmuted. If those
    alarms are in an ALARM state, their configured actions will trigger. This
    operation is idempotent. If you delete a mute rule that does not exist, the
    operation succeeds without returning an error."*

    Tres cosas se apoyan en esa frase y solo en ella: que cerrar antes de tiempo
    hace que el correo pendiente SALGA en vez de perderse; que borrar una regla
    que quizá no existe —el caso del acuse NO verificado— es seguro; y que es la
    única vía con re-disparo documentado, o sea la que hay que preferir sobre
    dejar que la ventana expire sola (ver el agujero declarado en la cabecera).

    ``rule_name=None`` (ventana que no llegó a emitir regla porque no había ni
    una alarma que silenciar) es un no-op: no hay nada que borrar.

    **Aquí SÍ se cree al 200, al revés que en ``apply_mute``, y es a propósito.**
    El PUT acepta N nombres y su resultado es parcial por naturaleza (un nombre
    inexistente no muta nada), así que "200" y "cuántas quedaron mudas" son dos
    hechos distintos; el DELETE actúa sobre UN objeto y no tiene ``N/M`` que
    releer. Lo que esa asimetría deja sin cubrir —un 200 que no surtiera efecto—
    está declarado, con su forma de cierre y su gate, en
    ``tests/ops/test_muting.test_el_cierre_CONFIA_en_el_200_del_borrado...``.

    **Si esto levanta, la regla puede seguir viva y las alarmas mudas**, y quien
    llama no puede tragarse la excepción y declarar reabierta la vigilancia. Aquí
    no hay lado ambiguo que valga: la idempotencia hace que reintentar sea gratis,
    así que la respuesta correcta al fallo es no afirmar el cierre y volver a
    intentarlo. Ver ``routers/maintenance._reabrir_o_fallar``.
    """
    if not rule_name:
        return
    client.delete_alarm_mute_rule(AlarmMuteRuleName=rule_name)
