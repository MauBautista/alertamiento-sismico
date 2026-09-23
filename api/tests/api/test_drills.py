"""POST/GET /drills (T-1.60): simulacro institucional — jamás toca incidents.

Reutiliza el arnés del command service (fleet con gateway comandable, publisher
fake, claves HMAC inline): el drill emite comandos firmados REALES por sitio.
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

# Arnés compartido con el router de comandos (fixtures gateway/publisher).
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)


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


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _count(sql: str) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (await conn.execute(text(sql))).scalar_one()


async def test_post_drills_emite_drill_start_firmado_por_sitio(client, gateway, publisher):
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120, "note": "simulacro trimestral"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True and body["duration_s"] == 120
    assert len(body["sites"]) == 1
    assert body["sites"][0]["command_id"] is not None
    # El envelope firmado salió con la duración DENTRO del payload canónico.
    assert len(publisher.published) == 1
    envelope = publisher.published[0][1]
    assert envelope["payload"]["action"] == "drill_start"
    assert envelope["payload"]["duration_s"] == 120
    assert envelope["payload"]["event_id"] == f"DRILL-{body['drill_id']}"


async def test_un_drill_jamas_crea_incidentes(client, gateway, publisher):
    before = await _count("SELECT count(*) FROM incidents")
    r = await client.post("/drills", json={"duration_s": 60}, headers=_token())
    assert r.status_code == 201
    assert await _count("SELECT count(*) FROM incidents") == before
    assert await _count("SELECT count(*) FROM incident_actions") == 0
    assert await _count("SELECT count(*) FROM dictamens") == 0


@pytest.mark.parametrize("role", ["soc_operator", "gov_operator", "inspector", "building_admin"])
async def test_roles_sin_drill_start_403(client, gateway, role):
    r = await client.post("/drills", json={"duration_s": 60}, headers=_token(role))
    assert r.status_code == 403


async def test_tenant_sin_gabinetes_comandables_409(client, base_data):
    # El tenant B solo tiene sitios SIN gateway comandable (base_data).
    r = await client.post(
        "/drills", json={"duration_s": 60}, headers=_token(tenant=au.DB_TENANT_PRIV2)
    )
    assert r.status_code == 409


async def test_registro_visible_para_gov_y_active_para_consola(client, gateway, publisher):
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 300}, headers=_token()
    )
    drill_id = created.json()["drill_id"]

    # gov_operator LEE el registro de su ámbito (RLS gov_shared: tenant privado
    # ajeno ⇒ lista vacía, jamás 403 — el endpoint es de consola).
    gov = await client.get("/drills", headers=_token("gov_operator", tenant=au.DB_TENANT_GOV))
    assert gov.status_code == 200

    # El propio tenant ve su drill con el acuse por sitio (derivado de commands).
    mine = await client.get("/drills", headers=_token())
    items = mine.json()["items"]
    assert any(d["drill_id"] == drill_id for d in items)
    row = next(d for d in items if d["drill_id"] == drill_id)
    assert row["sites"][0]["command_status"] == "pending"  # aún sin ack del edge

    # El banner de la consola: cualquier rol del SOC ve el drill activo.
    active = await client.get("/drills/active", headers=_token("soc_operator"))
    assert active.status_code == 200
    assert active.json()["drill"]["drill_id"] == drill_id


async def test_stop_marca_fin_y_publica_drill_stop(client, gateway, publisher):
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 300}, headers=_token()
    )
    drill_id = created.json()["drill_id"]
    publisher.published.clear()

    stopped = await client.post(f"/drills/{drill_id}/stop", headers=_token())
    assert stopped.status_code == 200, stopped.text
    body = stopped.json()
    assert body["active"] is False and body["stopped_at"] is not None
    assert len(publisher.published) == 1
    assert publisher.published[0][1]["payload"]["action"] == "drill_stop"

    # Idempotente: un segundo stop devuelve el drill sin re-publicar.
    again = await client.post(f"/drills/{drill_id}/stop", headers=_token())
    assert again.status_code == 200
    assert len(publisher.published) == 1

    # Y el banner se apaga.
    active = await client.get("/drills/active", headers=_token("soc_operator"))
    assert active.json()["drill"] is None


async def _sql(sql: str, **params) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def test_el_aborto_del_gabinete_se_expone_por_sitio_y_cierra_el_simulacro(
    client, gateway, publisher
):
    """[T-6.17] El gabinete acusó (ejecuta) y una alerta real lo cortó: el sitio
    lleva `aborted_at`/`abort_reason`, el simulacro sale `aborted` con
    `stop_reason='aborted'` y deja de ser el activo. Medido el 2026-09-06: sin
    esto el SOC seguía anunciando «SIMULACRO EN CURSO» sobre un gabinete callado."""
    r = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 300}, headers=_token()
    )
    assert r.status_code == 201, r.text
    drill_id = r.json()["drill_id"]
    command_id = r.json()["sites"][0]["command_id"]

    # 1) Acuse de arranque: el sitio EJECUTA y el simulacro lo cuenta.
    await _sql(
        "UPDATE commands SET status = 'acked', acked_at = now() WHERE command_id = :c",
        c=command_id,
    )
    active = (await client.get("/drills/active", headers=_token())).json()["drill"]
    assert active is not None and active["drill_id"] == drill_id
    assert active["executing"] == 1
    assert active["aborted"] is False
    assert active["sites"][0]["aborted_at"] is None

    # 2) Aborto por alerta real (lo que deja la ingesta del segundo acuse).
    await _sql(
        "UPDATE drill_sites SET aborted_at = now(), abort_reason = 'SASMEX real' "
        "WHERE drill_id = :d AND site_id = :s",
        d=drill_id,
        s=au.DB_SITE_PRIV,
    )
    await _sql(
        "UPDATE drills SET stopped_at = now(), stop_reason = 'aborted' WHERE drill_id = :d",
        d=drill_id,
    )
    assert (await client.get("/drills/active", headers=_token())).json()["drill"] is None
    items = (await client.get("/drills", headers=_token())).json()["items"]
    row = next(d for d in items if d["drill_id"] == drill_id)
    assert row["active"] is False
    assert row["aborted"] is True
    assert row["abort_reason"] == "SASMEX real"
    assert row["stop_reason"] == "aborted"
    # El acuse sigue en `acked` (sí sonó), pero ya no cuenta como EJECUTANDO.
    assert row["sites"][0]["command_status"] == "acked"
    assert row["sites"][0]["aborted_at"] is not None
    assert row["sites"][0]["abort_reason"] == "SASMEX real"
    assert row["executing"] == 0


# --- [A-016 · T-8.07] un rol interno NOMBRA al cliente ---------------------------
#
# La consola decía «SIN SELECCIÓN ⇒ TODOS LOS SITIOS … DEL TENANT», pero para un
# rol interno TAKAB la RLS abre los gabinetes de TODOS los clientes: el superadmin
# que no marcaba ningún sitio mandaba el simulacro a cada edificio de la
# plataforma. Y la fila del simulacro se escribía en el tenant DEL TOKEN (TAKAB),
# así que el cliente dueño de los edificios ni siquiera la veía en su registro.
# Mismo contrato que `resolve_write_tenant`: el interno no escribe por omisión.

#: El superadmin vive en SU tenant, que no es el del cliente al que apunta.
_TENANT_DEL_INTERNO = au.DB_TENANT_GOV


def _superadmin() -> dict[str, str]:
    return _token("takab_superadmin", tenant=_TENANT_DEL_INTERNO)


async def _escalar(sql: str, **params) -> object:
    async with get_engine().begin() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


def _dentro_de_dos_dias() -> str:
    return (datetime.now(tz=UTC) + timedelta(days=2)).isoformat()


async def test_superadmin_sin_seleccion_NO_lanza_a_todos_los_clientes(client, gateway, publisher):
    r = await client.post("/drills", json={"duration_s": 60}, headers=_superadmin())
    assert r.status_code == 400, r.text
    assert "cliente" in r.json()["detail"]
    # Ni un comando firmado, ni una fila: nada salió hacia ningún edificio.
    assert publisher.published == []
    assert await _count("SELECT count(*) FROM drills") == 0


async def test_superadmin_escribe_el_simulacro_en_el_cliente_de_los_sitios(
    client, gateway, publisher
):
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 60},
        headers=_superadmin(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tenant_id"] == au.DB_TENANT_PRIV
    assert len(publisher.published) == 1
    # La fila por sitio también es del cliente, no de TAKAB.
    assert (
        await _escalar(
            "SELECT count(*) FROM drill_sites WHERE drill_id = CAST(:d AS uuid) "
            "AND tenant_id = CAST(:t AS uuid)",
            d=body["drill_id"],
            t=au.DB_TENANT_PRIV,
        )
        == 1
    )
    # Y el cliente dueño de los edificios lo ve en SU registro (evidencia).
    suyo = await client.get("/drills", headers=_token())
    assert any(d["drill_id"] == body["drill_id"] for d in suyo.json()["items"])


async def test_superadmin_con_plantilla_lanza_solo_en_el_cliente_de_la_plantilla(
    client, gateway, publisher
):
    # Plantilla del tenant A SIN sitios = «todos los comandables». Para un interno
    # eso tiene que ser todos los DE ESE CLIENTE, no de la plataforma.
    creada = await client.post(
        "/drill-templates", json={"name": "T-8.07 todos", "duration_s": 60}, headers=_token()
    )
    assert creada.status_code == 201, creada.text
    plantilla = creada.json()["template_id"]
    try:
        r = await client.post("/drills", json={"from_template": plantilla}, headers=_superadmin())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"] == au.DB_TENANT_PRIV
        assert body["sites"], "la plantilla «todos» no apuntó a nada"
        assert (
            await _escalar(
                "SELECT count(*) FROM drill_sites ds JOIN sites s USING (site_id) "
                "WHERE ds.drill_id = CAST(:d AS uuid) AND s.tenant_id <> CAST(:t AS uuid)",
                d=body["drill_id"],
                t=au.DB_TENANT_PRIV,
            )
            == 0
        )
    finally:
        await client.delete(f"/drill-templates/{plantilla}", headers=_token())


async def test_superadmin_no_mezcla_clientes_en_un_simulacro(client, gateway):
    # La agenda puede apuntar a sitios sin gabinete, así que aquí dos clientes
    # distintos entran en la misma lista sin montar un segundo gabinete.
    r = await client.post(
        "/drills",
        json={
            "site_ids": [au.DB_SITE_PRIV, au.DB_SITE_PRIV2],
            "scheduled_at": _dentro_de_dos_dias(),
        },
        headers=_superadmin(),
    )
    assert r.status_code == 422, r.text
    assert "cliente" in r.json()["detail"]
    assert await _count("SELECT count(*) FROM drills") == 0


async def test_superadmin_agenda_sin_seleccion_tambien_exige_cliente(client, gateway):
    r = await client.post(
        "/drills", json={"scheduled_at": _dentro_de_dos_dias()}, headers=_superadmin()
    )
    assert r.status_code == 400, r.text
    assert await _count("SELECT count(*) FROM drills") == 0


async def test_superadmin_agenda_con_sitios_queda_en_el_cliente(client, gateway):
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV2], "scheduled_at": _dentro_de_dos_dias()},
        headers=_superadmin(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["tenant_id"] == au.DB_TENANT_PRIV2


async def test_el_rol_de_cliente_sigue_igual_sin_seleccion(client, gateway, publisher):
    # El contrato del tenant_admin NO cambia: sin selección, los comandables DE SU
    # cliente (la RLS ya lo acota) y la fila en su tenant.
    r = await client.post("/drills", json={"duration_s": 60}, headers=_token())
    assert r.status_code == 201, r.text
    assert r.json()["tenant_id"] == au.DB_TENANT_PRIV


# --- [A-016 · T-8.07] lo que un interno guardó ANTES: el cliente lo dicen los SITIOS
#
# Antes de A-016 un rol interno escribía agendas y plantillas en el tenant DEL
# TOKEN (el de TAKAB) aunque apuntaran a edificios de un cliente, y
# `POST /drill-templates` lo sigue haciendo. Si el cliente del simulacro sale de
# la FILA y no de sus sitios, los gabinetes del cliente real pasan por
# «inalcanzables» y el 409 manda a arreglar un inventario que no está roto —el
# mismo error que el comentario de T-5.13 prohíbe—. Se siembran a mano porque la
# API de simulacros ya no las crea así.

_USUARIO_INTERNO = "7e000000-0000-0000-0000-00000000e0e1"


async def _agenda_en_el_tenant_de_takab(site_ids: list[str]) -> str:
    async with get_engine().begin() as conn:
        drill_id = (
            await conn.execute(
                text(
                    "INSERT INTO drills (tenant_id, initiated_by, duration_s, note, scheduled_at) "
                    "VALUES (CAST(:t AS uuid), CAST(:u AS uuid), 120, 'agenda antigua', "
                    "now() + interval '2 days') RETURNING drill_id"
                ),
                {"t": _TENANT_DEL_INTERNO, "u": _USUARIO_INTERNO},
            )
        ).scalar_one()
        for site_id in site_ids:
            await conn.execute(
                text(
                    "INSERT INTO drill_sites (drill_id, site_id, tenant_id) "
                    "VALUES (CAST(:d AS uuid), CAST(:s AS uuid), CAST(:t AS uuid))"
                ),
                {"d": str(drill_id), "s": site_id, "t": _TENANT_DEL_INTERNO},
            )
    return str(drill_id)


async def _plantilla_en_el_tenant_de_takab(nombre: str, site_ids: list[str]) -> str:
    async with get_engine().begin() as conn:
        template_id = (
            await conn.execute(
                text(
                    "INSERT INTO drill_templates (tenant_id, name, duration_s, created_by) "
                    "VALUES (CAST(:t AS uuid), :n, 90, CAST(:u AS uuid)) RETURNING template_id"
                ),
                {"t": _TENANT_DEL_INTERNO, "n": nombre, "u": _USUARIO_INTERNO},
            )
        ).scalar_one()
        for site_id in site_ids:
            await conn.execute(
                text(
                    "INSERT INTO drill_template_sites (template_id, site_id, tenant_id) "
                    "VALUES (CAST(:p AS uuid), CAST(:s AS uuid), CAST(:t AS uuid))"
                ),
                {"p": str(template_id), "s": site_id, "t": _TENANT_DEL_INTERNO},
            )
    return str(template_id)


async def _borrar_plantilla(template_id: str) -> None:
    await _sql("DELETE FROM drill_templates WHERE template_id = CAST(:p AS uuid)", p=template_id)


async def test_superadmin_ejecuta_su_agenda_antigua_en_el_cliente_de_sus_sitios(
    client, gateway, publisher
):
    agenda = await _agenda_en_el_tenant_de_takab([au.DB_SITE_PRIV])
    r = await client.post("/drills", json={"from_scheduled": agenda}, headers=_superadmin())
    assert r.status_code == 201, r.text
    body = r.json()
    # Sonó donde estaba programado, y quedó en el registro del cliente dueño.
    assert body["tenant_id"] == au.DB_TENANT_PRIV
    assert [s["commandable"] for s in body["sites"]] == [True]
    assert len(publisher.published) == 1
    # Y la agenda quedó consumida: el banner armado se apaga.
    assert (
        await _escalar("SELECT stop_reason FROM drills WHERE drill_id = CAST(:d AS uuid)", d=agenda)
        == "executed"
    )


async def test_superadmin_con_agenda_antigua_de_dos_clientes_no_mezcla(client, gateway, publisher):
    # DB_SITE_PRIV2 no tiene gabinete: aun así es de OTRO cliente, y registrarlo
    # bajo el simulacro del primero le enseñaría a ése un edificio ajeno.
    agenda = await _agenda_en_el_tenant_de_takab([au.DB_SITE_PRIV, au.DB_SITE_PRIV2])
    r = await client.post("/drills", json={"from_scheduled": agenda}, headers=_superadmin())
    assert r.status_code == 422, r.text
    assert "cliente" in r.json()["detail"]
    assert publisher.published == []


async def test_superadmin_con_plantilla_antigua_lanza_en_el_cliente_de_sus_sitios(
    client, gateway, publisher
):
    plantilla = await _plantilla_en_el_tenant_de_takab("T-8.07 antigua", [au.DB_SITE_PRIV])
    try:
        r = await client.post("/drills", json={"from_template": plantilla}, headers=_superadmin())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"] == au.DB_TENANT_PRIV
        assert [s["commandable"] for s in body["sites"]] == [True]
        assert body["duration_s"] == 90
        assert len(publisher.published) == 1
    finally:
        await _borrar_plantilla(plantilla)


async def test_superadmin_programa_desde_plantilla_antigua_en_el_cliente_de_sus_sitios(
    client, gateway
):
    plantilla = await _plantilla_en_el_tenant_de_takab("T-8.07 agenda", [au.DB_SITE_PRIV])
    try:
        r = await client.post(
            "/drills",
            json={"from_template": plantilla, "scheduled_at": _dentro_de_dos_dias()},
            headers=_superadmin(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # Antes: agenda con CERO sitios en el tenant de TAKAB, que nadie veía.
        assert body["tenant_id"] == au.DB_TENANT_PRIV
        assert [s["site_id"] for s in body["sites"]] == [au.DB_SITE_PRIV]
    finally:
        await _borrar_plantilla(plantilla)


async def test_superadmin_con_plantilla_todos_de_takab_dice_la_verdad(client, gateway, publisher):
    # «Todos los comandables» de una plantilla guardada en el tenant de TAKAB no
    # tiene cliente del que sacarlos: se rechaza, pero sin culpar al inventario.
    plantilla = await _plantilla_en_el_tenant_de_takab("T-8.07 todos antigua", [])
    try:
        r = await client.post("/drills", json={"from_template": plantilla}, headers=_superadmin())
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "plantilla" in detail and "cliente" in detail
        assert publisher.published == []
    finally:
        await _borrar_plantilla(plantilla)
