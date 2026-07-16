"""SQL de la superficie móvil (T-2.03). RLS acota TODO por tenant; estas
consultas añaden el acotamiento por USUARIO/alcance que RLS no modela:

- R2 (ratificada T-2.00): el alcance del ``occupant`` NO viaja en el claim
  (default-deny); se resuelve server-side contra ``user_zone_assignments``.
- Roles con ``site_scope`` acotado: el sitio pedido debe estar en el scope.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims, scope_filter

# --- acceso a sitio (R2) -------------------------------------------------------

_SITE = text("SELECT site_id, tenant_id, name FROM sites WHERE site_id = CAST(:site AS uuid)")

_MY_ASSIGNMENT = text(
    "SELECT a.zone_id, a.role, z.name AS zone_name, z.level_code, z.evac_policy "
    "FROM user_zone_assignments a LEFT JOIN zones z ON z.zone_id = a.zone_id "
    "WHERE a.user_id = CAST(:sub AS uuid) AND a.site_id = CAST(:site AS uuid)"
)


async def site_or_404(conn: AsyncConnection, site_id: UUID) -> Any:
    """Fila del sitio o 404 (RLS oculta lo ajeno ⇒ mismo 404, sin filtración)."""
    row = (await conn.execute(_SITE, {"site": str(site_id)})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="sitio no encontrado")
    return row


async def my_assignment(conn: AsyncConnection, sub: str, site_id: UUID) -> Any | None:
    """Asignación del portador en el sitio (zona + política) o None."""
    return (await conn.execute(_MY_ASSIGNMENT, {"sub": sub, "site": str(site_id)})).first()


async def assert_site_access(conn: AsyncConnection, claims: Claims, site_id: UUID) -> Any:
    """Sitio visible Y dentro del alcance del portador; si no, 404/403.

    - ``occupant``: debe estar ENROLADO en el sitio (R2) — sin fila ⇒ 404 (no
      se revela la existencia del sitio a quien no pertenece a él).
    - resto: ``site_scope`` del claim (default-deny; ALL_SITES = sin filtro).
    """
    site = await site_or_404(conn, site_id)
    if claims.role == "occupant":
        if await my_assignment(conn, claims.sub, site_id) is None:
            raise HTTPException(status_code=404, detail="sitio no encontrado")
        return site
    allowed = scope_filter(claims)
    if allowed is not None and str(site_id) not in allowed:
        raise HTTPException(status_code=403, detail="sitio fuera de tu alcance")
    return site


# --- push tokens -----------------------------------------------------------------

UPSERT_PUSH_TOKEN = text(
    "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id) "
    "VALUES (CAST(:tenant AS uuid), CAST(:sub AS uuid), :platform, :token, "
    "CAST(:site AS uuid)) "
    "ON CONFLICT (token) DO UPDATE SET last_seen_at = now(), revoked_at = NULL, "
    "platform = EXCLUDED.platform, site_id = EXCLUDED.site_id "
    "RETURNING push_token_id, platform, token, site_id, created_at, last_seen_at, revoked_at"
)

LIST_PUSH_TOKENS = text(
    "SELECT push_token_id, platform, token, site_id, created_at, last_seen_at, revoked_at "
    "FROM push_tokens WHERE revoked_at IS NULL ORDER BY created_at"
)

REVOKE_PUSH_TOKEN = text(
    "UPDATE push_tokens SET revoked_at = now() "
    "WHERE push_token_id = CAST(:id AS uuid) AND revoked_at IS NULL "
    "RETURNING push_token_id"
)

# --- device keys -------------------------------------------------------------------

INSERT_DEVICE_KEY = text(
    "INSERT INTO device_keys (tenant_id, user_sub, platform, public_key, attestation) "
    "VALUES (CAST(:tenant AS uuid), CAST(:sub AS uuid), :platform, :public_key, "
    "CAST(:attestation AS jsonb)) "
    "RETURNING key_id, platform, created_at, revoked_at"
)

LIST_DEVICE_KEYS = text(
    "SELECT key_id, platform, created_at, revoked_at FROM device_keys "
    "WHERE revoked_at IS NULL ORDER BY created_at"
)

# --- enrolamiento -------------------------------------------------------------------

# Consumo ATÓMICO del código: el UPDATE solo casa si sigue vigente (activo, sin
# expirar, con usos disponibles). RLS ya acota al tenant del portador — un código
# de OTRO tenant simplemente no existe para esta sesión.
CONSUME_CODE = text(
    "UPDATE site_enrollment_codes SET uses = uses + 1 "
    "WHERE code = :code AND active "
    "AND (expires_at IS NULL OR expires_at > now()) "
    "AND (max_uses IS NULL OR uses < max_uses) "
    "RETURNING site_id, zone_id, tenant_id, grants_role"
)

UPSERT_ASSIGNMENT = text(
    "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role) "
    "VALUES (CAST(:sub AS uuid), CAST(:tenant AS uuid), CAST(:site AS uuid), "
    "CAST(:zone AS uuid), :role) "
    "ON CONFLICT (user_id, site_id) DO UPDATE "
    "SET zone_id = EXCLUDED.zone_id, role = EXCLUDED.role, assigned_at = now()"
)

INSERT_CODE = text(
    "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id) "
    "VALUES (:code, CAST(:tenant AS uuid), CAST(:site AS uuid), CAST(:zone AS uuid)) "
    "RETURNING code, site_id, zone_id, grants_role, expires_at, max_uses, uses, active"
)

INSERT_CODE_FULL = text(
    "INSERT INTO site_enrollment_codes "
    "(code, tenant_id, site_id, zone_id, expires_at, max_uses) "
    "VALUES (:code, CAST(:tenant AS uuid), CAST(:site AS uuid), CAST(:zone AS uuid), "
    ":expires_at, :max_uses) "
    "RETURNING code, site_id, zone_id, grants_role, expires_at, max_uses, uses, active"
)

LIST_CODES = text(
    "SELECT code, site_id, zone_id, grants_role, expires_at, max_uses, uses, active "
    "FROM site_enrollment_codes WHERE site_id = CAST(:site AS uuid) ORDER BY code"
)

DEACTIVATE_CODE = text(
    "UPDATE site_enrollment_codes SET active = false "
    "WHERE code = :code AND site_id = CAST(:site AS uuid) AND active "
    "RETURNING code"
)

# --- mobile-state (ingredientes de la derivación de phase) ---------------------------

OPEN_INCIDENT = text(
    "SELECT i.incident_id, i.trigger, i.severity, i.state, i.opened_at, i.max_pga_g, "
    "(e.meta->>'node_count')::int AS node_count "
    "FROM incidents i LEFT JOIN seismic_events e ON e.event_id = i.event_id "
    "WHERE i.site_id = CAST(:site AS uuid) AND i.state <> 'closed' "
    "ORDER BY i.opened_at DESC LIMIT 1"
)

LATEST_TIER = text(
    "SELECT new_tier FROM rule_evaluations WHERE site_id = CAST(:site AS uuid) "
    "ORDER BY ts DESC LIMIT 1"
)

LATEST_DICTAMEN = text(
    "SELECT status, signed_by FROM dictamens "
    "WHERE incident_id = CAST(:incident AS uuid) ORDER BY created_at DESC LIMIT 1"
)

COMPLIANCE_LABELS = text(
    "SELECT labels FROM compliance_labels WHERE tenant_id = CAST(:tenant AS uuid)"
)

ASSEMBLY_POINT = text(
    "SELECT asset_id, kind, title, description, zone_id, content_type, s3_key, updated_at "
    "FROM site_assets WHERE site_id = CAST(:site AS uuid) AND kind = 'assembly_point' "
    "ORDER BY updated_at DESC LIMIT 1"
)

# Drill ACTIVO que toca este sitio (misma derivación que routers/drills.py; las
# filas de AGENDA — scheduled_at — jamás derivan activo: LO REAL GANA).
ACTIVE_DRILL_FOR_SITE = text(
    "SELECT 1 FROM drills d JOIN drill_sites ds ON ds.drill_id = d.drill_id "
    "WHERE ds.site_id = CAST(:site AS uuid) AND d.scheduled_at IS NULL "
    "AND d.stopped_at IS NULL "
    "AND now() < d.started_at + make_interval(secs => d.duration_s) LIMIT 1"
)

NEXT_SCHEDULED_DRILL = text(
    "SELECT scheduled_at FROM drills "
    "WHERE scheduled_at IS NOT NULL AND scheduled_at > now() "
    "ORDER BY scheduled_at ASC LIMIT 1"
)

LAST_DRILL_FOR_SITE = text(
    "SELECT d.started_at, d.note FROM drills d "
    "JOIN drill_sites ds ON ds.drill_id = d.drill_id "
    "WHERE ds.site_id = CAST(:site AS uuid) AND d.scheduled_at IS NULL "
    "AND (d.stopped_at IS NOT NULL "
    "     OR now() >= d.started_at + make_interval(secs => d.duration_s)) "
    "ORDER BY d.started_at DESC LIMIT 1"
)

# --- salud del sitio + directorio (T-2.07 · 1.1/1.7) -----------------------------------

# Último heartbeat por gabinete ACTIVO del sitio (patrón LATERAL de fleet.py);
# la edad usa now() de la transacción, jamás el reloj del teléfono.
SITE_HEALTH = text(
    "SELECT g.gateway_id, g.has_wr1, h.ts AS health_ts, h.power_status, "
    "h.battery_pct::float8 AS battery_pct, h.cert_days_remaining, "
    "h.mqtt_rtt_ms::float8 AS mqtt_rtt_ms, h.seedlink_lag_s::float8 AS seedlink_lag_s, "
    "h.ntp_offset_ms::float8 AS ntp_offset_ms, "
    "EXTRACT(EPOCH FROM (now() - h.ts))::float8 AS age_s "
    "FROM gateways g "
    "LEFT JOIN LATERAL ("
    "  SELECT dh.ts, dh.power_status, dh.battery_pct, dh.cert_days_remaining, "
    "         dh.mqtt_rtt_ms, dh.seedlink_lag_s, dh.ntp_offset_ms "
    "  FROM device_health dh WHERE dh.gateway_id = g.gateway_id "
    "  ORDER BY dh.ts DESC LIMIT 1"
    ") h ON true "
    "WHERE g.site_id = CAST(:site AS uuid) AND g.status <> 'retired'"
)

# Roster PÚBLICO del sitio: contactos de emergencia (jamás occupants). El RLS
# acota el tenant; el alcance del sitio lo valida assert_site_access antes.
SITE_DIRECTORY = text(
    "SELECT a.user_id, p.display_name, a.role, a.zone_id, z.name AS zone_name, p.phone "
    "FROM user_zone_assignments a "
    "JOIN user_profiles p ON p.user_sub = a.user_id "
    "LEFT JOIN zones z ON z.zone_id = a.zone_id "
    "WHERE a.site_id = CAST(:site AS uuid) "
    "AND a.role IN ('brigadista','security_guard','building_admin') "
    "ORDER BY z.name NULLS LAST, p.display_name"
)

# --- check-ins ------------------------------------------------------------------------

# [T-2.06] checkin_id lo puede traer la COLA OFFLINE del dispositivo: el replay
# del mismo id no inserta (DO NOTHING ⇒ RETURNING vacío) y el router devuelve la
# fila original vía CHECKIN_REPLAY. La tabla es append-only: jamás DO UPDATE.
INSERT_CHECKIN = text(
    "INSERT INTO life_checkins (checkin_id, tenant_id, incident_id, user_id, site_id, status, "
    "geom, zone_id, ts_device, via, verified_by) "
    "VALUES (COALESCE(CAST(:checkin_id AS uuid), gen_random_uuid()), "
    "CAST(:tenant AS uuid), CAST(:incident AS uuid), CAST(:subject AS uuid), "
    "CAST(:site AS uuid), :status, "
    "CASE WHEN CAST(:lon AS float8) IS NULL THEN NULL "
    "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326)"
    "::geography END, "
    "CAST(:zone AS uuid), :ts_device, :via, CAST(:verified_by AS uuid)) "
    "ON CONFLICT (checkin_id) DO NOTHING "
    "RETURNING checkin_id, incident_id, user_id, site_id, status, via, verified_by, "
    "ts_device, created_at"
)

# Replay legítimo = MISMO incidente y MISMO portador; un id ajeno no devuelve
# nada (⇒ 409 en el router) — jamás la fila de otro usuario.
CHECKIN_REPLAY = text(
    "SELECT checkin_id, incident_id, user_id, site_id, status, via, verified_by, "
    "ts_device, created_at FROM life_checkins "
    "WHERE checkin_id = CAST(:checkin_id AS uuid) "
    "AND incident_id = CAST(:incident AS uuid) AND user_id = CAST(:subject AS uuid)"
)

MY_CHECKINS = text(
    "SELECT checkin_id, incident_id, user_id, site_id, status, via, verified_by, "
    "ts_device, created_at FROM life_checkins "
    "WHERE incident_id = CAST(:incident AS uuid) AND user_id = CAST(:sub AS uuid) "
    "ORDER BY created_at DESC"
)

INCIDENT_FOR_MOBILE = text(
    "SELECT incident_id, tenant_id, site_id, state FROM incidents "
    "WHERE incident_id = CAST(:incident AS uuid)"
)

# --- roster (headcount) ------------------------------------------------------------------

# Roster del sitio del incidente × último check-in de ESTE incidente por persona.
ROSTER = text(
    "SELECT a.user_id, a.zone_id, z.name AS zone_name, "
    "p.display_name, p.phone, "
    "lc.status AS c_status, lc.via AS c_via, lc.created_at AS c_created_at, "
    "lc.ts_device AS c_ts_device "
    "FROM user_zone_assignments a "
    "LEFT JOIN zones z ON z.zone_id = a.zone_id "
    "LEFT JOIN user_profiles p ON p.user_sub = a.user_id "
    "LEFT JOIN LATERAL ("
    "  SELECT status, via, created_at, ts_device FROM life_checkins c "
    "  WHERE c.incident_id = CAST(:incident AS uuid) AND c.user_id = a.user_id "
    "  ORDER BY c.created_at DESC LIMIT 1"
    ") lc ON true "
    "WHERE a.site_id = CAST(:site AS uuid) "
    "ORDER BY z.name NULLS LAST, p.display_name NULLS LAST, a.user_id"
)

# --- damage reports ------------------------------------------------------------------------

INSERT_DAMAGE_REPORT = text(
    "INSERT INTO damage_reports (tenant_id, incident_id, site_id, zone_id, user_sub, "
    "categories, people_at_risk, notes, evidence_ids, intent_key_id, intent_signature, "
    "ts_device) "
    "VALUES (CAST(:tenant AS uuid), CAST(:incident AS uuid), CAST(:site AS uuid), "
    "CAST(:zone AS uuid), CAST(:sub AS uuid), CAST(:categories AS jsonb), "
    ":people_at_risk, :notes, CAST(:evidence_ids AS uuid[]), "
    "CAST(:intent_key_id AS uuid), :intent_signature, :ts_device) "
    "RETURNING report_id, incident_id, site_id, zone_id, user_sub, categories, "
    "people_at_risk, notes, evidence_ids, ts_device, created_at"
)

LIST_DAMAGE_REPORTS = text(
    "SELECT report_id, incident_id, site_id, zone_id, user_sub, categories, "
    "people_at_risk, notes, evidence_ids, ts_device, created_at "
    "FROM damage_reports WHERE incident_id = CAST(:incident AS uuid) "
    "ORDER BY created_at DESC"
)

# --- site assets --------------------------------------------------------------------------

LIST_ASSETS = text(
    "SELECT asset_id, kind, title, description, zone_id, content_type, s3_key, updated_at "
    "FROM site_assets WHERE site_id = CAST(:site AS uuid) ORDER BY kind, title"
)

INSERT_ASSET = text(
    "INSERT INTO site_assets (tenant_id, site_id, zone_id, kind, title, description, "
    "s3_key, content_type, updated_by) "
    "VALUES (CAST(:tenant AS uuid), CAST(:site AS uuid), CAST(:zone AS uuid), :kind, "
    ":title, :description, :s3_key, :content_type, CAST(:by AS uuid)) "
    "RETURNING asset_id, kind, title, description, zone_id, content_type, s3_key, updated_at"
)

DELETE_ASSET = text(
    "DELETE FROM site_assets WHERE asset_id = CAST(:id AS uuid) "
    "AND site_id = CAST(:site AS uuid) RETURNING asset_id"
)
