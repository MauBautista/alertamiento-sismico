"""T-2.11 · Señal live de check-in para el headcount (2.6).

Extiende ``takab_notify()`` con el tipo ``checkin`` y añade el trigger AFTER
INSERT sobre ``life_checkins``: cada check-in (propio o delegado) emite en el
canal ``takab_live`` un payload MÍNIMO ``{t:'checkin', tenant, site,
incident_id}`` — sin PII. El hub lo mapea al topic ``incidents`` y los tácticos
suscritos refrescan el roster en <2 s (criterio de aceptación 2.6). La
autoridad de PII sigue siendo el REST ``/roster`` (gated ``roster_read``); esto
es solo una señal de invalidación.

``takab_notify`` es SECURITY INVOKER y solo hace ``pg_notify`` — corre bajo
cualquier rol escritor (incl. ``takab_app`` del móvil). Idempotente
(invariante T-1.45): ``CREATE OR REPLACE FUNCTION`` + ``DROP TRIGGER IF
EXISTS`` antes de crear. La función es PREEXISTENTE (0004) ⇒ el REPLACE corre
como usuario de conexión; el trigger es objeto nuevo sobre tabla preexistente
⇒ también usuario de conexión (patrón de dueños históricos, T-2.05).

Revision ID: 0020_checkin_notify
Revises: 0019_push_endpoints
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_checkin_notify"
down_revision: str | None = "0019_push_endpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CREATE OR REPLACE de takab_notify con el caso 'checkin' añadido (resto igual
# a 0004). El payload trae site + incident_id para acotar la entrega por
# site_scope (hub, T-2.08) sin exponer al portador ni su estado.
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
    WHEN 'checkin' THEN
      payload := jsonb_build_object(
        't', 'checkin', 'tenant', NEW.tenant_id,
        'site', NEW.site_id, 'incident_id', NEW.incident_id);
    ELSE
      RAISE EXCEPTION 'takab_notify: tipo desconocido %', TG_ARGV[0];
  END CASE;
  PERFORM pg_notify('takab_live', payload::text);
  RETURN NULL;
END $fn$;
"""

_UP_TRIGGER = """
DROP TRIGGER IF EXISTS trg_life_checkins_notify ON life_checkins;
CREATE TRIGGER trg_life_checkins_notify
  AFTER INSERT ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION takab_notify('checkin');
"""

# Reverso: quita el trigger y restaura takab_notify SIN el caso 'checkin'.
_DOWN_TRIGGER = "DROP TRIGGER IF EXISTS trg_life_checkins_notify ON life_checkins;"

_FN_0004 = """
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


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (``%``/``::text`` del PL/pgSQL romperían
    el binding de SQLAlchemy) — patrón de 0004."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_FN)
    _exec(_UP_TRIGGER)


def downgrade() -> None:
    _exec(_DOWN_TRIGGER)
    _exec(_FN_0004)
