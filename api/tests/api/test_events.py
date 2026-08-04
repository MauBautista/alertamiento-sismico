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


async def test_missing_event_is_404(client) -> None:
    resp = await client.get("/events/EVT-DOES-NOT-EXIST", headers=_token())
    assert resp.status_code == 404


# ---- filtro por conjunto de ids (T-2.39) -------------------------------------
#
# La pantalla de evaluación enriquecía sus filas con los 50 eventos más recientes.
# Al cargar la segunda página, incidentes con evento perfectamente existente perdían
# magnitud, epicentro y nodos SIN decir por qué. Ahora se piden los que hacen falta.


async def test_ids_devuelve_exactamente_ese_conjunto(client, make_event) -> None:
    a = await make_event(event_id="EVT-IDS-A")
    b = await make_event(event_id="EVT-IDS-B")
    await make_event(event_id="EVT-IDS-C")

    resp = await client.get(f"/events?ids={a},{b}", headers=_token())
    assert resp.status_code == 200, resp.text
    assert {e["event_id"] for e in resp.json()["items"]} == {a, b}


async def test_ids_no_pagina_por_keyset(client, make_event) -> None:
    """Con `ids` la consulta es una búsqueda, no un recorrido: sin cursor de vuelta."""
    ids = [await make_event(event_id=f"EVT-IDS-{i}") for i in range(3)]
    resp = await client.get(f"/events?ids={','.join(ids)}", headers=_token())
    assert resp.json()["next_cursor"] is None


async def test_ids_ignora_los_inexistentes_sin_fallar(client, make_event) -> None:
    real = await make_event(event_id="EVT-IDS-REAL")
    resp = await client.get(f"/events?ids={real},EVT-NO-EXISTE", headers=_token())
    assert resp.status_code == 200
    assert [e["event_id"] for e in resp.json()["items"]] == [real]


async def test_ids_vacio_devuelve_vacio_no_todo(client, make_event) -> None:
    """Una lista vacía NO puede degradar a "dame el catálogo entero"."""
    await make_event(event_id="EVT-IDS-X")
    resp = await client.get("/events?ids=", headers=_token())
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_demasiados_ids_es_422(client) -> None:
    many = ",".join(f"EVT-{i}" for i in range(201))
    resp = await client.get(f"/events?ids={many}", headers=_token())
    assert resp.status_code == 422


# ---- nombre de la estación en los votos (T-2.39) ------------------------------


async def test_los_votos_traen_el_codigo_de_la_estacion(client, make_event, make_vote) -> None:
    """Ocho hex de un uuid no le dicen nada a nadie en una sala de crisis."""
    eid = await make_event(event_id="EVT-VOTE-NAME")
    await make_vote(eid, SENSOR_PRIV)

    resp = await client.get(f"/events/{eid}", headers=_token())
    assert resp.status_code == 200, resp.text
    vote = resp.json()["quorum_votes"][0]
    assert vote["site_code"] == "B2SA"
    assert vote["station_serial"] is None or isinstance(vote["station_serial"], str)


async def test_un_voto_de_otra_red_no_inventa_etiqueta(client, make_event, make_vote) -> None:
    """La RLS oculta el sensor ajeno ⇒ nulos. Es el HECHO: la consola dirá OTRA RED."""
    eid = await make_event(event_id="EVT-VOTE-FOREIGN")
    await make_vote(eid, SENSOR_PRIV2)

    resp = await client.get(f"/events/{eid}", headers=_token())
    vote = resp.json()["quorum_votes"][0]
    assert vote["site_code"] is None
    assert vote["station_serial"] is None
