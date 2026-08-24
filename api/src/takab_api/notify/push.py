"""Push móvil vía SNS platform endpoints (T-2.04 · decisión T-2.00).

TRES clases JAMÁS mezcladas (spec móvil §6). Eran dos hasta que `T-2.147.a` añadió
``PANIC``; esta línea seguía diciendo "dos", que es la clase de desfase que hace que
alguien crea que ya las ha revisado todas:

- ``CRISIS`` — alerta activa / cambio de fase. iOS: sonido *critical* con
  ``interruption-level: time-sensitive`` como base — cuando Apple apruebe el
  entitlement (GATE-STORE) se sube a ``critical``; sin él, iOS degrada el flag
  en silencio y el sonido llega normal. Android: canal ``seismic_alert_v2``
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
        "channel_id": "seismic_alert_v2",
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
        "channel_id": "building_alarm",
    },
}


def build_push_payload(
    *,
    push_class: str,
    site_id: str,
    incident_id: str | None,
    phase: str,
) -> dict[str, str]:
    """Estructura ``MessageStructure=json`` de SNS: default + APNS(+SANDBOX) + GCM.

    Datos mínimos idénticos en todas las plataformas; el estilo de entrega
    (sonido crítico / canal Android) depende de la CLASE.
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
    style = _DELIVERY_STYLE[push_class]

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
    gcm = json.dumps({"notification": dict(text), "android": android, "data": data})

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
            try:
                arn = device.endpoint_arn
                if not arn:
                    arn = client.create_platform_endpoint(
                        PlatformApplicationArn=application, Token=device.token
                    )["EndpointArn"]
                    outcome.created_arns[device.push_token_id] = arn
                client.publish(TargetArn=arn, MessageStructure="json", Message=message)
                outcome.delivered += 1
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("EndpointDisabled", "InvalidParameter"):
                    # Token muerto/rotado: se revoca en DB; el dispositivo vivo
                    # re-registrará su token nuevo (upsert de /me/push-tokens).
                    outcome.disabled_ids.append(device.push_token_id)
                else:
                    outcome.errors.append(f"{device.push_token_id}: {code or exc}")
            except BotoCoreError as exc:
                outcome.errors.append(f"{device.push_token_id}: {exc}")
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
