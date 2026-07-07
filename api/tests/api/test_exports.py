"""Exportación de evidencia (T-1.22 · B4): listado RLS + presigned + audit.

Reusa las fixtures de ``tests/api/conftest.py`` (entorno de auth, engine por
test, ``make_incident``, limpieza por TRUNCATE que ya incluye evidence_objects/
audit_log). Sobrescribe ``app`` para montar SOLO el router de exports (la
integración en main.py es de otra fase). S3 se mockea con moto.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.exports import router as exports_router

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"


@pytest.fixture
def app() -> FastAPI:
    """Override del ``app`` del conftest: monta el router de exports."""
    application = create_app()
    application.include_router(exports_router)
    return application


async def _add_evidence(
    incident_id: str,
    tenant_id: str,
    *,
    kind: str = "miniseed",
    s3_key: str = "evidence/x/abc.mseed",
) -> str:
    engine = get_engine()
    eid = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO evidence_objects (evidence_id, tenant_id, incident_id, "
                "kind, s3_key, sha256) VALUES (:e, :t, :i, :k, :key, 'deadbeef')"
            ),
            {"e": eid, "t": tenant_id, "i": incident_id, "k": kind, "key": s3_key},
        )
    return eid


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


async def test_list_evidence_scoped_to_tenant(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed")

    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "miniseed"


async def test_list_evidence_cross_tenant_is_empty(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _add_evidence(iid, au.DB_TENANT_PRIV)

    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV2)
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_list_evidence_mobile_surface_forbidden(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="mobile")
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 403


async def test_download_presigned_and_audits_miniseed(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        key = "evidence/EVT-1/proof.mseed"
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed", s3_key=key)

        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 200
        body = r.json()
        assert body["expires_in"] == 300
        assert BUCKET in body["url"] and "proof.mseed" in body["url"]

    assert "export_miniseed" in await _audit_verbs(au.DB_TENANT_PRIV)


async def test_download_pdf_audits_export_pdf(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        ev = await _add_evidence(
            iid, au.DB_TENANT_PRIV, kind="report_pdf", s3_key="dictamen/x/d.pdf"
        )
        tok = au.make_token("inspector", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 200

    assert "export_pdf" in await _audit_verbs(au.DB_TENANT_PRIV)


async def test_download_gov_sees_gov_shared(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
        ev = await _add_evidence(iid, au.DB_TENANT_GOV, kind="miniseed")
        tok = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 200


async def test_download_gov_private_is_404(client, make_incident, monkeypatch) -> None:
    """gov_operator NO ve evidencia de un tenant privado → 404 (sin fuga)."""
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed")
        tok = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 404


async def test_download_non_export_role_forbidden(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ev = await _add_evidence(iid, au.DB_TENANT_PRIV)
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
    assert r.status_code == 403


async def test_download_no_bucket_503(client, make_incident, monkeypatch) -> None:
    monkeypatch.delenv("TAKAB_API_EVIDENCE_BUCKET", raising=False)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ev = await _add_evidence(iid, au.DB_TENANT_PRIV)
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
    assert r.status_code == 503
