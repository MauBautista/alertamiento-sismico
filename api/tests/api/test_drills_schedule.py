"""Simulacro ARMADO, historial paginado y acuse por sitio (T-2.48).

Extiende el arnés de ``test_drills.py`` (fleet comandable + publisher fake +
claves HMAC inline). Lo que se verifica aquí es distinto del T-1.60:

- la rama de AGENDA deja constancia de **a qué sitios apunta** (``drill_sites``
  con ``command_id NULL``): sin eso, un simulacro programado no dice a quién iba
  dirigido y el banner armado no puede precargar nada;
- ``POST /drills/{id}/cancel`` cancela lo que aún no ocurrió y **jamás
  "descancela"** lo que ya ocurrió;
- ejecutar un armado es un acto humano (``from_scheduled``) que consume la
  agenda — el banner armado deja de mentir en cuanto el simulacro corrió;
- ``SIN GABINETE COMANDABLE`` (``commandable=False``) es un hecho distinto de
  ``SIN ACUSE``: colapsarlos haría creer que un sitio ignoró el simulacro.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router
from takab_api.routers.drills import router as drills_router
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)

# Sitio del tenant A SIN gabinete: la agenda puede apuntarle (el hardware puede
# llegar después) y su ausencia de comando NO es un "sin acuse".
SITE_NOGW = "7c300000-0000-0000-0000-0000000009f0"


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(drills_router)
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


@pytest.fixture
async def site_sin_gateway(base_data) -> str:
    """Sitio del tenant A sin ningún gabinete (ni retirado)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-NOGW', 'Sitio sin gabinete', "
                "ST_SetSRID(ST_MakePoint(-99.10, 19.40), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_NOGW, "t": au.DB_TENANT_PRIV},
        )
    return SITE_NOGW


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


def _future(minutes: int = 30) -> str:
    return (datetime.now(tz=UTC) + timedelta(minutes=minutes)).isoformat()


async def _row(drill_id: str) -> dict:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            (
                await conn.execute(
                    text(
                        "SELECT stopped_at, stop_reason, scheduled_at FROM drills "
                        "WHERE drill_id = CAST(:d AS uuid)"
                    ),
                    {"d": drill_id},
                )
            )
            .mappings()
            .one()
        )


# --- AGENDA: constancia de a quién apunta -------------------------------------


async def test_agenda_persiste_los_sitios_apuntados_sin_comando(
    client, gateway, site_sin_gateway, publisher
):
    r = await client.post(
        "/drills",
        json={
            "site_ids": [au.DB_SITE_PRIV, SITE_NOGW],
            "duration_s": 180,
            "scheduled_at": _future(),
            "note": "simulacro trimestral",
        },
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is False and body["scheduled_at"] is not None
    # Una agenda JAMÁS emite comandos (regla de oro 8: ejecutar es un acto humano).
    assert publisher.published == []

    sites = {s["site_id"]: s for s in body["sites"]}
    assert set(sites) == {au.DB_SITE_PRIV, SITE_NOGW}
    assert all(s["command_id"] is None for s in sites.values())
    # Y el registro dice, por sitio, si hay a quién mandarle el comando.
    assert sites[au.DB_SITE_PRIV]["commandable"] is True
    assert sites[SITE_NOGW]["commandable"] is False

    # La lista lo relee de la DB (no es un artefacto de la respuesta del POST).
    listed = await client.get("/drills?kind=scheduled", headers=_token())
    row = next(d for d in listed.json()["items"] if d["drill_id"] == body["drill_id"])
    assert {s["site_id"] for s in row["sites"]} == {au.DB_SITE_PRIV, SITE_NOGW}


async def test_agenda_con_sitio_ajeno_o_inexistente_404(client, gateway):
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV2], "scheduled_at": _future()},
        headers=_token(),
    )
    assert r.status_code == 404


async def test_agenda_sin_site_ids_apunta_a_los_comandables(client, gateway, site_sin_gateway):
    r = await client.post("/drills", json={"scheduled_at": _future()}, headers=_token())
    assert r.status_code == 201, r.text
    targets = {s["site_id"] for s in r.json()["sites"]}
    assert au.DB_SITE_PRIV in targets
    assert SITE_NOGW not in targets


# --- CANCELAR -----------------------------------------------------------------


async def test_cancel_marca_la_agenda_y_no_emite_nada(client, gateway, publisher):
    created = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "scheduled_at": _future()},
        headers=_token(),
    )
    drill_id = created.json()["drill_id"]

    r = await client.post(f"/drills/{drill_id}/cancel", headers=_token())
    assert r.status_code == 200, r.text
    assert r.json()["stop_reason"] == "cancelled"
    assert r.json()["active"] is False
    assert publisher.published == []
    assert (await _row(drill_id))["stopped_at"] is not None

    # Ya no aparece como armado pendiente.
    scheduled = await client.get("/drills?kind=scheduled", headers=_token())
    row = next(d for d in scheduled.json()["items"] if d["drill_id"] == drill_id)
    assert row["stop_reason"] == "cancelled"


async def test_cancelar_un_simulacro_ya_ejecutado_no_lo_descancela(client, gateway, publisher):
    """Un simulacro que YA CORRIÓ no se cancela: cancelarlo sería reescribir la
    evidencia de que sonó en los edificios."""
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120}, headers=_token()
    )
    drill_id = created.json()["drill_id"]

    r = await client.post(f"/drills/{drill_id}/cancel", headers=_token())
    assert r.status_code == 409
    after = await _row(drill_id)
    assert after["stopped_at"] is None and after["stop_reason"] is None

    # Y tampoco tras terminarlo: el motivo 'manual' se conserva.
    await client.post(f"/drills/{drill_id}/stop", headers=_token())
    again = await client.post(f"/drills/{drill_id}/cancel", headers=_token())
    assert again.status_code == 409
    assert (await _row(drill_id))["stop_reason"] == "manual"


async def test_cancel_de_una_agenda_ya_ejecutada_conserva_el_motivo(client, gateway, publisher):
    agenda = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "scheduled_at": _future(minutes=1)},
        headers=_token(),
    )
    agenda_id = agenda.json()["drill_id"]
    ran = await client.post("/drills", json={"from_scheduled": agenda_id}, headers=_token())
    assert ran.status_code == 201, ran.text

    r = await client.post(f"/drills/{agenda_id}/cancel", headers=_token())
    assert r.status_code == 200
    assert r.json()["stop_reason"] == "executed"
    assert (await _row(agenda_id))["stop_reason"] == "executed"


async def test_cancel_es_idempotente(client, gateway):
    created = await client.post("/drills", json={"scheduled_at": _future()}, headers=_token())
    drill_id = created.json()["drill_id"]
    first = await client.post(f"/drills/{drill_id}/cancel", headers=_token())
    stopped_at = first.json()["stopped_at"]
    second = await client.post(f"/drills/{drill_id}/cancel", headers=_token())
    assert second.status_code == 200
    assert second.json()["stopped_at"] == stopped_at


async def test_cancel_404_y_403(client, gateway):
    missing = await client.post(
        "/drills/00000000-0000-0000-0000-0000000000ff/cancel", headers=_token()
    )
    assert missing.status_code == 404

    created = await client.post("/drills", json={"scheduled_at": _future()}, headers=_token())
    drill_id = created.json()["drill_id"]
    forbidden = await client.post(f"/drills/{drill_id}/cancel", headers=_token("soc_operator"))
    assert forbidden.status_code == 403
    assert (await _row(drill_id))["stopped_at"] is None


# --- EJECUTAR UN ARMADO (un clic humano) --------------------------------------


async def test_from_scheduled_ejecuta_y_consume_la_agenda(client, gateway, publisher):
    agenda = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 90, "scheduled_at": _future(minutes=1)},
        headers=_token(),
    )
    agenda_id = agenda.json()["drill_id"]

    ran = await client.post("/drills", json={"from_scheduled": agenda_id}, headers=_token())
    assert ran.status_code == 201, ran.text
    body = ran.json()
    assert body["drill_id"] != agenda_id
    assert body["active"] is True and body["scheduled_at"] is None
    # Hereda los sitios y la duración de lo programado (botón "precargado").
    assert body["duration_s"] == 90
    assert [s["site_id"] for s in body["sites"]] == [au.DB_SITE_PRIV]
    assert body["sites"][0]["command_id"] is not None
    assert publisher.published[0][1]["payload"]["action"] == "drill_start"

    # La agenda queda consumida: el banner armado deja de anunciarla.
    after = await _row(agenda_id)
    assert after["stop_reason"] == "executed" and after["stopped_at"] is not None
    # Y la ejecución quedó auditada contra la agenda.
    engine = get_engine()
    async with engine.begin() as conn:
        verbs = (
            (
                await conn.execute(
                    text("SELECT verb FROM audit_log WHERE object = :o"),
                    {"o": f"drill:{agenda_id}"},
                )
            )
            .scalars()
            .all()
        )
    assert "drill_executed" in verbs


async def test_from_scheduled_registra_los_sitios_sin_gabinete_sin_abortar(
    client, gateway, site_sin_gateway, publisher
):
    """Un sitio que perdió (o nunca tuvo) gabinete no puede tumbar el simulacro
    de los demás: queda registrado SIN comando y rotulado como no comandable."""
    agenda = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV, SITE_NOGW], "scheduled_at": _future()},
        headers=_token(),
    )
    ran = await client.post(
        "/drills", json={"from_scheduled": agenda.json()["drill_id"]}, headers=_token()
    )
    assert ran.status_code == 201, ran.text
    sites = {s["site_id"]: s for s in ran.json()["sites"]}
    assert sites[au.DB_SITE_PRIV]["command_id"] is not None
    assert sites[SITE_NOGW]["command_id"] is None
    assert sites[SITE_NOGW]["commandable"] is False
    assert len(publisher.published) == 1


async def test_from_scheduled_de_una_agenda_consumida_409(client, gateway):
    agenda = await client.post("/drills", json={"scheduled_at": _future()}, headers=_token())
    agenda_id = agenda.json()["drill_id"]
    await client.post(f"/drills/{agenda_id}/cancel", headers=_token())
    r = await client.post("/drills", json={"from_scheduled": agenda_id}, headers=_token())
    assert r.status_code == 409


async def test_from_scheduled_sobre_un_simulacro_ejecutado_409(client, gateway):
    ran = await client.post("/drills", json={"duration_s": 60}, headers=_token())
    r = await client.post(
        "/drills", json={"from_scheduled": ran.json()["drill_id"]}, headers=_token()
    )
    assert r.status_code == 409


async def test_from_scheduled_inexistente_404(client, gateway):
    r = await client.post(
        "/drills",
        json={"from_scheduled": "00000000-0000-0000-0000-0000000000ff"},
        headers=_token(),
    )
    assert r.status_code == 404


async def test_from_scheduled_con_scheduled_at_es_422(client, gateway):
    r = await client.post(
        "/drills",
        json={"from_scheduled": "00000000-0000-0000-0000-0000000000ff", "scheduled_at": _future()},
        headers=_token(),
    )
    assert r.status_code == 422


# --- HISTORIAL: keyset + filtro por tipo --------------------------------------


async def test_list_drills_pagina_por_keyset_sin_solapes(client, gateway):
    ids = []
    for _ in range(3):
        created = await client.post("/drills", json={"duration_s": 60}, headers=_token())
        ids.append(created.json()["drill_id"])

    first = await client.get("/drills?limit=2", headers=_token())
    assert first.status_code == 200
    page1 = first.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    second = await client.get(f"/drills?limit=2&cursor={page1['next_cursor']}", headers=_token())
    page2 = second.json()
    seen = [d["drill_id"] for d in page1["items"]] + [d["drill_id"] for d in page2["items"]]
    assert len(seen) == len(set(seen)) == 3
    assert set(seen) == set(ids)
    assert page2["next_cursor"] is None


async def test_list_drills_cursor_corrupto_400(client, gateway):
    r = await client.get("/drills?cursor=no-es-un-cursor", headers=_token())
    assert r.status_code == 400


async def test_list_drills_filtra_por_kind(client, gateway):
    ran = await client.post("/drills", json={"duration_s": 60}, headers=_token())
    agenda = await client.post("/drills", json={"scheduled_at": _future()}, headers=_token())

    executed = await client.get("/drills?kind=executed", headers=_token())
    assert [d["drill_id"] for d in executed.json()["items"]] == [ran.json()["drill_id"]]

    scheduled = await client.get("/drills?kind=scheduled", headers=_token())
    assert [d["drill_id"] for d in scheduled.json()["items"]] == [agenda.json()["drill_id"]]

    every = await client.get("/drills", headers=_token())
    assert len(every.json()["items"]) == 2


async def test_list_drills_kind_invalido_422(client, gateway):
    r = await client.get("/drills?kind=inventado", headers=_token())
    assert r.status_code == 422


async def test_el_acuse_distingue_sin_gabinete_de_sin_acuse(client, gateway, publisher):
    """El sitio comandado sin ack todavía es ``pending``; nunca se confunde con
    un sitio al que no había a quién mandarle nada."""
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120}, headers=_token()
    )
    row = next(
        d
        for d in (await client.get("/drills", headers=_token())).json()["items"]
        if d["drill_id"] == created.json()["drill_id"]
    )
    site = row["sites"][0]
    assert site["commandable"] is True
    assert site["command_status"] == "pending" and site["ack"] is None
