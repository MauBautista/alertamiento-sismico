"""Plan PURO de la cascada de notificación (blueprint §5.6). Sin DB.

- Normal: cascada secuencial escalonada webhook→WhatsApp→SMS→email
  (``due_at = t0 + position·step``); con step 10 s el SMS sale a t0+20 y su
  SLA de entrega es ≤30 s (``deadline_at``).
- Crítico: ADEMÁS email ``parallel`` inmediato con deadline <10 s
  (interpretación ratificada plan maestro: secuencial puro haría el SLA
  imposible tras timeouts de los canales previos).
- Fail-open (``trigger='quorum'``: incidente sintético de sitio SIN ENLACE,
  T-1.19): TODOS los canales configurados en paralelo a t0 — se prefiere
  sobre-notificar a callar.

El ``target`` del job NUNCA lleva secretos (el HMAC del webhook se
re-resuelve del rule_set al despachar).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

# Orden fijo de la cascada (blueprint §5.6).
CASCADE_ORDER: tuple[str, ...] = ("webhook", "whatsapp", "sms", "email")


class _NotifyDefaults(Protocol):
    """Proveedor de defaults del plan (``Settings`` u otro stand-in)."""

    notify_step_s: float
    notify_sms_deadline_s: float
    notify_email_critical_deadline_s: float


@dataclass(frozen=True)
class NotifyParams:
    """Tiempos resueltos de la cascada."""

    step_s: float
    sms_deadline_s: float
    email_critical_deadline_s: float


@dataclass(frozen=True)
class JobSpec:
    """Job planificado, listo para persistir en ``notification_jobs``."""

    channel: str
    mode: str  # 'cascade' | 'parallel'
    position: int
    due_at: datetime
    deadline_at: datetime | None
    target: dict


def resolve_params(settings: _NotifyDefaults) -> NotifyParams:
    return NotifyParams(
        step_s=settings.notify_step_s,
        sms_deadline_s=settings.notify_sms_deadline_s,
        email_critical_deadline_s=settings.notify_email_critical_deadline_s,
    )


def plan_jobs(
    *,
    severity: str,
    trigger: str,
    opened_at: datetime,
    destinations: dict[str, dict],
    params: NotifyParams,
) -> list[JobSpec]:
    """Jobs a encolar para un incidente según severidad/disparo y destinos."""
    t0 = opened_at
    configured = [ch for ch in CASCADE_ORDER if ch in destinations]

    def _deadline(channel: str, mode: str) -> datetime | None:
        if channel == "sms":
            return t0 + timedelta(seconds=params.sms_deadline_s)
        if channel == "email" and mode == "parallel" and severity == "critical":
            return t0 + timedelta(seconds=params.email_critical_deadline_s)
        return None

    def _target(channel: str) -> dict:
        clean = dict(destinations[channel])
        clean.pop("secret", None)  # jamás persistir secretos en el job
        return clean

    # [T-2.04] La push móvil NO es un salto de la cascada (no es fallback: es el
    # despertador de la app) — va SIEMPRE en paralelo a t0, clase CRISIS. Es
    # best-effort: la vida la protege la sirena del edge (R5).
    push = (
        [JobSpec("push", "parallel", 0, t0, None, _target("push"))]
        if "push" in destinations
        else []
    )

    if trigger == "quorum":  # fail-open: sitio SIN ENLACE cubierto por la red
        return [
            JobSpec(ch, "parallel", pos, t0, _deadline(ch, "parallel"), _target(ch))
            for pos, ch in enumerate(configured)
        ] + push

    jobs = [
        JobSpec(
            ch,
            "cascade",
            pos,
            t0 + timedelta(seconds=params.step_s * pos),
            _deadline(ch, "cascade"),
            _target(ch),
        )
        for pos, ch in enumerate(configured)
    ]
    if severity == "critical" and "email" in destinations:
        jobs.append(
            JobSpec("email", "parallel", 0, t0, _deadline("email", "parallel"), _target("email"))
        )
    return jobs + push
