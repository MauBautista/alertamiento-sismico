"""GET /incidents (lista keyset + filtros), detalle, actions, RLS y authz (B2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import auth_utils as au

_USER = "abcabcab-0000-0000-0000-0000000000a1"
_BASE = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_USER))


async def test_list_keyset_pages_are_stable(client, make_incident) -> None:
    ids: list[str] = []
    for i in range(5):
        ids.append(
            await make_incident(
                au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_BASE + timedelta(minutes=i)
            )
        )

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/incidents", params=params, headers=_token())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        opened = [it["opened_at"] for it in body["items"]]
        assert opened == sorted(opened, reverse=True), "cada página va opened_at desc"
        seen.extend(it["incident_id"] for it in body["items"])
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert pages < 10, "no debe paginar indefinidamente"

    assert len(seen) == len(set(seen)) == 5, "sin solapes ni faltantes entre páginas"
    assert set(seen) == set(ids)
    # el más nuevo primero
    assert seen[0] == ids[-1]


async def test_detail_and_missing_is_404(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, severity="critical")
    ok = await client.get(f"/incidents/{iid}", headers=_token())
    assert ok.status_code == 200
    assert ok.json()["incident_id"] == iid
    assert ok.json()["severity"] == "critical"

    missing = await client.get(f"/incidents/{uuid4()}", headers=_token())
    assert missing.status_code == 404


async def test_cross_tenant_incident_is_invisible(client, make_incident) -> None:
    """Un incidente de tenant B no aparece ni es accesible con token de tenant A (RLS)."""
    b_iid = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)

    detail = await client.get(f"/incidents/{b_iid}", headers=_token())
    assert detail.status_code == 404

    listing = await client.get("/incidents", headers=_token())
    assert listing.status_code == 200
    assert all(it["incident_id"] != b_iid for it in listing.json()["items"])


async def test_filters_state_severity_and_event_prefix(client, make_incident, make_event) -> None:
    await make_event(event_id="EVT-QTEST-0001")
    match = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        severity="critical",
        state="acked",
        event_id="EVT-QTEST-0001",
    )
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, severity="info", state="open")

    by_state = await client.get("/incidents", params={"state": "acked"}, headers=_token())
    assert {it["incident_id"] for it in by_state.json()["items"]} == {match}

    by_sev = await client.get("/incidents", params={"severity": "critical"}, headers=_token())
    assert {it["incident_id"] for it in by_sev.json()["items"]} == {match}

    by_q = await client.get("/incidents", params={"q": "EVT-QTEST"}, headers=_token())
    assert {it["incident_id"] for it in by_q.json()["items"]} == {match}

    bad = await client.get("/incidents", params={"state": "bogus"}, headers=_token())
    assert bad.status_code == 400


async def test_actions_timeline(client, make_incident, make_action) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await make_action(iid, au.DB_TENANT_PRIV, kind="siren_on", actor="edge:A")
    await make_action(iid, au.DB_TENANT_PRIV, kind="ack", actor=f"user:{_USER}")

    resp = await client.get(f"/incidents/{iid}/actions", headers=_token())
    assert resp.status_code == 200
    kinds = [a["kind"] for a in resp.json()]
    assert kinds == ["siren_on", "ack"], "orden cronológico ascendente por ts"

    missing = await client.get(f"/incidents/{uuid4()}/actions", headers=_token())
    assert missing.status_code == 404


async def test_mobile_only_role_forbidden(client, make_incident) -> None:
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    resp = await client.get("/incidents", headers=_token(role="brigadista"))
    assert resp.status_code == 403
