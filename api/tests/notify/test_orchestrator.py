"""Orquestador de notificaciones contra Postgres real (T-1.21 · B6).

Patrón de ``tests/dictamen/test_service.py``: siembra directa bajo ``SET ROLE
takab_ingest``, tenant fresco, BASE en 2033 (aísla el barrido cross-tenant de
otros archivos) y limpieza con ``session_replication_role`` (incident_actions
es append-only). Providers = fakes con toggle de fallo; reloj inyectado (SLA).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.providers import NotifyError
from takab_api.settings import Settings

BASE = datetime(2033, 4, 20, 12, 0, 0, tzinfo=UTC)
SRC_LON, SRC_LAT = -100.5, 12.0  # aislado (Pacífico), lejos de otras fixtures

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"

NOTIF_CONFIG = {
    "notifications": {
        "webhook": {"url": "https://soc.example.mx/hook", "secret": "s3cr3t"},
        "whatsapp": {"to": "+525511111111"},
        "sms": {"to": "+525522222222"},
        "email": {"to": ["ops@example.mx"]},
    }
}


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[dict, dict]] = []

    def send(self, target: dict, message: dict) -> None:
        if self.fail:
            raise NotifyError("fallo simulado")
        self.sent.append((target, message))


def _providers(**fail: bool) -> dict[str, _FakeProvider]:
    return {
        ch: _FakeProvider(fail=fail.get(ch, False))
        for ch in ("webhook", "whatsapp", "sms", "email")
    }


class _Scenario:
    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant

    def seed_config(self, config: dict | None = None) -> None:
        import json

        self.conn.execute(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
            "is_active, config) VALUES (%s,'tenant',%s,1,true,%s::jsonb)",
            (self.tenant, self.tenant, json.dumps(config or NOTIF_CONFIG)),
        )
        self.conn.commit()

    def seed_incident(
        self,
        *,
        severity: str = "warning",
        trigger: str = "local_threshold",
        opened_at: datetime | None = None,
    ) -> str:
        site, incident = str(uuid.uuid4()), str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'Sitio N', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
            (site, self.tenant, f"N-{site[:8]}", SRC_LON, SRC_LAT),
        )
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (incident, str(uuid.uuid4()), self.tenant, site, opened_at or BASE, severity, trigger),
        )
        self.conn.commit()
        return incident

    def jobs(self, incident_id: str) -> list[dict]:
        return self.conn.execute(
            "SELECT channel, mode, position, status, due_at, deadline_at, sent_at, "
            "target, error FROM notification_jobs WHERE incident_id = %s "
            "ORDER BY mode, position, channel",
            (incident_id,),
        ).fetchall()

    def job(self, incident_id: str, channel: str, mode: str = "cascade") -> dict:
        rows = [j for j in self.jobs(incident_id) if j["channel"] == channel and j["mode"] == mode]
        assert len(rows) == 1, f"esperaba 1 job {channel}/{mode}, hay {len(rows)}"
        return rows[0]

    def notify_actions(self, incident_id: str) -> list[dict]:
        return self.conn.execute(
            "SELECT payload FROM incident_actions "
            "WHERE incident_id = %s AND kind = 'notify_sent' ORDER BY ts",
            (incident_id,),
        ).fetchall()


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Notify Test')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield _Scenario(conn, tenant)
    finally:
        _cleanup(conn, tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute("DELETE FROM notification_jobs WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _run(scenario: _Scenario, providers: dict, *, now: datetime) -> None:
    run_notify_pass(scenario.conn, Settings(), providers, now=now)


# ------------------------------------------------------------------- enqueue


def test_enqueue_normal_cascade(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True, sms=True, email=True)  # nada sale
    _run(scenario, providers, now=BASE)

    jobs = scenario.jobs(iid)
    cascade = [j for j in jobs if j["mode"] == "cascade"]
    assert [j["channel"] for j in cascade] == ["webhook", "whatsapp", "sms", "email"]
    assert [j["position"] for j in cascade] == [0, 1, 2, 3]
    assert not [j for j in jobs if j["mode"] == "parallel"]
    assert scenario.job(iid, "sms")["deadline_at"] == BASE + timedelta(seconds=30)
    # Con todos los canales caídos, la cascada INTENTÓ todos (nunca calla).
    assert all(j["status"] == "failed" for j in cascade)


def test_enqueue_is_idempotent(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident()
    failing = _providers(webhook=True, whatsapp=True, sms=True, email=True)
    _run(scenario, failing, now=BASE)
    first = [(j["channel"], j["mode"], j["status"]) for j in scenario.jobs(iid)]
    _run(scenario, failing, now=BASE)
    assert [(j["channel"], j["mode"], j["status"]) for j in scenario.jobs(iid)] == first


def test_enqueue_without_destinations_creates_nothing(scenario: _Scenario) -> None:
    iid = scenario.seed_incident()  # tenant SIN rule_set de notificaciones
    _run(scenario, _providers(), now=BASE)
    assert scenario.jobs(iid) == []


def test_webhook_job_target_has_no_secret(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident()
    _run(scenario, _providers(webhook=True, whatsapp=True, sms=True, email=True), now=BASE)
    assert scenario.job(iid, "webhook")["target"] == {"url": "https://soc.example.mx/hook"}


# ------------------------------------------------------------------ cascada


def test_cascade_success_skips_the_rest(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers()
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook")["status"] == "sent"
    for ch in ("whatsapp", "sms", "email"):
        assert scenario.job(iid, ch)["status"] == "skipped"
    # El schedule de los skipped queda intacto (nadie los adelantó).
    assert scenario.job(iid, "sms")["due_at"] == BASE + timedelta(seconds=20)
    assert len(providers["webhook"].sent) == 1
    # El webhook recibe el secret re-resuelto del rule_set (nunca persistido).
    assert providers["webhook"].sent[0][0] == {
        "url": "https://soc.example.mx/hook",
        "secret": "s3cr3t",
    }
    acts = scenario.notify_actions(iid)
    assert len(acts) == 1
    assert acts[0]["payload"]["channel"] == "webhook"
    assert acts[0]["payload"]["deadline_met"] is True


def test_cascade_failure_escalates_within_pass(scenario: _Scenario) -> None:
    """webhook y whatsapp caen → el SMS se adelanta y sale en el MISMO pass a
    t0 (SLA ≤30 s cumplido de sobra); email queda skipped."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True)
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook")["status"] == "failed"
    assert scenario.job(iid, "whatsapp")["status"] == "failed"
    sms = scenario.job(iid, "sms")
    assert sms["status"] == "sent"
    assert sms["sent_at"] == BASE  # adelantado: no esperó su due_at de t0+20
    assert sms["sent_at"] <= sms["deadline_at"]
    assert scenario.job(iid, "email")["status"] == "skipped"
    payloads = [a["payload"] for a in scenario.notify_actions(iid)]
    assert [p["channel"] for p in payloads] == ["sms"]
    assert payloads[0]["deadline_met"] is True


def test_failure_advances_only_next_channel(scenario: _Scenario) -> None:
    """El fallo adelanta SOLO el siguiente canal (whatsapp), que al triunfar
    marca skipped el resto — no se dispara la cascada entera de golpe."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True)
    _run(scenario, providers, now=BASE)  # webhook falla, whatsapp adelantado y sale

    assert scenario.job(iid, "whatsapp")["status"] == "sent"
    assert scenario.job(iid, "sms")["status"] == "skipped"


# ------------------------------------------------------------ crítico <10 s


def test_critical_email_parallel_sent_first_pass(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident(severity="critical")
    providers = _providers()
    _run(scenario, providers, now=BASE)

    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "sent"
    assert par["sent_at"] == BASE
    assert par["deadline_at"] == BASE + timedelta(seconds=10)
    assert par["sent_at"] <= par["deadline_at"]  # <10 s
    # La cascada normal también corrió (webhook sent, resto skipped).
    assert scenario.job(iid, "webhook")["status"] == "sent"


# ---------------------------------------------------------------- fail-open


def test_failopen_quorum_fires_all_parallel_first_pass(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident(trigger="quorum")
    providers = _providers()
    _run(scenario, providers, now=BASE)

    jobs = scenario.jobs(iid)
    assert all(j["mode"] == "parallel" for j in jobs)
    assert {j["channel"] for j in jobs} == {"webhook", "whatsapp", "sms", "email"}
    assert all(j["status"] == "sent" and j["sent_at"] == BASE for j in jobs)
    assert len(scenario.notify_actions(iid)) == 4


def test_failopen_one_channel_down_does_not_block_others(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident(trigger="quorum")
    providers = _providers(webhook=True)
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook", mode="parallel")["status"] == "failed"
    for ch in ("whatsapp", "sms", "email"):
        assert scenario.job(iid, ch, mode="parallel")["status"] == "sent"


# ------------------------------------------------------------- idempotencia


def test_rerun_after_send_does_not_resend(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers()
    _run(scenario, providers, now=BASE)
    _run(scenario, providers, now=BASE + timedelta(seconds=60))

    assert len(providers["webhook"].sent) == 1
    assert len(scenario.notify_actions(iid)) == 1


# --- T-1.61 · Notificación al inspector en dictamen_request ---------------------

INSPECTOR_CONFIG = {
    "notifications": {
        **NOTIF_CONFIG["notifications"],
        "inspector_emails": ["inspector@example.mx", "perito@example.mx"],
    }
}


def _seed_action(
    scenario: _Scenario,
    incident_id: str,
    *,
    ts: datetime,
    requested_by: str = "op-ana",
    note: str | None = "urge dictamen",
) -> str:
    import json as _json

    action = str(uuid.uuid4())
    scenario.conn.execute(
        "INSERT INTO incident_actions (action_id, incident_id, tenant_id, ts, kind, "
        "actor, payload) VALUES (%s,%s,%s,%s,'dictamen_request',%s,%s::jsonb)",
        (
            action,
            incident_id,
            scenario.tenant,
            ts,
            f"user:{requested_by}",
            _json.dumps({"requested_by": requested_by, "note": note}),
        ),
    )
    scenario.conn.commit()
    return action


def _seed_signed_dictamen(scenario: _Scenario, incident_id: str, *, created_at: datetime) -> None:
    scenario.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, created_at) "
        "VALUES (%s,%s,'inhabit_monitor','{}'::jsonb,%s,%s)",
        (scenario.tenant, incident_id, str(uuid.uuid4()), created_at),
    )
    scenario.conn.commit()


def _action_jobs(scenario: _Scenario, action_id: str) -> list[dict]:
    return scenario.conn.execute(
        "SELECT channel, mode, status, target FROM notification_jobs WHERE action_id = %s",
        (action_id,),
    ).fetchall()


def _old_incident(scenario: _Scenario) -> str:
    """Incidente FUERA del lookback: su cascada no participa (aísla la acción)."""
    return scenario.seed_incident(opened_at=BASE - timedelta(days=2))


def test_dictamen_request_envia_email_al_inspector_con_link(scenario: _Scenario) -> None:
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = _old_incident(scenario)
    action = _seed_action(scenario, incident, ts=BASE - timedelta(seconds=5))
    providers = _providers()
    run_notify_pass(
        scenario.conn,
        Settings(notify_web_base_url="https://soc.example.mx/"),
        providers,
        now=BASE,
    )
    jobs = _action_jobs(scenario, action)
    assert len(jobs) == 1 and jobs[0]["status"] == "sent"
    assert jobs[0]["target"]["to"] == ["inspector@example.mx", "perito@example.mx"]
    assert len(providers["email"].sent) == 1
    _target, message = providers["email"].sent[0]
    assert message["kind"] == "dictamen_request"
    assert "Solicitud de dictamen" in message["headline"]
    assert message["requested_by"] == "op-ana"
    assert message["note"] == "urge dictamen"
    assert message["link"] == f"https://soc.example.mx/triage?incident={incident}"


def test_re_run_no_duplica_el_correo(scenario: _Scenario) -> None:
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = _old_incident(scenario)
    action = _seed_action(scenario, incident, ts=BASE - timedelta(seconds=5))
    providers = _providers()
    _run(scenario, providers, now=BASE)
    _run(scenario, providers, now=BASE + timedelta(seconds=30))
    assert len(_action_jobs(scenario, action)) == 1
    assert len(providers["email"].sent) == 1


def test_solicitud_ya_firmada_no_notifica(scenario: _Scenario) -> None:
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = _old_incident(scenario)
    action = _seed_action(scenario, incident, ts=BASE - timedelta(minutes=10))
    _seed_signed_dictamen(scenario, incident, created_at=BASE - timedelta(minutes=5))
    providers = _providers()
    _run(scenario, providers, now=BASE)
    assert _action_jobs(scenario, action) == []
    assert providers["email"].sent == []


def test_sin_inspector_emails_se_omite_con_gracia(scenario: _Scenario) -> None:
    scenario.seed_config(NOTIF_CONFIG)  # sin inspector_emails
    incident = _old_incident(scenario)
    action = _seed_action(scenario, incident, ts=BASE - timedelta(seconds=5))
    providers = _providers()
    _run(scenario, providers, now=BASE)
    assert _action_jobs(scenario, action) == []
    assert providers["email"].sent == []


def test_convive_con_el_email_del_incidente_en_el_mismo_pass(scenario: _Scenario) -> None:
    """El job del inspector NO colisiona con la cascada del MISMO incidente:
    ni en notification_jobs (índices parciales 0014) ni en el timeline
    (actor con sufijo de action_id)."""
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = scenario.seed_incident(
        severity="critical", opened_at=BASE
    )  # cascada + email crítico
    action = _seed_action(scenario, incident, ts=BASE)
    providers = _providers()
    _run(scenario, providers, now=BASE)
    inspector_jobs = _action_jobs(scenario, action)
    assert len(inspector_jobs) == 1 and inspector_jobs[0]["status"] == "sent"
    # El email crítico del incidente TAMBIÉN salió (paralelo, mismo canal).
    kinds = [m.get("kind") for _t, m in providers["email"].sent]
    assert kinds.count("dictamen_request") == 1
    assert len(providers["email"].sent) >= 2
    # Dos notify_sent del mismo incidente/pass sin colisión de unique.
    assert len(scenario.notify_actions(incident)) >= 2
