"""Exportación PDF por incidente (T-1.20 · B5): genera + sube + registra.

Patrón de ``test_exports.py``: fixtures del conftest de B2, S3 con moto.
``POST /incidents/{id}/report`` construye el PDF del dictamen, lo sube al
bucket de evidencia, inserta ``evidence_objects kind='report_pdf'`` (sha256
del objeto) + huella en ``audit_log`` y responde con presigned URL.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.reports import router as reports_router

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(reports_router)
    return application


def _env_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _make_bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": _REGION},
    )


def _get_object(key: str) -> bytes:
    import boto3

    obj = boto3.client("s3", region_name=_REGION).get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read()


async def _evidence_rows(incident_id: str) -> list:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT kind, s3_key, sha256, tenant_id FROM evidence_objects "
                    "WHERE incident_id = :i"
                ),
                {"i": incident_id},
            )
        ).all()
    return rows


async def _audit_verbs(tenant_id: str) -> list[str]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT verb FROM audit_log WHERE tenant_id = :t ORDER BY ts"),
                {"t": tenant_id},
            )
        ).all()
    return [r.verb for r in rows]


async def test_report_generates_pdf_evidence_and_audits(
    client, make_incident, make_dictamen, monkeypatch
) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor")

        tok = au.make_token("inspector", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
        assert r.status_code == 201
        body = r.json()
        assert body["expires_in"] == 300
        assert BUCKET in body["url"]

        rows = await _evidence_rows(iid)
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "report_pdf"
        assert iid in row.s3_key and row.s3_key.endswith(".pdf")

        pdf = _get_object(row.s3_key)
        assert pdf.startswith(b"%PDF-")
        assert row.sha256 == hashlib.sha256(pdf).hexdigest()

    assert "export_pdf" in await _audit_verbs(au.DB_TENANT_PRIV)


async def test_report_without_bucket_is_503(client, make_incident, monkeypatch) -> None:
    monkeypatch.delenv("TAKAB_API_EVIDENCE_BUCKET", raising=False)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
    assert r.status_code == 503


async def test_report_cross_tenant_is_404(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        tok = au.make_token("inspector", tenant=au.DB_TENANT_PRIV2)
        r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
        assert r.status_code == 404


async def test_report_non_export_role_forbidden(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
    assert r.status_code == 403


async def test_report_gov_operator_forbidden(client, make_incident, monkeypatch) -> None:
    """gov descarga evidencia existente (exports), pero NO genera evidencia
    en el tenant ajeno (la fila llevaría un tenant_id que su RLS rechaza)."""
    _env_bucket(monkeypatch)
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    tok = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)
    r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
    assert r.status_code == 403
