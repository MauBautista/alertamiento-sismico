"""T-2.03 · Núcleo móvil: enrolamiento, push/device, mobile-state, check-ins,
roster y daños — con los invariantes de seguridad de la spec §5/§8:

- R2: el alcance del occupant se resuelve SERVER-SIDE (enrolado o 404).
- Cruce de tenants DEBE fallar (RLS + mismo 404, sin filtración).
- Check-in delegado ≠ propio (via/verified_by) y solo con ``roster_read``.
- La derivación de ``phase`` usa datos REALES (incidente + tier + dictamen).
- Filas de AGENDA de drills jamás derivan activo (LO REAL GANA).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

ZONE_PRIV = "7d000000-0000-0000-0000-0000000000d1"
OCC_USER = "70000000-0000-0000-0000-00000000aa01"
OCC_USER_2 = "70000000-0000-0000-0000-00000000aa02"
BRIG_USER = "70000000-0000-0000-0000-00000000bb01"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    """Habilita el pool de ocupantes encima del entorno base (_auth_env)."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _occ(user_id: str = OCC_USER, tenant: str = au.DB_TENANT_PRIV) -> str:
    return au.occupant_token(tenant=tenant, user_id=user_id)


def _brig(site_scope: str = au.DB_SITE_PRIV) -> str:
    return au.make_token(
        "brigadista",
        tenant=au.DB_TENANT_PRIV,
        user_id=BRIG_USER,
        surface="mobile",
        site_scope=site_scope,
    )


async def _seed_zone_and_code(code: str = "CODE-P10", **code_over) -> None:
    """Zona (shelter) + código de alta vigente en el sitio PRIV."""
    engine = get_engine()
    params = {
        "zone": ZONE_PRIV,
        "tenant": au.DB_TENANT_PRIV,
        "site": au.DB_SITE_PRIV,
        "code": code,
        "expires_at": code_over.get("expires_at"),
        "max_uses": code_over.get("max_uses"),
        "active": code_over.get("active", True),
    }
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:zone, :tenant, :site, 'P10-A', 'P10', 'shelter') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            params,
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes "
                "(code, tenant_id, site_id, zone_id, expires_at, max_uses, active) "
                "VALUES (:code, :tenant, :site, :zone, :expires_at, :max_uses, :active)"
            ),
            params,
        )


async def _enroll(client, token: str, code: str = "CODE-P10"):
    return await client.post("/me/enrollment", json={"code": code}, headers=au.bearer(token))


@pytest.mark.anyio
async def test_enrolamiento_y_alcance_r2(base_data) -> None:
    """El occupant sin enrolar NO ve el sitio (404); tras consumir el código ve
    mobile-state con su zona/política. Un código vencido da el MISMO 404."""
    await _seed_zone_and_code()
    await _seed_zone_and_code(code="CODE-DEAD", expires_at=datetime.now(UTC) - timedelta(days=1))
    async with au.client_for(create_app()) as client:
        # sin enrolar: el sitio "no existe" para él (R2, sin filtración)
        resp = await client.get(f"/sites/{au.DB_SITE_PRIV}/mobile-state", headers=au.bearer(_occ()))
        assert resp.status_code == 404

        assert (await _enroll(client, _occ(), "CODE-DEAD")).status_code == 404
        resp = await _enroll(client, _occ())
        assert resp.status_code == 200
        body = resp.json()
        assert body["zone_name"] == "P10-A"
        assert body["evac_policy"] == "shelter"

        resp = await client.get(f"/sites/{au.DB_SITE_PRIV}/mobile-state", headers=au.bearer(_occ()))
        assert resp.status_code == 200
        state = resp.json()
        assert state["phase"] == "idle"
        assert state["my_zone"]["evac_policy"] == "shelter"
        assert state["incident"] is None


@pytest.mark.anyio
async def test_enrolamiento_cross_tenant_es_404(base_data) -> None:
    """Un código de OTRO tenant no existe para esta sesión (RLS)."""
    await _seed_zone_and_code()
    other = _occ(user_id=OCC_USER_2, tenant=au.DB_TENANT_PRIV2)
    async with au.client_for(create_app()) as client:
        assert (await _enroll(client, other)).status_code == 404


@pytest.mark.anyio
async def test_codigo_agotado_es_404_y_no_incrementa(base_data) -> None:
    await _seed_zone_and_code(max_uses=1)
    async with au.client_for(create_app()) as client:
        assert (await _enroll(client, _occ())).status_code == 200
        assert (await _enroll(client, _occ(OCC_USER_2))).status_code == 404


@pytest.mark.anyio
async def test_push_tokens_ciclo_completo_y_superficie(base_data) -> None:
    """Upsert por token (re-registro revive), lista propia, revocación; una
    superficie web pura queda fuera (403)."""
    async with au.client_for(create_app()) as client:
        headers = au.bearer(_occ())
        body = {"platform": "android", "token": "fcm-token-1"}
        first = await client.post("/me/push-tokens", json=body, headers=headers)
        assert first.status_code == 201
        again = await client.post("/me/push-tokens", json=body, headers=headers)
        assert again.status_code == 201
        assert again.json()["push_token_id"] == first.json()["push_token_id"]

        listed = await client.get("/me/push-tokens", headers=headers)
        assert [t["token"] for t in listed.json()] == ["fcm-token-1"]

        gone = await client.delete(
            f"/me/push-tokens/{first.json()['push_token_id']}", headers=headers
        )
        assert gone.status_code == 204
        assert (await client.get("/me/push-tokens", headers=headers)).json() == []

        web = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="web")
        resp = await client.post("/me/push-tokens", json=body, headers=au.bearer(web))
        assert resp.status_code == 403


@pytest.mark.anyio
async def test_device_key_valida_pem(base_data) -> None:
    async with au.client_for(create_app()) as client:
        headers = au.bearer(_brig())
        bad = await client.post(
            "/me/device-keys",
            json={"platform": "ios", "public_key": "no-es-pem" * 20},
            headers=headers,
        )
        assert bad.status_code == 422
        pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEfake0000000000000000000000\n"
            "-----END PUBLIC KEY-----"
        )
        ok = await client.post(
            "/me/device-keys", json={"platform": "ios", "public_key": pem}, headers=headers
        )
        assert ok.status_code == 201
        assert (await client.get("/me/device-keys", headers=headers)).json()[0]["platform"] == "ios"


async def _seed_tier(new_tier: str, ts_offset_s: int = 0) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, "
                "prev_tier, new_tier) VALUES (:ts, :t, :s, :g, 'normal', :tier)"
            ),
            {
                "ts": datetime.now(UTC) + timedelta(seconds=ts_offset_s),
                "t": au.DB_TENANT_PRIV,
                "s": au.DB_SITE_PRIV,
                "g": str(uuid.uuid4()),
                "tier": new_tier,
            },
        )


async def _seed_dictamen(incident_id: str, *, status: str, signed: bool) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by) "
                "VALUES (:t, :i, :st, '{}'::jsonb, :by)"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "i": incident_id,
                "st": status,
                "by": str(uuid.uuid4()) if signed else None,
            },
        )


@pytest.mark.anyio
async def test_phase_se_deriva_de_datos_reales(base_data, make_incident) -> None:
    """alert_active (tier ≠ normal) → shaking_concluded (tier normal) →
    reentry_approved SOLO con dictamen FIRMADO habitable."""
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/sites/{au.DB_SITE_PRIV}/mobile-state"
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())
        headers = au.bearer(_occ())

        await _seed_tier("evacuate_or_hold")
        state = (await client.get(url, headers=headers)).json()
        assert state["phase"] == "alert_active"
        assert state["reentry"]["blocked"] is True

        await _seed_tier("normal", ts_offset_s=1)
        state = (await client.get(url, headers=headers)).json()
        assert state["phase"] == "shaking_concluded"

        # dictamen preliminar SIN firma: no libera
        await _seed_dictamen(incident_id, status="inhabit_monitor", signed=False)
        state = (await client.get(url, headers=headers)).json()
        assert state["phase"] == "shaking_concluded"
        assert state["reentry"]["dictamen_signed"] is False

        await _seed_dictamen(incident_id, status="inhabit_monitor", signed=True)
        state = (await client.get(url, headers=headers)).json()
        assert state["phase"] == "reentry_approved"
        assert state["reentry"]["blocked"] is False


@pytest.mark.anyio
async def test_drills_agenda_no_deriva_activo(base_data) -> None:
    """Una fila con scheduled_at es ANUNCIO: aparece como próximo, jamás activa."""
    await _seed_zone_and_code()
    engine = get_engine()
    future = datetime.now(UTC) + timedelta(days=3)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO drills (tenant_id, initiated_by, note, duration_s, scheduled_at) "
                "VALUES (:t, :by, 'Simulacro nacional', 300, :at)"
            ),
            {"t": au.DB_TENANT_PRIV, "by": str(uuid.uuid4()), "at": future},
        )
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())
        resp = await client.get(f"/sites/{au.DB_SITE_PRIV}/drills", headers=au.bearer(_occ()))
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is False
        assert body["next_scheduled_at"] is not None


@pytest.mark.anyio
async def test_checkin_propio_delegado_y_cruces(base_data, make_incident) -> None:
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/incidents/{incident_id}/checkins"
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())

        # propio (occupant): via=self, sin verified_by
        own = await client.post(
            url,
            json={"status": "safe", "ts_device": datetime.now(UTC).isoformat()},
            headers=au.bearer(_occ()),
        )
        assert own.status_code == 201
        assert own.json()["via"] == "self"
        assert own.json()["verified_by"] is None

        # delegado (brigadista con roster_read): distinguible en datos
        delegated = await client.post(
            url,
            json={"status": "safe", "subject_user_id": OCC_USER_2},
            headers=au.bearer(_brig()),
        )
        assert delegated.status_code == 201
        assert delegated.json()["via"] == "delegated"
        assert delegated.json()["verified_by"] == BRIG_USER
        assert delegated.json()["user_id"] == OCC_USER_2

        # un occupant NO puede delegar (marca a terceros)
        forged = await client.post(
            url,
            json={"status": "safe", "subject_user_id": OCC_USER_2},
            headers=au.bearer(_occ()),
        )
        assert forged.status_code == 403

        # scope=me reconstruye SOLO lo propio
        mine = await client.get(url, headers=au.bearer(_occ()))
        assert [c["user_id"] for c in mine.json()] == [OCC_USER]

        # cruce de tenants: occupant de B sobre incidente de A ⇒ 404
        cross = await client.post(
            url,
            json={"status": "safe"},
            headers=au.bearer(_occ(user_id=OCC_USER_2, tenant=au.DB_TENANT_PRIV2)),
        )
        assert cross.status_code == 404

        # gov_operator jamás escribe check-ins (sin acción checkin_submit)
        gov = au.make_token("gov_operator", tenant=au.DB_TENANT_GOV, surface="both")
        assert (
            await client.post(url, json={"status": "safe"}, headers=au.bearer(gov))
        ).status_code == 403


GW_PRIV = "70000000-0000-0000-0000-00000000ee01"


async def _cleanup_gateway() -> None:
    """gateways/device_health NO están en el TRUNCATE de la suite (portan seeds
    globales de OTROS tenants): este test limpia los gabinetes de SU sitio —
    residuos de otros archivos de test que también siembran ahí — para que el
    escenario "sitio sin gabinete" sea real en cualquier orden/rerun."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM device_health WHERE gateway_id IN "
                "(SELECT gateway_id FROM gateways WHERE site_id = :s)"
            ),
            {"s": au.DB_SITE_PRIV},
        )
        await conn.execute(text("DELETE FROM gateways WHERE site_id = :s"), {"s": au.DB_SITE_PRIV})


async def _seed_gateway(has_wr1: bool) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, has_wr1) "
                "VALUES (:g, :t, :s, 'GW-MOB-1', :wr1) "
                "ON CONFLICT (gateway_id) DO UPDATE SET has_wr1 = :wr1"
            ),
            {"g": GW_PRIV, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "wr1": has_wr1},
        )


async def _heartbeat(power_status: str, battery_pct: float | None) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, "
                "power_status, battery_pct) "
                "VALUES (now(), :t, :g, 'heartbeat', :power, :batt)"
            ),
            {"t": au.DB_TENANT_PRIV, "g": GW_PRIV, "power": power_status, "batt": battery_pct},
        )


@pytest.fixture
async def gw_sandbox(base_data):
    """Sitio PRIV sin gabinetes al ENTRAR y sin residuos al SALIR (los tests de
    ingest cuentan filas de device_health — un heartbeat huérfano los rompe)."""
    await _cleanup_gateway()
    yield
    await _cleanup_gateway()


@pytest.mark.anyio
async def test_mobile_state_site_health_honesto(gw_sandbox) -> None:
    """T-2.07 · 1.1: el banner del edificio sale del MISMO derivador que la
    Flota Edge (verdad única `derive_fleet_state`), jamás calculado en el
    teléfono. Sin heartbeat ⇒ SIN ENLACE (no se finge); fresco ⇒ OPERATIVO;
    en batería ⇒ DEGRADADO. `has_wr1` es el hardware DECLARADO del gabinete
    (no existe supervisión de línea del WR-1 — solo Relevador 2 cableado)."""
    await _seed_zone_and_code()
    url = f"/sites/{au.DB_SITE_PRIV}/mobile-state"
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())

        # sitio sin gabinete: SIN ENLACE honesto, sin heartbeat, sin WR-1 y
        # TODAS las métricas del panel en None (S/D — jamás ceros inventados)
        r0 = await client.get(url, headers=au.bearer(_occ()))
        assert r0.status_code == 200
        sh0 = r0.json()["site_health"]
        assert sh0["status"] == "SIN ENLACE"
        assert sh0["heartbeat_at"] is None
        assert sh0["has_wr1"] is False
        for metric in ("mqtt_rtt_ms", "power_status", "battery_pct", "cpu_temp_c"):
            assert sh0[metric] is None

        # gabinete con WR-1 y heartbeat fresco en la pared ⇒ OPERATIVO
        await _seed_gateway(has_wr1=True)
        await _heartbeat("mains", 100.0)
        sh1 = (await client.get(url, headers=au.bearer(_occ()))).json()["site_health"]
        assert sh1["status"] == "OPERATIVO"
        assert sh1["has_wr1"] is True
        assert sh1["heartbeat_at"] is not None
        assert sh1["age_s"] < 60

        # en batería ⇒ DEGRADADO (mismo umbral que la consola)
        await _heartbeat("on_battery", 50.0)
        sh2 = (await client.get(url, headers=au.bearer(_occ()))).json()["site_health"]
        assert sh2["status"] == "DEGRADADO"


@pytest.mark.anyio
async def test_directorio_del_sitio(base_data) -> None:
    """T-2.07 · 1.7: roster PÚBLICO del sitio — brigadistas/seguridad con
    nombre, zona y teléfono (llamada de un toque). El occupant enrolado lo ve;
    los occupants NO se listan (no son contactos de emergencia); cruce de
    tenants = el MISMO 404; sitio sin contactos = [] honesto."""
    await _seed_zone_and_code()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) "
                "VALUES (:u, :t, 'Brigada Uno', '+525511112222')"
            ),
            {"u": BRIG_USER, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role) "
                "VALUES (:u, :t, :s, :z, 'brigadista')"
            ),
            {"u": BRIG_USER, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONE_PRIV},
        )
    url = f"/sites/{au.DB_SITE_PRIV}/directory"
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())  # el enrolamiento crea la uza del occupant

        r = await client.get(url, headers=au.bearer(_occ()))
        assert r.status_code == 200
        entries = r.json()
        assert [e["role"] for e in entries] == ["brigadista"]  # occupant fuera
        assert entries[0]["display_name"] == "Brigada Uno"
        assert entries[0]["phone"] == "+525511112222"
        assert entries[0]["zone_name"] == "P10-A"

        # cruce de tenants: el MISMO 404 (sin filtración de existencia)
        cross = await client.get(
            url, headers=au.bearer(_occ(user_id=OCC_USER_2, tenant=au.DB_TENANT_PRIV2))
        )
        assert cross.status_code == 404

        # sin contactos ⇒ [] honesto (jamás inventa filas)
        engine2 = get_engine()
        async with engine2.begin() as conn:
            await conn.execute(text("DELETE FROM user_zone_assignments WHERE role = 'brigadista'"))
        assert (await client.get(url, headers=au.bearer(_occ()))).json() == []


@pytest.mark.anyio
async def test_checkin_replay_offline_es_idempotente(base_data, make_incident) -> None:
    """T-2.06 · La cola offline REINTENTA: el mismo ``checkin_id`` de cliente
    jamás duplica (regla de oro 3 — idempotencia en todo dato que cruza).

    - 1er envío ⇒ 201, fila nueva con el id del dispositivo.
    - Replay exacto (red que murió tras aterrizar) ⇒ 200 con LA MISMA fila.
    - El mismo id desde OTRO portador ⇒ 409 y JAMÁS la fila ajena.
    """
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/incidents/{incident_id}/checkins"
    cid = str(uuid.uuid4())
    body = {
        "checkin_id": cid,
        "status": "need_help",
        "ts_device": datetime.now(UTC).isoformat(),
        "location": [-99.13, 19.43],
    }
    async with au.client_for(create_app()) as client:
        await _enroll(client, _occ())

        first = await client.post(url, json=body, headers=au.bearer(_occ()))
        assert first.status_code == 201
        assert first.json()["checkin_id"] == cid

        replay = await client.post(url, json=body, headers=au.bearer(_occ()))
        assert replay.status_code == 200
        assert replay.json()["checkin_id"] == cid
        assert replay.json()["created_at"] == first.json()["created_at"]

        # scope=me: UNA sola fila — el replay no duplicó nada
        mine = await client.get(url, headers=au.bearer(_occ()))
        assert [c["checkin_id"] for c in mine.json()] == [cid]

        # el mismo id desde OTRO portador: conflicto explícito, sin fuga
        await _enroll(client, _occ(user_id=OCC_USER_2))
        thief = await client.post(
            url,
            json={"checkin_id": cid, "status": "safe"},
            headers=au.bearer(_occ(user_id=OCC_USER_2)),
        )
        assert thief.status_code == 409


@pytest.mark.anyio
async def test_traza_bms_para_dashboard_tactico(base_data, make_incident) -> None:
    """T-2.08 · ``panel_read`` (RBAC §3: Dashboard táctico): el brigadista lee
    la traza del incidente DE SU SITIO por el MISMO endpoint que la consola
    (cero SQL divergente); fuera de su ``site_scope`` recibe el MISMO 404; el
    occupant jamás entra (403 — §3 da "—" en dashboard)."""
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/incidents/{incident_id}/actions"
    async with au.client_for(create_app()) as client:
        ok = await client.get(url, headers=au.bearer(_brig()))
        assert ok.status_code == 200
        assert isinstance(ok.json(), list)

        fuera = await client.get(url, headers=au.bearer(_brig(site_scope=str(uuid.uuid4()))))
        assert fuera.status_code == 404

        occ = await client.get(url, headers=au.bearer(_occ()))
        assert occ.status_code == 403


@pytest.mark.anyio
async def test_roster_cuenta_y_gatea(base_data, make_incident) -> None:
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) "
                "VALUES (:u, :t, 'María Reyes', '+525512848211')"
            ),
            {"u": OCC_USER, "t": au.DB_TENANT_PRIV},
        )
        for user in (OCC_USER, OCC_USER_2):
            await conn.execute(
                text(
                    "INSERT INTO user_zone_assignments "
                    "(user_id, tenant_id, site_id, zone_id, role) "
                    "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONE_PRIV},
            )
    async with au.client_for(create_app()) as client:
        await client.post(
            f"/incidents/{incident_id}/checkins",
            json={"status": "safe"},
            headers=au.bearer(_occ()),
        )
        resp = await client.get(f"/incidents/{incident_id}/roster", headers=au.bearer(_brig()))
        assert resp.status_code == 200
        roster = resp.json()
        assert roster["total"] == 2
        assert roster["safe"] == 1
        assert roster["unreported"] == 1
        named = next(e for e in roster["entries"] if e["user_id"] == OCC_USER)
        assert named["display_name"] == "María Reyes"
        assert named["phone"] == "+525512848211"
        assert named["checkin"]["via"] == "self"

        # el occupant NO ve el roster (PII de terceros)
        assert (
            await client.get(f"/incidents/{incident_id}/roster", headers=au.bearer(_occ()))
        ).status_code == 403


@pytest.mark.anyio
async def test_lee_dictamen_para_reingreso(base_data, make_incident) -> None:
    """T-2.12 · 2.7: el táctico lee el certificado (dictamen_read) — metadatos
    del dictamen firmado + habitable; sin PDF generado ⇒ pdf_url None (honesto,
    no finge). El occupant NO lo lee (sin dictamen_read)."""
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        # sin firma todavía
        r0 = await client.get(f"/incidents/{incident_id}/dictamen", headers=au.bearer(_brig()))
        assert r0.status_code == 200
        assert r0.json()["signed"] is False
        assert r0.json()["habitable"] is False

        await _seed_dictamen(incident_id, status="inhabit_monitor", signed=True)
        r1 = await client.get(f"/incidents/{incident_id}/dictamen", headers=au.bearer(_brig()))
        body = r1.json()
        assert body["signed"] is True
        assert body["habitable"] is True
        assert body["folio"] is not None
        assert body["pdf_url"] is None  # sin bucket/PDF: se declara, no se inventa

        # el occupant no tiene dictamen_read
        assert (
            await client.get(f"/incidents/{incident_id}/dictamen", headers=au.bearer(_occ()))
        ).status_code == 403


@pytest.mark.anyio
async def test_firma_habitable_deja_accion_para_push(base_data, make_incident) -> None:
    """T-2.12: firmar un dictamen HABITABLE en consola deja un incident_action
    ``dictamen_signed`` que el orchestrator convierte en push OPS de fase; una
    firma NO habitable (restricted) no lo deja."""
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        insp = au.make_token("inspector", tenant=au.DB_TENANT_PRIV, surface="web")
        ok = await client.post(
            f"/incidents/{incident_id}/dictamens",
            json={"status": "inhabit_monitor"},
            headers=au.bearer(insp),
        )
        assert ok.status_code == 201, ok.text
        bad = await client.post(
            f"/incidents/{incident_id}/dictamens",
            json={"status": "restricted"},
            headers=au.bearer(insp),
        )
        assert bad.status_code == 201

    engine = get_engine()
    async with engine.begin() as conn:
        kinds = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM incident_actions WHERE incident_id = :i "
                    "AND kind = 'dictamen_signed'"
                ),
                {"i": incident_id},
            )
        ).scalar_one()
    assert kinds == 1  # solo la firma habitable dejó acción


@pytest.mark.anyio
async def test_headcount_cierre_y_notificacion(base_data, make_incident) -> None:
    """T-2.11 · 2.6: cerrar headcount = acción firmada (headcount_closed) con el
    conteo de no reportados; notificar-a-no-reportados registra headcount_notify
    (el orchestrator lo convierte en push OPS). Solo roles con roster_read."""
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    engine = get_engine()
    async with engine.begin() as conn:
        for user in (OCC_USER, OCC_USER_2):
            await conn.execute(
                text(
                    "INSERT INTO user_zone_assignments "
                    "(user_id, tenant_id, site_id, zone_id, role) "
                    "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONE_PRIV},
            )
    async with au.client_for(create_app()) as client:
        # un occupant reporta ⇒ 1 no reportado
        await client.post(
            f"/incidents/{incident_id}/checkins",
            json={"status": "safe"},
            headers=au.bearer(_occ()),
        )
        close = await client.post(
            f"/incidents/{incident_id}/headcount/close", json={}, headers=au.bearer(_brig())
        )
        assert close.status_code == 200
        assert close.json()["kind"] == "headcount_closed"
        assert close.json()["unreported"] == 1
        assert close.json()["signed"] is False

        notify = await client.post(
            f"/incidents/{incident_id}/headcount/notify-unreported", headers=au.bearer(_brig())
        )
        assert notify.status_code == 200
        assert notify.json()["kind"] == "headcount_notify"
        assert notify.json()["unreported"] == 1

        # firma incompleta ⇒ 400 (key_id y signature van juntos)
        bad = await client.post(
            f"/incidents/{incident_id}/headcount/close",
            json={"signature": "x" * 40},
            headers=au.bearer(_brig()),
        )
        assert bad.status_code == 400

        # el occupant no cierra headcount (sin roster_read)
        assert (
            await client.post(
                f"/incidents/{incident_id}/headcount/close", json={}, headers=au.bearer(_occ())
            )
        ).status_code == 403

    # las acciones quedaron en el timeline para el orchestrator
    async with engine.begin() as conn:
        kinds = (
            await conn.execute(
                text(
                    "SELECT kind FROM incident_actions WHERE incident_id = :i "
                    "AND kind IN ('headcount_closed','headcount_notify') ORDER BY kind"
                ),
                {"i": incident_id},
            )
        ).all()
    assert [k.kind for k in kinds] == ["headcount_closed", "headcount_notify"]


@pytest.mark.anyio
async def test_checkin_emite_notify_live(base_data, make_incident) -> None:
    """T-2.11 · 2.6: cada check-in dispara NOTIFY en takab_live (señal de roster)
    para que el headcount táctico refresque en <2 s. Se escucha el canal."""
    import asyncio
    import json as _json

    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    # conexión de escucha cruda (LISTEN no pasa por SQLAlchemy)
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    listener = await asyncio.to_thread(psycopg.connect, dsn, autocommit=True)
    try:
        await asyncio.to_thread(listener.execute, "LISTEN takab_live")
        async with au.client_for(create_app()) as client:
            await _enroll(client, _occ())
            r = await client.post(
                f"/incidents/{incident_id}/checkins",
                json={"status": "safe"},
                headers=au.bearer(_occ()),
            )
            assert r.status_code == 201

        def _drain() -> list[dict]:
            got = []
            for note in listener.notifies(timeout=3.0):
                got.append(_json.loads(note.payload))
                break
            return got

        notifies = await asyncio.to_thread(_drain)
    finally:
        await asyncio.to_thread(listener.close)

    checkin_signals = [n for n in notifies if n.get("t") == "checkin"]
    assert checkin_signals, f"sin señal de check-in: {notifies}"
    assert checkin_signals[0]["incident_id"] == str(incident_id)


@pytest.mark.anyio
async def test_damage_report_deriva_prioridad_y_llega_a_consola(base_data, make_incident) -> None:
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/incidents/{incident_id}/damage-reports"
    async with au.client_for(create_app()) as client:
        created = await client.post(
            url,
            json={
                "categories": [
                    {"key": "structural", "severity": "critical"},
                    {"key": "people_trapped", "severity": "critical"},
                ],
                "notes": "columna NE con grieta",
            },
            headers=au.bearer(_brig()),
        )
        assert created.status_code == 201
        assert created.json()["people_at_risk"] is True

        # [T-2.10] personas en riesgo ⇒ acción en el timeline para que el
        # orchestrator OPS notifique al SOC de inmediato.
        engine = get_engine()
        async with engine.begin() as conn:
            kinds = (
                await conn.execute(
                    text(
                        "SELECT kind FROM incident_actions WHERE incident_id = :i "
                        "AND kind = 'damage_people_at_risk'"
                    ),
                    {"i": incident_id},
                )
            ).all()
        assert len(kinds) == 1

        # la consola (soc_operator del tenant) LEE el reporte para Triage
        soc = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="web")
        listed = await client.get(url, headers=au.bearer(soc))
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        # el occupant no reporta daños (sin acción damage_report_submit)
        assert (
            await client.post(
                url,
                json={"categories": [{"key": "gas_leak", "severity": "low"}]},
                headers=au.bearer(_occ()),
            )
        ).status_code == 403

        # categoría desconocida: 422 del schema, jamás llega a la DB
        assert (
            await client.post(
                url,
                json={"categories": [{"key": "aliens", "severity": "low"}]},
                headers=au.bearer(_brig()),
            )
        ).status_code == 422


@pytest.mark.anyio
async def test_enrollment_codes_gestion(base_data) -> None:
    """building_admin administra códigos; el occupant no (403)."""
    admin = au.make_token(
        "building_admin", tenant=au.DB_TENANT_PRIV, surface="both", site_scope=au.DB_SITE_PRIV
    )
    base = f"/sites/{au.DB_SITE_PRIV}/enrollment-codes"
    async with au.client_for(create_app()) as client:
        created = await client.post(
            base, json={"code": "NUEVO-01", "max_uses": 10}, headers=au.bearer(admin)
        )
        assert created.status_code == 201
        assert created.json()["grants_role"] == "occupant"

        listed = await client.get(base, headers=au.bearer(admin))
        assert [c["code"] for c in listed.json()] == ["NUEVO-01"]

        assert (
            await client.post(base, json={"code": "X-1"}, headers=au.bearer(_occ()))
        ).status_code == 403

        gone = await client.delete(f"{base}/NUEVO-01", headers=au.bearer(admin))
        assert gone.status_code == 204
        assert (await client.get(base, headers=au.bearer(admin))).json()[0]["active"] is False
