"""Push móvil vía SNS platform endpoints (T-2.04 · decisión T-2.00).

TRES clases JAMÁS mezcladas (spec móvil §6). Eran dos hasta que `T-2.147.a` añadió
``PANIC``; esta línea seguía diciendo "dos", que es la clase de desfase que hace que
alguien crea que ya las ha revisado todas:

- ``CRISIS`` — alerta activa / cambio de fase. iOS: sonido *critical* con
  ``interruption-level: time-sensitive`` como base — cuando Apple apruebe el
  entitlement (GATE-STORE) se sube a ``critical``; sin él, iOS degrada el flag
  en silencio y el sonido llega normal. Android: canal ``seismic_alert_v3``
  (IMPORTANCE_MAX + bypass DND, lo crea la app en onboarding).
- ``PANIC`` — activación manual del inmueble por quórum de pánico (`D-05`/`D-11`).
  Canal propio ``building_alarm`` (IMPORTANCE_MAX + bypass DND: despierta como una
  crisis) con el sonido del SISTEMA, nunca el sísmico: no es un sismo.
- ``OPS`` — dictamen recibido, sync, recordatorios. Prioridad normal.

El payload es MÍNIMO y sin datos sensibles (aparece en lockscreen): tipo,
clase, ids y fase. El contenido real se obtiene por API al abrir la app —
la push es DESPERTADOR, no fuente de verdad (spec §4.1). Y es best-effort:
la protección de vida es la sirena del edge (R5), por eso vive en la cascada
FAIL-OPEN y jamás en el camino de actuación.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("takab_api.notify")

PUSH_CLASS_CRISIS = "CRISIS"
PUSH_CLASS_OPS = "OPS"
#: [T-2.147.a] Activación manual del inmueble (quórum de pánico). Alta prioridad
#: —tiene que despertar a la brigada— y **NO sísmica**: canal, sonido y texto
#: propios. Las dos clases anteriores fallaban por extremos opuestos: `CRISIS`
#: presta el tono del SASMEX a algo que SASMEX no dijo (el defecto de T-2.104), y
#: `OPS` va en prioridad normal, que de madrugada no despierta a nadie.
PUSH_CLASS_PANIC = "PANIC"
#: [T-9.11 · D-39] Movimiento de UN SOLO inmueble en DISPARO, sin SASMEX ni cuórum.
#: Solo a la brigada (`movement_alert` en la matriz). Despierta —prioridad alta, salta
#: el No Molestar en Android por su canal— pero NO es la alerta sísmica: ni el tono ni
#: el texto de CRISIS. Suena la VOZ «Se detectó un movimiento en el inmueble.
#: Verifique.» (`shared/audio/MANIFEST.json`), para que quien la oye sepa qué hacer.
PUSH_CLASS_MOVEMENT = "MOVEMENT"
#: [T-9.33 · D-43] La regla ``dictamen-v2`` emitió un AMARILLO sin firmar: se pide a
#: quien tiene ``confirm_dictamen`` (brigada, inspector, administración) que revise y
#: confirme. NO despierta: prioridad normal, canal ``ops`` y sonido por defecto — es
#: trabajo posterior a la sacudida, no una alarma. Clase propia (y no ``OPS``) porque
#: la app abre OTRA pantalla y porque ``OPS`` va a TODO el inmueble.
PUSH_CLASS_DICTAMEN_CONFIRM = "DICTAMEN_CONFIRM"

# Texto visible FIJO y genérico (lockscreen): jamás nombres de sitio ni datos.
_ALERT_TEXT = {
    PUSH_CLASS_CRISIS: {
        "title": "ALERTA SÍSMICA",
        "body": "Abra la app y siga su instrucción.",
    },
    PUSH_CLASS_OPS: {
        "title": "TAKAB Ailert",
        "body": "Nueva notificación operativa.",
    },
    PUSH_CLASS_PANIC: {
        "title": "ALARMA DEL INMUEBLE",
        "body": "Activación manual. Abra la app.",
    },
    PUSH_CLASS_MOVEMENT: {
        "title": "MOVIMIENTO EN EL INMUEBLE",
        "body": "Se detectó un movimiento. Verifique el inmueble.",
    },
    PUSH_CLASS_DICTAMEN_CONFIRM: {
        "title": "DICTAMEN POR CONFIRMAR",
        "body": "Revise el inmueble y confirme el dictamen en la app.",
    },
}

#: Estilo de entrega POR CLASE, en una tabla y no en ternarios repartidos.
#:
#: Hasta T-2.147.a esto eran tres `if push_class == PUSH_CLASS_CRISIS` en sitios
#: distintos del constructor, y una clase nueva tenía que acertar los tres para
#: no heredar el estilo de `OPS` por omisión. La forma de fallar era silenciosa y
#: en la dirección mala: un push de emergencia entregado como una notificación
#: operativa. Aquí una clase nueva **declara su estilo o no existe**.
#:
#: `sound` es el campo que separa el sismo del resto: el `critical` de Apple se
#: solicitó para alertamiento sísmico (GATE-STORE) y gastarlo en otra cosa es la
#: clase de uso que hace que Apple lo revoque.
#:
#: [T-9.70 · D-50] La CRISIS que AUTORIZA evacuar (SASMEX o cuórum de red) suena con
#: el sonido OFICIAL del SASMEX, decidido por Mauricio el 2026-10-01. No es una clase
#: nueva —mismos textos, misma fase— sino otro ESTILO de la misma: en Android el
#: sonido lo decide el canal, que es inmutable, así que el oficial va por uno propio.
#: iOS sigue con el tono de TAKAB (≤ 30 s por notificación; APNs aún no vive).
CANAL_TONO_OFICIAL = "alerta_oficial_v1"
ESTILO_CRISIS_TONO_OFICIAL = "CRISIS_TONO_OFICIAL"

_DELIVERY_STYLE = {
    PUSH_CLASS_CRISIS: {
        # Base honesta pre-entitlement: time-sensitive suena aun en foco/atención;
        # el dict `critical` queda listo para cuando Apple apruebe (GATE-STORE).
        "interruption_level": "time-sensitive",
        # [D-19] El tono es PROPIO de TAKAB, no el oficial del SASMEX, y es el mismo
        # que sale por el altavoz del gabinete. Hasta el 2026-08-22 esto nombraba un
        # `seismic_alert.caf` que NO ESTABA EN EL REPO: iOS caía al sonido por
        # defecto en silencio, o sea que el sistema afirmaba un sonido crítico que
        # no podía sonar. El fichero viaja en el bundle por el `sounds` de
        # `mobile/app.json`, y `tests/notify/test_censo_canales_y_sonidos.py` es lo
        # que impide que vuelvan a separarse.
        "sound": {"critical": 1, "name": "alerta_sismica.wav", "volume": 1.0},
        "android_priority": "high",
        # El `_v2` viaja con el de la app y NO es cosmético: el sonido de un canal
        # Android es inmutable tras crearlo, así que estrenar tono exige id nuevo.
        # Ver el comentario largo en `mobile/src/services/push.ts`.
        # [T-9.12] `_v3`: el MISMO tono con uso de audio ALARMA. Medido en el Pixel el
        # 2026-09-27: con «No molestar» en prioridad, la CRISIS por `_v2` llegó y no
        # sonó ni vibró hasta encender la pantalla; `bypassDnd` no hace nada sin el
        # acceso que el usuario concede a mano. El uso ALARMA sí pasa ese modo.
        "channel_id": "seismic_alert_v3",
    },
    ESTILO_CRISIS_TONO_OFICIAL: {
        "interruption_level": "time-sensitive",
        "sound": {"critical": 1, "name": "alerta_sismica.wav", "volume": 1.0},
        "android_priority": "high",
        "channel_id": CANAL_TONO_OFICIAL,
    },
    PUSH_CLASS_OPS: {
        "interruption_level": "active",
        "sound": "default",
        "android_priority": "normal",
        "channel_id": "ops",
    },
    PUSH_CLASS_PANIC: {
        # Despierta como una crisis…
        "interruption_level": "time-sensitive",
        "android_priority": "high",
        # …y NO suena como una: canal propio y el sonido del sistema, nunca el
        # tono del SASMEX ni el sonido crítico.
        "sound": "default",
        # [T-9.12] `_v2`: uso de audio ALARMA, que pasa «No molestar» (ver
        # `mobile/src/services/push.ts::audioDeAlarma`).
        "channel_id": "building_alarm_v2",
    },
    PUSH_CLASS_MOVEMENT: {
        # Despierta a la brigada de madrugada: alta prioridad y time-sensitive…
        "interruption_level": "time-sensitive",
        "android_priority": "high",
        # …con SU voz, nunca el tono del SASMEX ni el sonido crítico de Apple (que se
        # pidió para alertamiento sísmico). El canal lleva versión por la misma razón
        # que `seismic_alert_v3`: el sonido de un canal Android es inmutable.
        "sound": "movimiento_inmueble.wav",
        "channel_id": "building_movement_v2",
    },
    PUSH_CLASS_DICTAMEN_CONFIRM: {
        # Trabajo de revisión, no alarma: el estilo exacto de OPS.
        "interruption_level": "active",
        "sound": "default",
        "android_priority": "normal",
        "channel_id": "ops",
    },
}


#: Clave con la que SNS acepta un mensaje de FCM v1 SIN convertirlo (ver el
#: comentario en `build_push_payload`, que es donde está medido por qué importa).
FCM_V1_KEY = "fcmV1Message"


def build_push_payload(
    *,
    push_class: str,
    site_id: str,
    incident_id: str | None,
    phase: str,
    tono_oficial: bool = False,
) -> dict[str, str]:
    """Estructura ``MessageStructure=json`` de SNS: default + APNS(+SANDBOX) + GCM.

    Datos mínimos idénticos en todas las plataformas; el estilo de entrega
    (sonido crítico / canal Android) depende de la CLASE — y, en la CRISIS, de
    ``tono_oficial`` (T-9.70 · D-50): la que autoriza evacuar suena con el oficial.
    """
    if push_class not in _ALERT_TEXT:
        raise ValueError(f"clase de push desconocida: {push_class!r}")
    data = {
        "type": "incident",
        "class": push_class,
        "site_id": site_id,
        "incident_id": incident_id or "",
        "phase": phase,
    }
    text = _ALERT_TEXT[push_class]
    estilo = (
        ESTILO_CRISIS_TONO_OFICIAL
        if push_class == PUSH_CLASS_CRISIS and tono_oficial
        else push_class
    )
    style = _DELIVERY_STYLE[estilo]

    aps: dict = {
        "alert": dict(text),
        "interruption-level": style["interruption_level"],
        "sound": style["sound"],
    }
    apns = json.dumps({"aps": aps, **data})

    android: dict = {
        "priority": style["android_priority"],
        "notification": {"channel_id": style["channel_id"], **text},
    }
    # [T-7.03] La forma v1 EXPLÍCITA, y no la heredada.
    #
    # Medido contra el Pixel el 2026-09-12, con el primer push real del producto:
    # mandando `{"notification":…, "android":…, "data":…}` —la forma heredada—
    # SNS la convierte a FCM v1 y por el camino DESCARTA el bloque `android`
    # entero, que es donde viven las dos cosas que hacen de esto una alerta y no
    # un aviso: el canal (`seismic_alert_v3`, el único que salta el No Molestar y
    # suena con el tono de TAKAB) y la prioridad alta (la que entrega en Doze).
    # El aviso llegó, se pintó… en `fcm_fallback_notification_channel` y en
    # prioridad normal. Verde en el servidor, verde en el teléfono, y sin alerta.
    #
    # Envolverlo en `fcmV1Message` le entrega a FCM el mensaje v1 tal cual, sin
    # conversión. Comprobado en el mismo teléfono: con esta forma el aviso cae en
    # `seismic_alert_v3`; con la heredada, en el canal de reserva.
    gcm = json.dumps(
        {FCM_V1_KEY: {"message": {"notification": dict(text), "android": android, "data": data}}}
    )

    return {
        "default": json.dumps(data),
        "APNS": apns,
        "APNS_SANDBOX": apns,
        "GCM": gcm,
    }


@dataclass(frozen=True)
class PushDevice:
    """Dispositivo destino (fila de ``push_tokens`` resuelta al despachar)."""

    push_token_id: str
    token: str
    platform: str  # 'ios' | 'android'
    endpoint_arn: str | None


@dataclass
class PushOutcome:
    """Resultado por lote: el orquestador persiste ARNs nuevos y revoca muertos."""

    delivered: int = 0
    created_arns: dict[str, str] = field(default_factory=dict)  # push_token_id → arn
    disabled_ids: list[str] = field(default_factory=list)  # endpoints muertos
    errors: list[str] = field(default_factory=list)


class SnsPushProvider:
    """Entrega real vía SNS. Un endpoint por dispositivo (cacheado en DB);
    un endpoint deshabilitado (token rotado / app desinstalada) se reporta
    para REVOCAR el token — limpieza honesta, sin martillar muertos."""

    channel = "push"
    simulated = False

    def __init__(self, *, region: str, apns_application_arn: str, fcm_application_arn: str) -> None:
        self._region = region
        self._apns_arn = apns_application_arn
        self._fcm_arn = fcm_application_arn

    def _client(self):
        return boto3.client("sns", region_name=self._region)

    def _application_for(self, platform: str) -> str:
        return self._apns_arn if platform == "ios" else self._fcm_arn

    def deliver(self, devices: list[PushDevice], payload: dict[str, str]) -> PushOutcome:
        outcome = PushOutcome()
        client = self._client()
        message = json.dumps(payload)
        for device in devices:
            application = self._application_for(device.platform)
            if not application:
                outcome.errors.append(f"{device.platform}: platform application no configurada")
                continue
            # [T-7.03] Qué llamada se está haciendo, para poder DECIRLO si rebota:
            # crear el endpoint del dispositivo y publicar en él son permisos
            # distintos sobre recursos distintos (`sns:CreatePlatformEndpoint`
            # sobre la platform application; `sns:Publish` sobre el endpoint), y
            # SNS devuelve `AuthorizationError` para los dos.
            operacion = "create_platform_endpoint"
            try:
                arn = device.endpoint_arn
                if not arn:
                    arn = client.create_platform_endpoint(
                        PlatformApplicationArn=application, Token=device.token
                    )["EndpointArn"]
                    outcome.created_arns[device.push_token_id] = arn
                operacion = "publish"
                client.publish(TargetArn=arn, MessageStructure="json", Message=message)
                outcome.delivered += 1
            except ClientError as exc:
                error = exc.response.get("Error", {})
                code = error.get("Code", "")
                if code in ("EndpointDisabled", "InvalidParameter"):
                    # Token muerto/rotado: se revoca en DB; el dispositivo vivo
                    # re-registrará su token nuevo (upsert de /me/push-tokens).
                    outcome.disabled_ids.append(device.push_token_id)
                else:
                    # El código a secas no basta para arreglar nada: el mensaje
                    # de AWS es el que nombra al principal y a la acción.
                    detalle = error.get("Message") or ""
                    outcome.errors.append(
                        f"{device.push_token_id}: {operacion}: {code or exc}"
                        + (f": {detalle}" if detalle else "")
                    )
            except BotoCoreError as exc:
                outcome.errors.append(f"{device.push_token_id}: {operacion}: {exc}")
        return outcome


class SimulatedPushProvider:
    """Sin platform applications configuradas: NADA despierta un teléfono.

    [T-2.75] Se declara ``simulated`` y el orquestador ni siquiera llega a
    llamar ``deliver()``: el job queda ``simulated``, jamás ``sent``.

    Y si llegara —porque alguien mueva ese guard, o porque otro llamador use
    ``deliver()`` directamente—, lo que devuelve es la verdad: ``delivered=0``.
    Devolvía ``delivered=len(devices)``, contando como entrega el simple hecho
    de tener dispositivos registrados, y el tablero decía que sonaron. El guard
    del orquestador es un cortafuegos; esto es el contrato (regla de oro 7).
    """

    channel = "push"
    simulated = True
    hint = "TAKAB_API_PUSH_APNS/FCM_APPLICATION_ARN"

    def __init__(self) -> None:
        self.delivered: list[tuple[list[PushDevice], dict]] = []

    def deliver(self, devices: list[PushDevice], payload: dict[str, str]) -> PushOutcome:
        logger.warning(
            "push SIMULADO a %d dispositivo(s) — sin %s ningún teléfono recibe nada.",
            len(devices),
            self.hint,
        )
        self.delivered.append((devices, payload))
        # Se registra el intento (arriba) pero NO se cuenta ni una entrega: sin
        # platform application no salió un solo push.
        return PushOutcome(delivered=0)


def build_push_provider(settings) -> SnsPushProvider | SimulatedPushProvider:
    """SNS real si hay al menos una platform application; si no, simulado.

    El grito de arranque NO va aquí: lo emite ``warn_simulated_channels`` sobre
    el registro completo, para que ningún canal simulado dependa de que su
    constructor se haya acordado de avisar.
    """
    if settings.push_apns_application_arn or settings.push_fcm_application_arn:
        return SnsPushProvider(
            region=settings.aws_region,
            apns_application_arn=settings.push_apns_application_arn,
            fcm_application_arn=settings.push_fcm_application_arn,
        )
    return SimulatedPushProvider()
