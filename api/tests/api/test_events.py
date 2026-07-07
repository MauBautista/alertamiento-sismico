"""GET /events (datos de red) + /events/{id} con quorum_votes y delta_s (B2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import auth_utils as au
from tests.api.conftest import SENSOR_PRIV, SENSOR_PRIV2

_USER = "abcabcab-0000-0000-0000-0000000000e1"
_BASE = datetime(2026, 6, 2, 8, 0, 0, tzinfo=UTC)


def _token(role: str = "soc_operator") -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=_USER))


async def test_list_events_desc(client, make_event) -> None:
    eids = [
        await make_event(event_id=f"EVT-LIST-{i}", detected_at=_BASE + timedelta(minutes=i))
        for i in range(3)
    ]
    resp = await client.get("/events", headers=_token())
    assert resp.status_code == 200, resp.text
    got = [it["event_id"] for it in resp.json()["items"]]
    # más reciente primero; todos presentes
    assert got[: len(eids)] == list(reversed(eids))


async def test_any_authenticated_role_can_read_events(client, make_event) -> None:
    """Los eventos son datos de red: incluso un rol sin Consola (brigadista) los lee."""
    eid = await make_event(event_id="EVT-NETDATA-1")
    resp = await client.get("/events", headers=_token(role="brigadista"))
    assert resp.status_code == 200
    assert any(it["event_id"] == eid for it in resp.json()["items"])


async def test_event_detail_includes_quorum_votes(client, make_event, make_vote) -> None:
    eid = await make_event(event_id="EVT-QUORUM-1", magnitude=5.4)
    await make_vote(eid, SENSOR_PRIV, pga_g=0.20, delta_s=0.0)
    await make_vote(eid, SENSOR_PRIV2, pga_g=0.11, delta_s=0.7)

    resp = await client.get(f"/events/{eid}", headers=_token())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_id"] == eid
    assert body["magnitude"] == 5.4
    votes = {v["sensor_id"]: v["delta_s"] for v in body["quorum_votes"]}
    assert votes[SENSOR_PRIV] == 0.0
    assert votes[SENSOR_PRIV2] == 0.7


async def test_missing_event_is_404(client, base_data) -> None:
    resp = await client.get("/events/EVT-DOES-NOT-EXIST", headers=_token())
    assert resp.status_code == 404
