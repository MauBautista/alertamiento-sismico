"""T-2.78.a · Contrato de la cadena de operación (aviso → acuse → silencio).

Un solo recurso de lectura, y es interno de TAKAB: la cadena `CloudWatch → SNS →
on-call` es de la plataforma, no de un cliente. `outcome` viene CALCULADO de la
vista `v_ops_alert_chain` y no es un campo que nadie pueda poner en verde: sin
`acked_at` no existe el valor `acusado`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OpsAlertNoticeOut(BaseModel):
    """Un aviso de operación con su desenlace."""

    notice_id: str
    alarm_name: str | None = None
    alarm_state: str | None = None
    subject: str | None = None
    state_reason: str | None = None
    #: Instante que SNS puso en el sobre (cuándo salió del topic).
    published_at: datetime | None = None
    #: Instante en que ESTE servidor lo recibió. Es el t2 de máquina del runbook:
    #: no depende del buzón de nadie.
    received_at: datetime
    requires_ack: bool
    ack_deadline_at: datetime | None = None
    acked_at: datetime | None = None
    acked_by: str | None = None
    #: Cuándo el silencio dejó de ser espera y pasó a fallo declarado.
    unacked_at: datetime | None = None
    #: `no_requiere_acuse` · `esperando_acuse` · `sin_acuse` · `acusado` ·
    #: `acusado_tarde`. Derivado de los instantes, nunca almacenado.
    outcome: str
    #: Segundos de `received_at` a `acked_at`. **El número que la ficha pedía
    #: poder consultar** en vez de reconstruirlo de cabeceras de correo.
    ack_latency_s: float | None = None
    #: Lo mismo, medido desde que SNS lo publicó.
    ack_latency_publicado_s: float | None = None


class OpsAlertChain(BaseModel):
    """Los avisos más recientes, del más nuevo al más viejo."""

    items: list[OpsAlertNoticeOut] = Field(default_factory=list)
