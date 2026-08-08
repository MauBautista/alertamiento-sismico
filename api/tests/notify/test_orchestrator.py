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
from takab_api.notify.plan import CASCADE_ORDER
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
    """Stand-in de un proveedor REAL (entrega o revienta). [T-2.75] Lo declara:
    quien no se declara real se trata como simulado (default = peor causa)."""

    simulated = False

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
            "SELECT channel, mode, position, status, attempts, due_at, deadline_at, "
            "sent_at, target, error FROM notification_jobs WHERE incident_id = %s "
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
        conn.execute("DELETE FROM push_tokens WHERE tenant_id = %s", (tenant,))
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
    # Con todos los canales caídos, la cascada INTENTÓ todos (nunca calla). Los
    # tres primeros mueren ya (tenían a quién escalar); el ÚLTIMO salto no tiene
    # a nadie detrás y queda en reintento (T-1.62) en vez de convertirse en lápida.
    assert [j["status"] for j in cascade] == ["failed", "failed", "failed", "pending"]
    assert scenario.job(iid, "email")["attempts"] == 1


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

    # Un job paralelo no tiene a quién escalar: reintenta (T-1.62), no muere.
    down = scenario.job(iid, "webhook", mode="parallel")
    assert down["status"] == "pending"
    assert down["attempts"] == 1
    for ch in ("whatsapp", "sms", "email"):
        assert scenario.job(iid, ch, mode="parallel")["status"] == "sent"


# -------------------------------------------------------------- reintentos
# [T-1.62] Un fallo de proveedor era una LÁPIDA: el job quedaba 'failed' para
# siempre, el re-encolado lo daba por atendido y el 409 de dictamen-request
# impedía volver a pedirlo. Un AccessDenied de SES dejó un incidente real sin
# correo. Ahora: el que NO tiene a quién escalar reintenta con backoff.


def test_email_paralelo_reintenta_con_backoff(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident(severity="critical")
    providers = _providers(email=True)
    _run(scenario, providers, now=BASE)

    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "pending"  # vivo, no lápida
    assert par["attempts"] == 1
    assert par["due_at"] == BASE + timedelta(seconds=30)
    assert par["error"] == "fallo simulado"  # el motivo queda registrado
    assert par["sent_at"] is None

    providers["email"].fail = False  # el proveedor vuelve en sí
    _run(scenario, providers, now=BASE + timedelta(seconds=30))

    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "sent"
    assert par["sent_at"] == BASE + timedelta(seconds=30)
    assert len(providers["email"].sent) == 1
    # El SLA se reporta con honestidad: el reintento llegó tarde al deadline.
    payload = next(
        a["payload"] for a in scenario.notify_actions(iid) if a["payload"]["channel"] == "email"
    )
    assert payload["deadline_met"] is False


def test_reintentos_se_agotan_y_marcan_failed(scenario: _Scenario) -> None:
    scenario.seed_config()
    iid = scenario.seed_incident(severity="critical")
    providers = _providers(email=True)

    _run(scenario, providers, now=BASE)  # intento 1 → +30 s
    _run(scenario, providers, now=BASE + timedelta(seconds=30))  # intento 2 → +2 min
    par = scenario.job(iid, "email", mode="parallel")
    assert (par["status"], par["attempts"]) == ("pending", 2)
    assert par["due_at"] == BASE + timedelta(seconds=150)

    _run(scenario, providers, now=BASE + timedelta(seconds=150))  # intento 3: agotado
    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "failed"
    assert par["attempts"] == 3
    assert par["error"] == "fallo simulado"
    assert len(providers["email"].sent) == 0


def test_cascada_con_escalado_no_reintenta(scenario: _Scenario) -> None:
    """Reintentar un salto de cascada retrasaría llegar al humano: si hay a quién
    escalar, el fallo es inmediato y definitivo (semántica intacta de T-1.21)."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    _run(scenario, _providers(webhook=True), now=BASE)

    down = scenario.job(iid, "webhook")
    assert down["status"] == "failed"  # jamás 'pending': el whatsapp ya salió
    assert down["attempts"] == 1
    assert scenario.job(iid, "whatsapp")["status"] == "sent"


def test_ultimo_salto_de_cascada_reintenta_y_entrega(scenario: _Scenario) -> None:
    """Con TODA la cascada caída, el último salto es la única voz que queda: se
    reintenta hasta entregar en vez de dejar el incidente en silencio."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True, sms=True, email=True)
    _run(scenario, providers, now=BASE)
    assert scenario.job(iid, "email")["status"] == "pending"

    providers["email"].fail = False
    _run(scenario, providers, now=BASE + timedelta(seconds=30))

    assert scenario.job(iid, "email")["status"] == "sent"
    assert len(providers["email"].sent) == 1


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


# --- T-2.10 · Notificación al SOC en personas en riesgo (daños 2.4) --------------


def _seed_people_at_risk(
    scenario: _Scenario, incident_id: str, *, ts: datetime, report_id: str | None = None
) -> str:
    import json as _json

    action = str(uuid.uuid4())
    scenario.conn.execute(
        "INSERT INTO incident_actions (action_id, incident_id, tenant_id, ts, kind, "
        "actor, payload) VALUES (%s,%s,%s,%s,'damage_people_at_risk',%s,%s::jsonb)",
        (
            action,
            incident_id,
            scenario.tenant,
            ts,
            "user:brigada-uno",
            _json.dumps({"report_id": report_id or str(uuid.uuid4())}),
        ),
    )
    scenario.conn.commit()
    return action


def test_personas_en_riesgo_notifica_al_soc_de_inmediato(scenario: _Scenario) -> None:
    """[T-2.10] Un reporte con personas en riesgo dispara un email INMEDIATO al
    SOC (headline propio); reusa el destino operativo inspector_emails."""
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = _old_incident(scenario)
    action = _seed_people_at_risk(scenario, incident, ts=BASE - timedelta(seconds=5))
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
    _target, message = providers["email"].sent[0]
    assert message["kind"] == "damage_people_at_risk"
    assert "PERSONAS EN RIESGO" in message["headline"]
    assert message["link"] == f"https://soc.example.mx/triage?incident={incident}"


def test_personas_en_riesgo_no_duplica_el_correo(scenario: _Scenario) -> None:
    """Prioridad máxima pero idempotente: dos passes ⇒ un solo email."""
    scenario.seed_config(INSPECTOR_CONFIG)
    incident = _old_incident(scenario)
    action = _seed_people_at_risk(scenario, incident, ts=BASE - timedelta(seconds=5))
    providers = _providers()
    _run(scenario, providers, now=BASE)
    _run(scenario, providers, now=BASE + timedelta(seconds=30))
    assert len(_action_jobs(scenario, action)) == 1
    assert len(providers["email"].sent) == 1


# --- T-2.75 · Un canal simulado deja de mentir ----------------------------------
# Un canal sin proveedor real no entrega nada. Marcarlo 'sent' convertía el
# tablero en un mentiroso ("notificado" sin notificar) Y —peor— SATISFACÍA la
# cascada: el salto simulado "triunfaba", el orquestador marcaba `skipped` el
# resto y el canal REAL que venía detrás no llegaba a dispararse jamás.


class _SimProvider:
    """Canal sin proveedor real: se declara simulado (contrato NotifyProvider)."""

    simulated = True

    def __init__(self) -> None:
        self.sent: list[tuple[dict, dict]] = []

    def send(self, target: dict, message: dict) -> None:  # pragma: no cover - no debe llamarse
        self.sent.append((target, message))


def _mixed(*simulated: str, fail: tuple[str, ...] = ()) -> dict:
    """Registro con los canales de ``simulated`` sin proveedor real."""
    providers = _providers(**{ch: True for ch in fail})
    for channel in simulated:
        providers[channel] = _SimProvider()  # type: ignore[assignment]
    return providers


def _actions_by_kind(scenario: _Scenario, incident_id: str, kind: str) -> list[dict]:
    return scenario.conn.execute(
        "SELECT payload FROM incident_actions WHERE incident_id = %s AND kind = %s ORDER BY ts",
        (incident_id, kind),
    ).fetchall()


def _sim_actions(scenario: _Scenario, incident_id: str) -> list[dict]:
    return _actions_by_kind(scenario, incident_id, "notify_simulated")


def test_canal_simulado_no_marca_sent(scenario: _Scenario) -> None:
    """Criterio 1: el job queda 'simulated' y SIN ``sent_at``. Dos candados: el
    estado, y la marca de tiempo de entrega que nadie puede rellenar."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    _run(scenario, _mixed("webhook"), now=BASE)

    job = scenario.job(iid, "webhook")
    assert job["status"] == "simulated"
    assert job["sent_at"] is None


def test_simulado_deja_huella_propia_en_incident_actions(scenario: _Scenario) -> None:
    """Criterio 1: la evidencia lo dice con un verbo PROPIO. Un `notify_sent`
    con una bandera dentro se lee como enviado en cualquier consulta que agrupe
    por `kind` — y `incident_actions` es evidencia que jamás se poda."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    _run(scenario, _mixed("webhook"), now=BASE)

    sims = _sim_actions(scenario, iid)
    assert len(sims) == 1
    payload = sims[0]["payload"]
    assert payload["channel"] == "webhook"
    assert payload["simulated"] is True
    # Medir el plazo de una entrega que no ocurrió es inventar un dato: null es
    # "no aplica", y no se confunde con el False de "llegó tarde" (regla de oro 7).
    assert payload["deadline_met"] is None
    # Y NO existe un notify_sent de ese canal: la mentira no entra por otra puerta.
    assert [a["payload"]["channel"] for a in scenario.notify_actions(iid)] != ["webhook"]


def test_simulado_no_satisface_la_cascada_y_escala_al_canal_real(scenario: _Scenario) -> None:
    """LA CASCADA. Config de dev real: whatsapp y sms SIMULADOS, webhook caído.

    Antes: webhook falla → whatsapp simulado "triunfa" → sms y email `skipped`.
    El correo REAL —el único canal que llegaba a un humano— no se disparaba.
    Ahora: los dos simulados escalan y el email sale en el MISMO pass.
    """
    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _mixed("whatsapp", "sms", fail=("webhook",))
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook")["status"] == "failed"
    assert scenario.job(iid, "whatsapp")["status"] == "simulated"
    assert scenario.job(iid, "sms")["status"] == "simulated"
    email = scenario.job(iid, "email")
    assert email["status"] == "sent"
    assert email["sent_at"] == BASE  # adelantado: escaló dentro del mismo pass
    assert len(providers["email"].sent) == 1
    # Ningún canal simulado tocó a su proveedor: no hay a quién entregar.
    assert providers["whatsapp"].sent == []
    assert providers["sms"].sent == []


def test_toda_la_cascada_simulada_no_deja_ni_un_entregado(scenario: _Scenario) -> None:
    """Criterio 3: con los cuatro canales simulados, NADA aparece entregado —
    ni un 'sent', ni un `sent_at`, ni un `notify_sent`. Y quedan cuatro huellas."""
    scenario.seed_config()
    iid = scenario.seed_incident()
    _run(scenario, _mixed(*CASCADE_ORDER), now=BASE)

    jobs = scenario.jobs(iid)
    assert len(jobs) == len(CASCADE_ORDER)
    assert {j["status"] for j in jobs} == {"simulated"}
    assert all(j["sent_at"] is None for j in jobs)
    assert scenario.notify_actions(iid) == []
    assert {a["payload"]["channel"] for a in _sim_actions(scenario, iid)} == set(CASCADE_ORDER)


def test_simulado_es_terminal_y_no_consume_reintentos(scenario: _Scenario) -> None:
    """La distinción cara: `failed` es transitorio (el proveedor existe y puede
    volver) ⇒ reintento con backoff. `simulated` es TERMINAL (no hay proveedor
    que pueda volver) ⇒ ni un intento consumido, ni un martilleo contra la nada.
    """
    scenario.seed_config()
    iid = scenario.seed_incident(severity="critical")
    providers = _mixed("email")  # el paralelo crítico no tiene a quién escalar
    _run(scenario, providers, now=BASE)

    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "simulated"
    assert par["attempts"] == 0
    # Un pass posterior no lo re-despacha ni lo revive: es terminal, no pendiente.
    _run(scenario, providers, now=BASE + timedelta(seconds=600))
    par = scenario.job(iid, "email", mode="parallel")
    assert (par["status"], par["attempts"]) == ("simulated", 0)


def test_provider_que_no_se_declara_real_se_trata_como_simulado(scenario: _Scenario) -> None:
    """El default ante lo desconocido es la PEOR causa. Un provider que no
    declara `simulated` no ha demostrado que entregue: se le trata como
    simulado. Así el sexto canal que alguien enchufe sin declararse no hereda
    la presunción de entrega."""

    class _Indeclarado:
        def send(self, target: dict, message: dict) -> None:
            return None

    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers()
    providers["webhook"] = _Indeclarado()  # type: ignore[assignment]
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook")["status"] == "simulated"


def test_push_simulado_tampoco_entrega(scenario: _Scenario) -> None:
    """El canal push despacha por una rama PROPIA (``deliver()``, no ``send()``).
    La regla se aplica antes de bifurcar: no se enumeran canales, se pregunta al
    proveedor."""
    from takab_api.notify.push import SimulatedPushProvider

    scenario.seed_config()
    iid = scenario.seed_incident()
    site = scenario.conn.execute(
        "SELECT site_id FROM incidents WHERE incident_id = %s", (iid,)
    ).fetchone()["site_id"]
    scenario.conn.execute("RESET ROLE")  # takab_ingest lee y actualiza tokens, no los crea
    scenario.conn.execute(
        "INSERT INTO push_tokens (tenant_id, site_id, user_sub, token, platform) "
        "VALUES (%s,%s,%s,%s,'android')",
        (scenario.tenant, site, str(uuid.uuid4()), f"tok-{uuid.uuid4()}"),
    )
    scenario.conn.execute("SET ROLE takab_ingest")
    scenario.conn.commit()

    providers = _providers()
    providers["push"] = SimulatedPushProvider()  # type: ignore[assignment]
    _run(scenario, providers, now=BASE)

    push_job = scenario.job(iid, "push", mode="parallel")
    assert push_job["status"] == "simulated"
    assert push_job["sent_at"] is None
    assert providers["push"].delivered == []


def test_las_tres_cosas_dejan_verbos_DISTINTOS_en_la_evidencia(scenario: _Scenario) -> None:
    """Entregado, simulado y no entregado son TRES cosas con tres reacciones
    del operador: nada / contratar el canal / el proveedor está caído AHORA.
    En un mismo incidente, tres verbos distintos en `incident_actions`.
    """
    scenario.seed_config()
    iid = scenario.seed_incident()
    # webhook cae (y escala: fallo terminal), whatsapp simulado, sms entrega.
    providers = _mixed("whatsapp", fail=("webhook",))
    _run(scenario, providers, now=BASE)

    assert scenario.job(iid, "webhook")["status"] == "failed"
    assert scenario.job(iid, "whatsapp")["status"] == "simulated"
    assert scenario.job(iid, "sms")["status"] == "sent"

    sent = _actions_by_kind(scenario, iid, "notify_sent")
    simulated = _actions_by_kind(scenario, iid, "notify_simulated")
    failed = _actions_by_kind(scenario, iid, "notify_failed")
    assert [a["payload"]["channel"] for a in sent] == ["sms"]
    assert [a["payload"]["channel"] for a in simulated] == ["whatsapp"]
    assert [a["payload"]["channel"] for a in failed] == ["webhook"]
    # El fallo dice POR QUÉ (avería concreta); el simulado dice que no hay canal.
    assert failed[0]["payload"]["error"] == "fallo simulado"
    assert failed[0]["payload"]["deadline_met"] is None


def test_el_reintento_no_escribe_evidencia_hasta_agotarse(scenario: _Scenario) -> None:
    """`incident_actions` es append-only y EXENTA de poda por retención (regla
    de oro 11): una fila por intento inflaría para siempre la tabla que existe
    para reconstruir lo ocurrido. Se escribe UNA vez, al desenlace terminal."""
    scenario.seed_config()
    iid = scenario.seed_incident(severity="critical")
    providers = _providers(email=True)  # paralelo crítico: reintenta, no escala

    _run(scenario, providers, now=BASE)  # intento 1 → pending
    _run(scenario, providers, now=BASE + timedelta(seconds=30))  # intento 2 → pending
    par = scenario.job(iid, "email", mode="parallel")
    assert par["status"] == "pending"
    assert _actions_by_kind(scenario, iid, "notify_failed") == []  # aún puede volver

    _run(scenario, providers, now=BASE + timedelta(seconds=150))  # intento 3: agotado
    assert scenario.job(iid, "email", mode="parallel")["status"] == "failed"
    failed = _actions_by_kind(scenario, iid, "notify_failed")
    assert len(failed) == 1
    assert failed[0]["payload"]["attempts"] == 3


# --- T-2.76 · el SMS real de Twilio contra el orquestador SIN TOCARLO ------------


def _twilio(handler) -> object:
    """Provider de Twilio con transporte falso. CERO red (no hay credenciales)."""
    import httpx

    from takab_api.notify.twilio import TwilioSmsProvider

    return TwilioSmsProvider(
        account_sid="ACtest",
        auth_token="tok",
        from_number="+525599999999",
        messaging_service_sid="",
        timeout_s=2.0,
        validity_period_s=300,
        status_callback_url="",
        transport=httpx.MockTransport(handler),
    )


def test_twilio_entrega_por_la_misma_interfaz_y_deja_la_evidencia(scenario: _Scenario) -> None:
    """Criterios 1 y 3 juntos: el proveedor REAL se enchufa donde estaba el
    simulado —sin una línea del orquestador— y la evidencia sale con la misma
    forma que el resto (latencia + `deadline_met`)."""
    import httpx

    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return httpx.Response(201, json={"sid": "SM1", "status": "queued", "num_segments": "1"})

    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True)  # los dos previos caen
    providers["sms"] = _twilio(handler)  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=20))  # t0+20: le toca al sms

    sms = scenario.job(iid, "sms")
    assert sms["status"] == "sent"
    assert sms["sent_at"] == BASE + timedelta(seconds=20)
    assert len(peticiones) == 1

    acciones = scenario.notify_actions(iid)
    evidencia = [a["payload"] for a in acciones if a["payload"]["channel"] == "sms"]
    assert len(evidencia) == 1
    assert evidencia[0]["latency_s"] == 20.0
    assert evidencia[0]["deadline_met"] is True  # t0+20 ≤ deadline t0+30


def test_twilio_sin_credenciales_deja_el_sms_SIMULADO_no_enviado(scenario: _Scenario) -> None:
    """🚨 El invariante que T-2.75 compró: sin credenciales el canal NO finge.
    `build_providers` con un Settings pelado devuelve un simulado, y el job
    termina 'simulated' con `sent_at` en NULL — jamás 'sent'."""
    from takab_api.notify.providers import build_providers

    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True)
    providers["sms"] = build_providers(Settings())["sms"]  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=20))

    sms = scenario.job(iid, "sms")
    assert sms["status"] == "simulated"
    assert sms["sent_at"] is None
    assert "sms" not in [a["payload"]["channel"] for a in scenario.notify_actions(iid)]
    assert [a["payload"]["channel"] for a in _sim_actions(scenario, iid)] == ["sms"]
    # Y escala: el email real sale igual, porque un simulado no satisface nada.
    assert scenario.job(iid, "email")["status"] == "sent"


def test_twilio_caido_escala_al_correo_sin_duplicar_el_sms(scenario: _Scenario) -> None:
    """Un 5xx es AMBIGUO (el mensaje pudo crearse). El orquestador escala al
    email —el humano llega igual— y el SMS no se repite en el mismo incidente:
    un duplicado durante un sismo es ruido en el peor momento posible."""
    import httpx

    intentos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        intentos.append(request)
        return httpx.Response(500, json={"message": "twilio caído"})

    scenario.seed_config()
    iid = scenario.seed_incident()
    providers = _providers(webhook=True, whatsapp=True)
    providers["sms"] = _twilio(handler)  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=20))

    assert scenario.job(iid, "sms")["status"] == "failed"
    assert scenario.job(iid, "email")["status"] == "sent"  # el humano SÍ es avisado
    assert len(intentos) == 1
    fallidos = _actions_by_kind(scenario, iid, "notify_failed")
    assert "sms" in [a["payload"]["channel"] for a in fallidos]


# --- T-2.77 · WhatsApp por plantilla contra el orquestador SIN TOCARLO -----------
#
# El canal cuya degradación NO es un fallo del proveedor sino un veredicto de
# Meta sobre un texto. Aquí se acredita de punta a punta que ese veredicto se
# traduce en el desenlace correcto de `notification_jobs`.

WA_CONFIG = {
    "notifications": {
        "webhook": {"url": "https://soc.example.mx/hook", "secret": "s3cr3t"},
        # [T-2.77] El opt-in viaja con el destino: sin él el provider se niega.
        "whatsapp": {"to": "+525511111111", "opt_in": {"at": "2026-08-01T12:00:00Z"}},
        "sms": {"to": "+525522222222"},
        "email": {"to": ["ops@example.mx"]},
    }
}


def _wa_settings(tmp_path, *, aprobada: bool):
    """Settings con credenciales de mentira y un catálogo de plantillas propio.

    ``aprobada=False`` es el estado REAL del repo hoy (nadie las ha mandado a
    Meta); ``aprobada=True`` simula el día después de la aprobación sellando el
    digest del texto sin tocar una coma.
    """
    import json
    from pathlib import Path

    from takab_api.notify.whatsapp import TEMPLATES_DIR, template_digest

    directorio = Path(tmp_path) / "wa"
    directorio.mkdir()
    for src in sorted(TEMPLATES_DIR.glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        if aprobada:
            doc["approval"] = {
                "status": "APPROVED",
                "approved_digest": template_digest(doc["template"]),
            }
        (directorio / src.name).write_text(json.dumps(doc, ensure_ascii=False))
    return Settings(  # type: ignore[call-arg]
        notify_whatsapp_phone_number_id="1234567890",
        notify_whatsapp_access_token="EAAtest",
        notify_whatsapp_graph_version="v23.0",
        notify_whatsapp_templates_dir=str(directorio),
    )


def _whatsapp(tmp_path, handler, *, aprobada: bool = True) -> object:
    """Provider de WhatsApp con transporte falso. CERO red a Meta."""
    import httpx

    from takab_api.notify.whatsapp import build_whatsapp_provider

    return build_whatsapp_provider(
        _wa_settings(tmp_path, aprobada=aprobada), transport=httpx.MockTransport(handler)
    )


def _wa_ok(request):
    import httpx

    return httpx.Response(
        200,
        json={
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.OK", "message_status": "accepted"}],
        },
    )


def test_whatsapp_entrega_por_la_misma_interfaz_y_deja_la_evidencia(
    scenario: _Scenario, tmp_path
) -> None:
    """Criterios 1 y 3 juntos: la plantilla aprobada se enchufa donde estaba el
    simulado —sin una línea del orquestador— y la evidencia sale con la misma
    forma que el resto de canales."""
    peticiones: list = []

    def handler(request):
        peticiones.append(request)
        return _wa_ok(request)

    scenario.seed_config(WA_CONFIG)
    iid = scenario.seed_incident()
    providers = _providers(webhook=True)  # el webhook cae y le toca a whatsapp
    providers["whatsapp"] = _whatsapp(tmp_path, handler)  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=10))

    wa = scenario.job(iid, "whatsapp")
    assert wa["status"] == "sent"
    assert wa["sent_at"] == BASE + timedelta(seconds=10)
    assert len(peticiones) == 1

    evidencia = [
        a["payload"] for a in scenario.notify_actions(iid) if a["payload"]["channel"] == "whatsapp"
    ]
    assert len(evidencia) == 1
    assert evidencia[0]["latency_s"] == 10.0
    # Sin deadline para este canal el plan pone NULL: `deadline_met` es True
    # porque no hay plazo que incumplir, no porque se haya medido una entrega.
    assert evidencia[0]["deadline_met"] is True
    # Y la cascada se satisface: el SMS de pago ya no sale.
    assert scenario.job(iid, "sms")["status"] == "skipped"


def test_whatsapp_sin_plantilla_aprobada_queda_SIMULADO_no_enviado(
    scenario: _Scenario, tmp_path
) -> None:
    """🚨 El criterio 2, de punta a punta y en el estado REAL de hoy. Hay
    credenciales, hay red, hay provider real — y aun así nadie puede recibir
    nada, porque WhatsApp no deja improvisar texto y Meta no ha aprobado la
    plantilla. El canal CAE: 'simulated', `sent_at` en NULL, verbo propio en la
    evidencia y escalada al SMS. No finge."""

    def handler(request):  # pragma: no cover - no debe llamarse jamás
        raise AssertionError("sin plantilla aprobada no puede salir una petición")

    scenario.seed_config(WA_CONFIG)
    iid = scenario.seed_incident()
    providers = _providers(webhook=True)
    providers["whatsapp"] = _whatsapp(tmp_path, handler, aprobada=False)  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=10))

    wa = scenario.job(iid, "whatsapp")
    assert wa["status"] == "simulated"
    assert wa["sent_at"] is None
    assert "whatsapp" not in [a["payload"]["channel"] for a in scenario.notify_actions(iid)]
    assert [a["payload"]["channel"] for a in _sim_actions(scenario, iid)] == ["whatsapp"]
    # `deadline_met` es NULL, no False: sin entrega no hay plazo que incumplir.
    assert _sim_actions(scenario, iid)[0]["payload"]["deadline_met"] is None
    # Y escala: el SMS sale igual, porque un simulado no satisface nada.
    assert scenario.job(iid, "sms")["status"] == "sent"


def test_si_meta_PAUSA_la_plantilla_el_canal_cae_para_el_siguiente_incidente(
    scenario: _Scenario, tmp_path
) -> None:
    """El escenario que da nombre al criterio 2, medido donde importa.

    Meta pausa una plantilla por calidad SIN avisar (error 132015). El incidente
    en curso da `failed` —el proveedor sí existía y sí respondió— pero el canal
    queda tumbado, así que el incidente SIGUIENTE ya no se estrella contra una
    plantilla muerta: se declara `simulated` y escala en el acto. La diferencia
    importa: `failed` reintenta con backoff, `simulated` no; martillear una
    plantilla pausada solo empeora su calificación de calidad en Meta.
    """
    import httpx

    intentos: list = []

    def handler(request):
        intentos.append(request)
        return httpx.Response(
            400, json={"error": {"code": 132015, "message": "Template is paused"}}
        )

    scenario.seed_config(WA_CONFIG)
    provider = _whatsapp(tmp_path, handler)
    providers = _providers(webhook=True)
    providers["whatsapp"] = provider  # type: ignore[assignment]

    primero = scenario.seed_incident()
    _run(scenario, providers, now=BASE + timedelta(seconds=10))
    assert scenario.job(primero, "whatsapp")["status"] == "failed"
    assert "132015" in scenario.job(primero, "whatsapp")["error"]

    segundo = scenario.seed_incident(opened_at=BASE + timedelta(minutes=1))
    _run(scenario, providers, now=BASE + timedelta(minutes=1, seconds=10))

    assert scenario.job(segundo, "whatsapp")["status"] == "simulated"
    assert len(intentos) == 1  # ni una petición más contra la plantilla muerta
    assert scenario.job(segundo, "sms")["status"] == "sent"  # el humano llega igual


def test_whatsapp_sin_opt_in_no_sale_y_lo_deja_ESCRITO(scenario: _Scenario, tmp_path) -> None:
    """El hallazgo de compliance, medido: un tenant con el teléfono configurado
    pero SIN constancia de consentimiento no produce un silencio — produce un
    `notify_failed` rojo en la consola, con el motivo dentro, y escala al SMS."""
    sin_opt_in = {
        "notifications": {
            **WA_CONFIG["notifications"],
            "whatsapp": {"to": "+525511111111"},
        }
    }

    def handler(request):  # pragma: no cover - no debe llamarse jamás
        raise AssertionError("sin opt-in no puede salir una petición")

    scenario.seed_config(sin_opt_in)
    iid = scenario.seed_incident()
    providers = _providers(webhook=True)
    providers["whatsapp"] = _whatsapp(tmp_path, handler)  # type: ignore[assignment]
    _run(scenario, providers, now=BASE + timedelta(seconds=10))

    assert scenario.job(iid, "whatsapp")["status"] == "failed"
    fallidos = _actions_by_kind(scenario, iid, "notify_failed")
    motivo = next(a["payload"]["error"] for a in fallidos if a["payload"]["channel"] == "whatsapp")
    assert "opt-in" in motivo
    assert scenario.job(iid, "sms")["status"] == "sent"
