"""T-2.10 · Evidencia forense (cámara 2.3) — registro + PUT presignado +
verificación de hash server-side.

Criterio de aceptación clave: alterar UN byte del blob tras la captura invalida
la verificación (el backend re-hashea el objeto subido y lo confronta con el
SHA-256 declarado). Se prueba con S3 real (moto) subiendo bytes de verdad.
"""

from __future__ import annotations

import hashlib

import boto3
import pytest
from moto import mock_aws

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.mobile_incident import router as mobile_incident_router
from tests.api.test_mobile_core import _brig, _occ, _seed_zone_and_code

pytestmark = pytest.mark.anyio

BUCKET = "takab-evidence-test"
_REGION = "us-east-2"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    """El pool de ocupantes debe estar activo para que `_occ()` valide (el
    gating del occupant se prueba con su token real, no con un 401 de issuer)."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _env_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _make_bucket():
    client = boto3.client("s3", region_name=_REGION)
    client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION})
    return client


async def _audit_verbs(tenant_id: str) -> list[str]:
    from sqlalchemy import text

    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT verb FROM audit_log WHERE tenant_id = :t ORDER BY ts"),
                {"t": tenant_id},
            )
        ).all()
    return [r.verb for r in rows]


@pytest.mark.anyio
async def test_registro_subida_y_verificacion_integra(
    base_data, make_incident, monkeypatch
) -> None:
    """Foto forense íntegra: registro → PUT presignado → subida → verify OK."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    photo = b"\xff\xd8\xff\xe0forensic-jpeg-bytes-with-baked-watermark"
    sha = hashlib.sha256(photo).hexdigest()

    with mock_aws():
        s3 = _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            reg = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha, "content_type": "image/jpeg"},
                headers=au.bearer(tok),
            )
            assert reg.status_code == 201, reg.text
            evidence_id = reg.json()["evidence_id"]
            assert reg.json()["upload_url"] and BUCKET in reg.json()["upload_url"]

            # el móvil sube el blob al key que el backend generó
            from sqlalchemy import text

            engine = get_engine()
            async with engine.begin() as conn:
                key = (
                    await conn.execute(
                        text("SELECT s3_key FROM evidence_objects WHERE evidence_id = :e"),
                        {"e": evidence_id},
                    )
                ).scalar_one()
            s3.put_object(Bucket=BUCKET, Key=key, Body=photo)

            ver = await client.post(f"/evidence/{evidence_id}/verify", headers=au.bearer(tok))
            assert ver.status_code == 200, ver.text
            body = ver.json()
            assert body["verified"] is True
            assert body["actual_sha256"] == sha

    verbs = await _audit_verbs(au.DB_TENANT_PRIV)
    assert "evidence_registered" in verbs
    assert "evidence_verified" in verbs


@pytest.mark.anyio
async def test_alterar_un_byte_invalida_la_verificacion(
    base_data, make_incident, monkeypatch
) -> None:
    """CRITERIO DE ACEPTACIÓN: un byte alterado tras la captura ⇒ verified=False
    (el hash del objeto subido ya no coincide con el declarado)."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    photo = b"\xff\xd8\xff\xe0blob-integro-de-captura"
    sha = hashlib.sha256(photo).hexdigest()

    with mock_aws():
        s3 = _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            reg = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(tok),
            )
            evidence_id = reg.json()["evidence_id"]
            from sqlalchemy import text

            engine = get_engine()
            async with engine.begin() as conn:
                key = (
                    await conn.execute(
                        text("SELECT s3_key FROM evidence_objects WHERE evidence_id = :e"),
                        {"e": evidence_id},
                    )
                ).scalar_one()
            # se sube un blob ALTERADO (un byte distinto)
            tampered = b"\xff\xd8\xff\xe1blob-integro-de-captura"
            s3.put_object(Bucket=BUCKET, Key=key, Body=tampered)

            ver = await client.post(f"/evidence/{evidence_id}/verify", headers=au.bearer(tok))
            assert ver.status_code == 200
            body = ver.json()
            assert body["verified"] is False
            assert body["expected_sha256"] == sha
            assert body["actual_sha256"] == hashlib.sha256(tampered).hexdigest()


@pytest.mark.anyio
async def test_registro_gating_y_alcance(base_data, make_incident, monkeypatch) -> None:
    """Solo roles con ``evidence_upload`` (RBAC §3) registran; el occupant no;
    el táctico fuera de su ``site_scope`` es 403 (semántica de _incident_in_scope
    para roles no-occupant)."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    sha = hashlib.sha256(b"x").hexdigest()
    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            await _enroll_occ(client)
            occ = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(_occ()),
            )
            assert occ.status_code == 403  # occupant: sin evidence_upload

            import uuid as _uuid

            fuera = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(_brig(site_scope=str(_uuid.uuid4()))),
            )
            assert fuera.status_code == 403


async def test_verify_sin_subir_no_esta_verificado(base_data, make_incident, monkeypatch) -> None:
    """Registrada pero SIN subir el objeto ⇒ verified=False (honesto, no 500)."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    sha = hashlib.sha256(b"pendiente").hexdigest()
    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            reg = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(tok),
            )
            ev = reg.json()["evidence_id"]
            ver = await client.post(f"/evidence/{ev}/verify", headers=au.bearer(tok))
            assert ver.status_code == 200
            assert ver.json()["verified"] is False
            assert ver.json()["actual_sha256"] is None


async def _enroll_occ(client) -> None:
    await client.post("/me/enrollment", json={"code": "CODE-P10"}, headers=au.bearer(_occ()))


# el router se monta vía create_app; la referencia evita el import sin usar.
_ = mobile_incident_router
