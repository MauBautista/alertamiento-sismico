"""Push móvil vía SNS platform endpoints (T-2.04 · decisión T-2.00).

Dos clases JAMÁS mezcladas (spec móvil §6):

- ``CRISIS`` — alerta activa / cambio de fase. iOS: sonido *critical* con
  ``interruption-level: time-sensitive`` como base — cuando Apple apruebe el
  entitlement (GATE-STORE) se sube a ``critical``; sin él, iOS degrada el flag
  en silencio y el sonido llega normal. Android: canal ``seismic_alert``
  (IMPORTANCE_HIGH + bypass DND, lo crea la app en onboarding).
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

    aps: dict = {"alert": dict(text)}
    if push_class == PUSH_CLASS_CRISIS:
        # Base honesta pre-entitlement: time-sensitive suena aun en foco/atención;
        # el dict `critical` queda listo para cuando Apple apruebe (GATE-STORE).
        aps["interruption-level"] = "time-sensitive"
        aps["sound"] = {"critical": 1, "name": "seismic_alert.caf", "volume": 1.0}
    else:
        aps["interruption-level"] = "active"
        aps["sound"] = "default"
    apns = json.dumps({"aps": aps, **data})

    android: dict = {
        "priority": "high" if push_class == PUSH_CLASS_CRISIS else "normal",
        "notification": {
            "channel_id": "seismic_alert" if push_class == PUSH_CLASS_CRISIS else "ops",
            **text,
        },
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
    """Sin platform applications configuradas: registra y GRITA (patrón T-1.62 —
    marcar 'sent' en silencio sería mentir que los teléfonos sonaron)."""

    channel = "push"

    def __init__(self) -> None:
        self.delivered: list[tuple[list[PushDevice], dict]] = []

    def deliver(self, devices: list[PushDevice], payload: dict[str, str]) -> PushOutcome:
        logger.warning(
            "push SIMULADO a %d dispositivo(s) — sin TAKAB_API_PUSH_*_APPLICATION_ARN "
            "ningún teléfono recibe nada. En la nube esto es un fallo.",
            len(devices),
        )
        self.delivered.append((devices, payload))
        return PushOutcome(delivered=len(devices))


def build_push_provider(settings) -> SnsPushProvider | SimulatedPushProvider:
    """SNS real si hay al menos una platform application; si no, simulado ruidoso."""
    if settings.push_apns_application_arn or settings.push_fcm_application_arn:
        return SnsPushProvider(
            region=settings.aws_region,
            apns_application_arn=settings.push_apns_application_arn,
            fcm_application_arn=settings.push_fcm_application_arn,
        )
    logger.warning(
        "TAKAB_API_PUSH_APNS/FCM_APPLICATION_ARN vacíos: canal push SIMULADO — "
        "los jobs se marcarán 'sent' sin despertar teléfono alguno."
    )
    return SimulatedPushProvider()
