"""T-1.22 · live fan-out: función takab_notify() + triggers LISTEN/NOTIFY.

Fan-out del WS por fetch-on-notify: los writers (ingest BYPASSRLS, engine, ack de
la API) NO publican nada; un trigger AFTER en las tablas de negocio emite en el canal
``takab_live`` un payload MÍNIMO —solo señal de invalidación con tenant/site/ids—. El
hub del WS re-consulta la fila con los GUCs del suscriptor (Postgres/RLS decide qué se
ve); el payload del NOTIFY NUNCA se reenvía al cliente. Por eso ingest/engine (T-1.17/
T-1.19) necesitan CERO código para live: basta con que escriban la fila.

``takab_notify()`` es genérica y se instancia por tabla vía ``TG_ARGV[0]`` (el tipo).
Cada rama referencia solo columnas que la tabla en cuestión tiene (verificado contra
db/schema.sql): incidents(incident_id PK, tenant_id, site_id), incident_actions
(action_id PK, tenant_id, incident_id; SIN site_id), device_health(PK compuesto
(ts,gateway_id), tenant_id, gateway_id; SIN site_id, hypertable), rule_evaluations
(PK compuesto (ts,gateway_id), tenant_id, site_id, gateway_id; hypertable). PL/pgSQL
resuelve ``NEW.<col>`` por relación en ejecución, así que compartir la función entre
tablas de distinto shape es seguro (solo se ejecuta la rama de su ``TG_ARGV[0]``).

Canal: ``takab_live``. Payloads (json de una línea, ::text):
  incident         {"t":"incident","tenant":…,"site":…,"id":<incident_id>}
  incident_action  {"t":"incident_action","tenant":…,"id":<action_id>,"incident_id":…}
  device_health    {"t":"device_health","tenant":…,"gateway_id":…}   (solo transiciones)
  rule_evaluation  {"t":"rule_evaluation","tenant":…,"site":…,"gateway_id":…}

Revision ID: 0004_live_notify
Revises: 0003_gov_ack_lock
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_live_notify"
down_revision: str | None = "0003_gov_ack_lock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Función SECURITY INVOKER: solo hace pg_notify (no toca tablas con RLS), así que
# corre bien bajo cualquier rol escritor. RETURN NULL: es AFTER, el valor se ignora.
_FN = """
CREATE OR REPLACE FUNCTION takab_notify() RETURNS trigger
  LANGUAGE plpgsql AS $fn$
DECLARE
  payload jsonb;
BEGIN
  CASE TG_ARGV[0]
    WHEN 'incident' THEN
      payload := jsonb_build_object(
        't', 'incident', 'tenant', NEW.tenant_id,
        'site', NEW.site_id, 'id', NEW.incident_id);
    WHEN 'incident_action' THEN
      payload := jsonb_build_object(
        't', 'incident_action', 'tenant', NEW.tenant_id,
        'id', NEW.action_id, 'incident_id', NEW.incident_id);
    WHEN 'device_health' THEN
      payload := jsonb_build_object(
        't', 'device_health', 'tenant', NEW.tenant_id,
        'gateway_id', NEW.gateway_id);
    WHEN 'rule_evaluation' THEN
      payload := jsonb_build_object(
        't', 'rule_evaluation', 'tenant', NEW.tenant_id,
        'site', NEW.site_id, 'gateway_id', NEW.gateway_id);
    ELSE
      RAISE EXCEPTION 'takab_notify: tipo desconocido %', TG_ARGV[0];
  END CASE;
  PERFORM pg_notify('takab_live', payload::text);
  RETURN NULL;
END $fn$;
"""

_TRIGGERS = """
CREATE TRIGGER trg_incidents_notify
  AFTER INSERT OR UPDATE ON incidents
  FOR EACH ROW EXECUTE FUNCTION takab_notify('incident');

CREATE TRIGGER trg_incident_actions_notify
  AFTER INSERT ON incident_actions
  FOR EACH ROW EXECUTE FUNCTION takab_notify('incident_action');

CREATE TRIGGER trg_device_health_notify
  AFTER INSERT ON device_health
  FOR EACH ROW WHEN (NEW.reason = 'transition')
  EXECUTE FUNCTION takab_notify('device_health');

CREATE TRIGGER trg_rule_evaluations_notify
  AFTER INSERT ON rule_evaluations
  FOR EACH ROW EXECUTE FUNCTION takab_notify('rule_evaluation');
"""

_DROP = """
DROP TRIGGER IF EXISTS trg_incidents_notify ON incidents;
DROP TRIGGER IF EXISTS trg_incident_actions_notify ON incident_actions;
DROP TRIGGER IF EXISTS trg_device_health_notify ON device_health;
DROP TRIGGER IF EXISTS trg_rule_evaluations_notify ON rule_evaluations;
DROP FUNCTION IF EXISTS takab_notify();
"""


def _exec(sql: str) -> None:
    """Ejecuta SQL por el cursor psycopg crudo (sin binding).

    El cuerpo PL/pgSQL trae ``%`` (RAISE) y ``::text`` que el binding de SQLAlchemy
    malinterpretaría como placeholders; mismo patrón que la migración 0003.
    """
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_FN)
    _exec(_TRIGGERS)


def downgrade() -> None:
    _exec(_DROP)
