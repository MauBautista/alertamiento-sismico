"""T-2.04 · Canal push: payload mínimo por clase, provider SNS (moto) y la
rama del orquestador (enqueue por dispositivos + sellado de ARN + revocación).

Invariantes:
- Las clases JAMÁS se mezclan: CRISIS lleva sonido crítico/time-sensitive y el
  canal Android ``seismic_alert``; OPS va normal.
- El payload visible es GENÉRICO (lockscreen): sin nombre de sitio, sin
  severidad, sin PII — solo ids y fase (la app consulta la verdad por API).
- Sin dispositivos registrados NO se encola job push (nada de 'sent' vacíos).
- Endpoint deshabilitado ⇒ el token se REVOCA (limpieza honesta).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

import boto3
import psycopg
import pytest
from moto import mock_aws
from psycopg.rows import dict_row

from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.push import (
    PUSH_CLASS_CRISIS,
    PUSH_CLASS_OPS,
    PushDevice,
    PushOutcome,
    SnsPushProvider,
    build_push_payload,
)
from takab_api.settings import Settings

BASE = datetime(2033, 5, 10, 12, 0, 0, tzinfo=UTC)
SRC_LON, SRC_LAT = -101.5, 11.0

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


# ------------------------------------------------------------------ payloads


def test_payload_crisis_es_minimo_y_critico() -> None:
    payload = build_push_payload(
        push_class=PUSH_CLASS_CRISIS, site_id="S1", incident_id="I1", phase="alert_active"
    )
    data = json.loads(payload["default"])
    # payload mínimo EXACTO: ids y fase; jamás nombres/severidad/PII (lockscreen)
    assert set(data) == {"type", "class", "site_id", "incident_id", "phase"}
    assert data["class"] == "CRISIS"

    aps = json.loads(payload["APNS"])["aps"]
    assert aps["interruption-level"] == "time-sensitive"  # base pre-entitlement
    assert aps["sound"]["critical"] == 1  # listo para GATE-STORE

    gcm = json.loads(payload["GCM"])
    assert gcm["android"]["notification"]["channel_id"] == "seismic_alert"
    assert gcm["android"]["priority"] == "high"
    assert gcm["data"]["incident_id"] == "I1"
    # texto visible genérico: sin sitio ni severidad
    assert "S1" not in json.dumps(gcm["notification"])


def test_payload_ops_jamas_es_critico() -> None:
    payload = build_push_payload(
        push_class=PUSH_CLASS_OPS, site_id="S1", incident_id=None, phase="reentry_approved"
    )
    aps = json.loads(payload["APNS"])["aps"]
    assert aps["interruption-level"] == "active"
    assert aps["sound"] == "default"
    gcm = json.loads(payload["GCM"])
    assert gcm["android"]["notification"]["channel_id"] == "ops"
    assert gcm["android"]["priority"] == "normal"


def test_payload_clase_desconocida_revienta() -> None:
    with pytest.raises(ValueError):
        build_push_payload(push_class="URGENTE", site_id="S", incident_id=None, phase="x")


# ------------------------------------------------------------------ provider (moto)


@mock_aws
def test_sns_provider_crea_endpoint_una_vez_y_publica() -> None:
    sns = boto3.client("sns", region_name="us-east-2")
    app = sns.create_platform_application(
        Name="takab-test-fcm", Platform="GCM", Attributes={"PlatformCredential": "x"}
    )["PlatformApplicationArn"]
    provider = SnsPushProvider(region="us-east-2", apns_application_arn="", fcm_application_arn=app)
    device = PushDevice(
        push_token_id="t1", token="fcm-token-abc", platform="android", endpoint_arn=None
    )
    payload = build_push_payload(
        push_class=PUSH_CLASS_CRISIS, site_id="S", incident_id="I", phase="alert_active"
    )

    first = provider.deliver([device], payload)
    assert first.delivered == 1
    assert "t1" in first.created_arns
    assert first.disabled_ids == []

    # segunda entrega con el ARN sellado: no vuelve a crear endpoint
    device2 = PushDevice(
        push_token_id="t1",
        token="fcm-token-abc",
        platform="android",
        endpoint_arn=first.created_arns["t1"],
    )
    second = provider.deliver([device2], payload)
    assert second.delivered == 1
    assert second.created_arns == {}


@mock_aws
def test_sns_provider_endpoint_deshabilitado_se_reporta() -> None:
    sns = boto3.client("sns", region_name="us-east-2")
    app = sns.create_platform_application(
        Name="takab-test-fcm", Platform="GCM", Attributes={"PlatformCredential": "x"}
    )["PlatformApplicationArn"]
    arn = sns.create_platform_endpoint(PlatformApplicationArn=app, Token="tok-1")["EndpointArn"]
    sns.set_endpoint_attributes(EndpointArn=arn, Attributes={"Enabled": "false"})

    provider = SnsPushProvider(region="us-east-2", apns_application_arn="", fcm_application_arn=app)
    outcome = provider.deliver(
        [PushDevice(push_token_id="t9", token="tok-1", platform="android", endpoint_arn=arn)],
        build_push_payload(
            push_class=PUSH_CLASS_CRISIS, site_id="S", incident_id="I", phase="alert_active"
        ),
    )
    assert outcome.delivered == 0
    assert outcome.disabled_ids == ["t9"]


def test_sns_provider_sin_platform_application_reporta_error() -> None:
    provider = SnsPushProvider(region="us-east-2", apns_application_arn="", fcm_application_arn="")
    outcome = provider.deliver(
        [PushDevice(push_token_id="t1", token="x", platform="ios", endpoint_arn=None)],
        build_push_payload(
            push_class=PUSH_CLASS_CRISIS, site_id="S", incident_id=None, phase="alert_active"
        ),
    )
    assert outcome.delivered == 0
    assert outcome.errors  # declarado, no silencioso


# ------------------------------------------------------------------ orquestador


class _FakePushProvider:
    """deliver() controlable: registra lotes y devuelve el outcome configurado."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[PushDevice], dict]] = []
        self.next_outcome: PushOutcome | None = None

    def deliver(self, devices: list[PushDevice], payload: dict) -> PushOutcome:
        self.calls.append((devices, payload))
        if self.next_outcome is not None:
            return self.next_outcome
        return PushOutcome(delivered=len(devices))


class _NullProvider:
    def send(self, target: dict, message: dict) -> None:  # pragma: no cover - no usado
        raise AssertionError("no debería despacharse")


@pytest.fixture
def conn():
    c = psycopg.connect(_dsn(), row_factory=dict_row)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def scenario(conn):
    """Tenant fresco + sitio + dispositivo registrado (limpieza al final)."""
    tenant, site = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES (%s,%s,'Push T','private')",
        (tenant, f"PU{tenant[:6]}"),
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,%s,'Sitio Push', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
        (site, tenant, f"P-{site[:8]}", SRC_LON, SRC_LAT),
    )
    conn.commit()
    yield {"conn": conn, "tenant": tenant, "site": site}
    conn.rollback()
    conn.execute("SET session_replication_role = replica")
    for table, col in (
        ("incident_actions", "tenant_id"),
        ("notification_jobs", "tenant_id"),
        ("push_tokens", "tenant_id"),
        ("incidents", "tenant_id"),
        ("rule_sets", "tenant_id"),
        ("sites", "tenant_id"),
        ("tenants", "tenant_id"),
    ):
        conn.execute(f"DELETE FROM {table} WHERE {col} = %s", (tenant,))  # noqa: S608
    conn.execute("SET session_replication_role = DEFAULT")
    conn.commit()


def _seed_incident(s, *, opened_at: datetime = BASE) -> str:
    incident = str(uuid.uuid4())
    s["conn"].execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
        "severity, trigger) VALUES (%s,%s,%s,%s,%s,'critical','sasmex')",
        (incident, str(uuid.uuid4()), s["tenant"], s["site"], opened_at),
    )
    s["conn"].commit()
    return incident


def _seed_device(s, *, token: str = "fcm-1", endpoint: str | None = None) -> str:
    token_id = str(uuid.uuid4())
    s["conn"].execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, endpoint_arn) VALUES (%s,%s,%s,'android',%s,%s,%s)",
        (token_id, s["tenant"], str(uuid.uuid4()), token, s["site"], endpoint),
    )
    s["conn"].commit()
    return token_id


def _providers(push) -> dict:
    return {ch: _NullProvider() for ch in ("webhook", "whatsapp", "sms", "email")} | {"push": push}


def test_orquestador_encola_y_despacha_push(scenario) -> None:
    """Con dispositivo registrado: job push parallel → sent + ARN sellado +
    incident_action con el conteo de dispositivos (evidencia del despertador)."""
    token_id = _seed_device(scenario)
    incident = _seed_incident(scenario)
    push = _FakePushProvider()
    push.next_outcome = PushOutcome(delivered=1, created_arns={token_id: "arn:ep/1"})

    counts = run_notify_pass(scenario["conn"], Settings(), _providers(push), now=BASE)
    assert counts["enqueued"] == 1  # solo push (tenant sin cascada configurada)
    assert counts["sent"] == 1
    assert len(push.calls) == 1
    devices, payload = push.calls[0]
    assert devices[0].token == "fcm-1"
    assert json.loads(payload["default"])["class"] == "CRISIS"

    row = (
        scenario["conn"]
        .execute(
            "SELECT status FROM notification_jobs WHERE incident_id = %s AND channel='push'",
            (incident,),
        )
        .fetchone()
    )
    assert row["status"] == "sent"
    sealed = (
        scenario["conn"]
        .execute("SELECT endpoint_arn FROM push_tokens WHERE push_token_id = %s", (token_id,))
        .fetchone()
    )
    assert sealed["endpoint_arn"] == "arn:ep/1"
    action = (
        scenario["conn"]
        .execute(
            "SELECT payload FROM incident_actions WHERE incident_id = %s AND kind='notify_sent'",
            (incident,),
        )
        .fetchone()
    )
    assert action["payload"]["devices_delivered"] == 1


def test_sin_dispositivos_no_se_encola_push(scenario) -> None:
    """Sitio sin app instalada: cero jobs push (nada de 'sent' vacíos)."""
    _seed_incident(scenario)
    push = _FakePushProvider()
    counts = run_notify_pass(scenario["conn"], Settings(), _providers(push), now=BASE)
    assert counts["enqueued"] == 0
    assert push.calls == []


def test_endpoint_muerto_revoca_token_y_reintenta(scenario) -> None:
    """Todos los endpoints deshabilitados ⇒ tokens revocados + job en backoff
    (paralelo sin nadie detrás: se reintenta, no se tira — T-1.62)."""
    token_id = _seed_device(scenario, endpoint="arn:ep/dead")
    incident = _seed_incident(scenario)
    push = _FakePushProvider()
    push.next_outcome = PushOutcome(delivered=0, disabled_ids=[token_id])

    counts = run_notify_pass(scenario["conn"], Settings(), _providers(push), now=BASE)
    assert counts["retried"] == 1

    revoked = (
        scenario["conn"]
        .execute("SELECT revoked_at FROM push_tokens WHERE push_token_id = %s", (token_id,))
        .fetchone()
    )
    assert revoked["revoked_at"] is not None
    job = (
        scenario["conn"]
        .execute(
            "SELECT status, attempts FROM notification_jobs WHERE incident_id = %s "
            "AND channel='push'",
            (incident,),
        )
        .fetchone()
    )
    assert job["status"] == "pending"
    assert job["attempts"] == 1
