"""Plan PURO de la cascada de notificación (T-1.21 · B6). Sin DB.

Cascada secuencial webhook→WhatsApp→SMS(≤30 s)→email; crítico añade email
``parallel`` inmediato (interpretación ratificada: secuencial puro haría <10 s
imposible tras timeouts); fail-open (``trigger='quorum'``: sitio SIN ENLACE
cubierto por la red) dispara TODOS los canales configurados en paralelo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_api.notify.config import resolve_destinations
from takab_api.notify.plan import CASCADE_ORDER, NotifyParams, plan_jobs

T0 = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
PARAMS = NotifyParams(step_s=10.0, sms_deadline_s=30.0, email_critical_deadline_s=10.0)

DESTINATIONS = {
    "webhook": {"url": "https://soc.example.mx/hook"},
    "whatsapp": {"to": "+525511111111"},
    "sms": {"to": "+525522222222"},
    "email": {"to": ["ops@example.mx"]},
}


def _plan(severity: str = "warning", trigger: str = "local_threshold", dest: dict | None = None):
    return plan_jobs(
        severity=severity,
        trigger=trigger,
        opened_at=T0,
        destinations=DESTINATIONS if dest is None else dest,
        params=PARAMS,
    )


def _by(jobs, channel: str, mode: str):
    found = [j for j in jobs if j.channel == channel and j.mode == mode]
    assert len(found) == 1, f"esperaba 1 job {channel}/{mode}, hay {len(found)}"
    return found[0]


# ------------------------------------------------------------------- cascada


def test_normal_incident_plans_staggered_cascade() -> None:
    jobs = _plan()
    assert [j.channel for j in jobs] == list(CASCADE_ORDER)
    assert all(j.mode == "cascade" for j in jobs)
    for pos, j in enumerate(jobs):
        assert j.position == pos
        assert j.due_at == T0 + timedelta(seconds=10.0 * pos)


def test_sms_due_and_deadline_within_30s() -> None:
    sms = _by(_plan(), "sms", "cascade")
    assert sms.due_at <= T0 + timedelta(seconds=30)  # margen para entregar ≤30 s
    assert sms.deadline_at == T0 + timedelta(seconds=30)


def test_non_sms_cascade_has_no_deadline() -> None:
    jobs = _plan()
    for channel in ("webhook", "whatsapp", "email"):
        assert _by(jobs, channel, "cascade").deadline_at is None


def test_missing_channel_is_omitted_and_positions_compact() -> None:
    dest = {k: v for k, v in DESTINATIONS.items() if k != "whatsapp"}
    jobs = _plan(dest=dest)
    assert [j.channel for j in jobs] == ["webhook", "sms", "email"]
    assert [j.position for j in jobs] == [0, 1, 2]
    assert _by(jobs, "sms", "cascade").due_at == T0 + timedelta(seconds=10)


def test_empty_destinations_plan_nothing() -> None:
    assert _plan(dest={}) == []


# ------------------------------------------------------------ crítico <10 s


def test_critical_adds_parallel_email_at_t0() -> None:
    jobs = _plan(severity="critical")
    par = _by(jobs, "email", "parallel")
    assert par.due_at == T0
    assert par.deadline_at == T0 + timedelta(seconds=10)
    # La cascada completa sigue existiendo (email cascade además del parallel).
    assert _by(jobs, "email", "cascade").mode == "cascade"


def test_critical_without_email_configured_has_no_parallel() -> None:
    dest = {k: v for k, v in DESTINATIONS.items() if k != "email"}
    jobs = _plan(severity="critical", dest=dest)
    assert all(j.mode == "cascade" for j in jobs)


# ---------------------------------------------------------------- fail-open


def test_quorum_failopen_plans_all_parallel_at_t0() -> None:
    jobs = _plan(trigger="quorum")
    assert {j.channel for j in jobs} == set(CASCADE_ORDER)
    assert all(j.mode == "parallel" and j.due_at == T0 for j in jobs)


def test_quorum_failopen_keeps_sms_deadline() -> None:
    sms = _by(_plan(trigger="quorum"), "sms", "parallel")
    assert sms.deadline_at == T0 + timedelta(seconds=30)


def test_quorum_critical_email_keeps_10s_deadline() -> None:
    email = _by(_plan(severity="critical", trigger="quorum"), "email", "parallel")
    assert email.deadline_at == T0 + timedelta(seconds=10)


# ------------------------------------------------------- target sin secretos


def test_webhook_target_never_carries_secret() -> None:
    dest = {"webhook": {"url": "https://soc.example.mx/hook", "secret": "s3cr3t"}}
    hook = _by(_plan(dest=dest), "webhook", "cascade")
    assert hook.target == {"url": "https://soc.example.mx/hook"}


# -------------------------------------------------------------- destinations


def test_resolve_destinations_from_ruleset_config() -> None:
    cfg = {"notifications": DESTINATIONS}
    assert resolve_destinations(cfg) == DESTINATIONS


def test_resolve_destinations_missing_or_invalid() -> None:
    assert resolve_destinations(None) == {}
    assert resolve_destinations({}) == {}
    cfg = {
        "notifications": {
            "webhook": {"secret": "x"},  # sin url → inválido
            "whatsapp": {"to": ""},  # vacío → inválido
            "sms": "no-dict",  # tipo inválido
            "email": {"to": []},  # sin destinatarios
        }
    }
    assert resolve_destinations(cfg) == {}


def test_resolve_destinations_email_string_becomes_list() -> None:
    cfg = {"notifications": {"email": {"to": "ops@example.mx"}}}
    assert resolve_destinations(cfg) == {"email": {"to": ["ops@example.mx"]}}
