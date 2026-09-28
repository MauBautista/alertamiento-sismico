"""POST /incidents/{id}/dictamen-request (T-1.48): solicitud auditada en el
timeline, con idempotencia suave (409 mientras haya una solicitud sin dictamen
FIRMADO posterior)."""

from __future__ import annotations

import uuid

import pytest

import auth_utils as au

pytestmark = pytest.mark.usefixtures("base_data")


def _hdr(role: str = "tenant_admin", *, tenant: str = au.DB_TENANT_PRIV):
    return au.bearer(au.make_token(role, tenant=tenant, user_id=str(uuid.uuid4())))


async def test_request_creates_action_201(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/dictamen-request",
        headers=_hdr(),
        json={"note": "  revisar grieta poniente  "},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "dictamen_request"
    assert body["incident_id"] == iid
    assert body["payload"]["note"] == "revisar grieta poniente"
    assert body["payload"]["requested_by"]

    acts = await client.get(f"/incidents/{iid}/actions", headers=_hdr())
    assert "dictamen_request" in [a["kind"] for a in acts.json()]


async def test_second_request_while_pending_is_409(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r1 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r1.status_code == 201
    r2 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r2.status_code == 409


async def test_after_signed_dictamen_can_request_again(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r1 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r1.status_code == 201
    # El inspector firma DESPUÉS de la solicitud ⇒ la solicitud queda atendida.
    await make_dictamen(au.DB_TENANT_PRIV, iid, signed_by=str(uuid.uuid4()))
    r2 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r2.status_code == 201


async def test_la_firma_del_SISTEMA_no_atiende_la_solicitud(
    client, make_incident, make_dictamen
) -> None:
    """[F3 · D-43] La brigada pidió que viniera un INSPECTOR: el VERDE que firma el
    sistema no es esa inspección. La solicitud sigue pendiente (409 al repetirla)."""
    from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID

    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r1 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r1.status_code == 201
    await make_dictamen(
        au.DB_TENANT_PRIV,
        iid,
        status="normal_operation",
        band="verde",
        signature_kind="system",
        signed_by=SYSTEM_DICTAMEN_SIGNER_UUID,
    )
    r2 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r2.status_code == 409, r2.text


async def test_una_CONFIRMACION_atiende_la_solicitud_y_se_puede_volver_a_escalar(
    client, make_incident, make_dictamen
) -> None:
    """[D-49 · R3 · R5] La confirmación de la brigada atiende la escalada para el
    reingreso, así que también la atiende aquí: con dos criterios distintos, tras una
    confirmación el reingreso quedaba autorizado y NADIE podía volver a escalar (409
    por una solicitud que el reingreso ya daba por atendida)."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r1 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r1.status_code == 201
    await make_dictamen(
        au.DB_TENANT_PRIV,
        iid,
        status="inhabit_monitor",
        band="amarillo",
        signature_kind="confirmation",
        signed_by=str(uuid.uuid4()),
    )
    r2 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r2.status_code == 201, r2.text


async def test_la_firma_del_INSPECTOR_si_atiende_la_solicitud(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r1 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r1.status_code == 201
    await make_dictamen(
        au.DB_TENANT_PRIV, iid, signed_by=str(uuid.uuid4()), signature_kind="inspector"
    )
    r2 = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(), json={})
    assert r2.status_code == 201, r2.text


@pytest.mark.parametrize("role", ["gov_operator", "inspector", "takab_support"])
async def test_request_forbidden_roles(client, make_incident, role: str) -> None:
    """gov queda fuera a propósito: la RLS actions_insert le impide insertar —
    concederle la acción pintaría un botón que siempre da 403."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(f"/incidents/{iid}/dictamen-request", headers=_hdr(role), json={})
    assert r.status_code == 403


async def test_request_cross_tenant_is_404(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/dictamen-request", headers=_hdr(tenant=au.DB_TENANT_PRIV2), json={}
    )
    assert r.status_code == 404
