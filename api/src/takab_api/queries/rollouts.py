"""Consultas del canary por cohortes (T-2.70)."""

from __future__ import annotations

from sqlalchemy import text

INSERT_ROLLOUT = text(
    "INSERT INTO fleet_rollouts (tenant_id, release_id, target_fw, created_by) "
    "VALUES (CAST(:tenant AS uuid), :release, :target_fw, CAST(:user_id AS uuid)) "
    "RETURNING rollout_id, tenant_id, release_id, target_fw, state, created_at, "
    "finished_at, abort_reason"
)

INSERT_ROLLOUT_SITE = text(
    "INSERT INTO fleet_rollout_sites (rollout_id, site_id, tenant_id, phase) "
    "VALUES (CAST(:rollout AS uuid), CAST(:site AS uuid), CAST(:tenant AS uuid), :phase)"
)

MARK_ACTIVATED = text(
    "UPDATE fleet_rollout_sites SET command_id = CAST(:command AS uuid), activated_at = :now "
    "WHERE rollout_id = CAST(:rollout AS uuid) AND site_id = CAST(:site AS uuid)"
)

SELECT_ROLLOUT = text(
    "SELECT rollout_id, tenant_id, release_id, target_fw, state, created_at, "
    "finished_at, abort_reason FROM fleet_rollouts WHERE rollout_id = CAST(:rollout AS uuid)"
)

#: Los sitios del rollout con lo único que responde «¿funcionó?»: qué SHA declara
#: el PROCESO de ese gabinete (`fw_running`, T-2.69). El disco cambia con el
#: `rsync` y la memoria sólo con el reinicio, así que `fw_version` no sirve aquí.
#: `ack` viene del comando: distingue «el gabinete recibió la orden» de «el
#: gabinete la ejecutó», que no son lo mismo y se confunden con facilidad.
SELECT_ROLLOUT_SITES = text(
    "SELECT rs.site_id, rs.phase, rs.command_id, rs.activated_at, "
    "       s.name AS site_name, g.fw_running, g.iot_thing, c.status AS command_status "
    "FROM fleet_rollout_sites rs "
    "JOIN sites s ON s.site_id = rs.site_id "
    "LEFT JOIN gateways g ON g.site_id = rs.site_id AND g.status <> 'retired' "
    "LEFT JOIN commands c ON c.command_id = rs.command_id "
    "WHERE rs.rollout_id = CAST(:rollout AS uuid) "
    "ORDER BY rs.phase, s.name"
)

SET_STATE = text(
    "UPDATE fleet_rollouts SET state = :state, finished_at = :now, "
    "abort_reason = :reason WHERE rollout_id = CAST(:rollout AS uuid)"
)

#: Sitios del tenant con gabinete comandable. Es a lo que puede apuntar un
#: rollout: sin `iot_thing` no hay a quién mandarle nada.
COMMANDABLE_SITES = text(
    "SELECT s.site_id, s.tenant_id FROM sites s "
    "WHERE s.status <> 'retired' AND EXISTS ("
    "  SELECT 1 FROM gateways g WHERE g.site_id = s.site_id "
    "  AND g.status <> 'retired' AND g.iot_thing IS NOT NULL) "
    "ORDER BY s.site_id"
)
