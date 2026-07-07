"""T-1.18 · gov_ack_incident: candado de fila contra doble-acuse concurrente

El acuse de gobierno (``gov_ack_incident``, SECURITY DEFINER, dueño ``takab_ingest``)
leía estado y transicionaba open->acked sin bloquear la fila: dos acuses
concurrentes del MISMO incidente gov_shared pasaban ambos la guarda ``state='open'``
y escribían dos filas en ``audit_log`` (violando el DoD G6: doble-acuse => 4xx).

Fix mínimo, dentro de la función (BYPASSRLS, sin líos de RLS): la lectura de estado
toma ``FOR UPDATE OF i`` sobre el incidente, así el segundo acuse serializa, vuelve a
leer ``state='acked'`` y lanza la excepción de transición inválida (=> 409 en la API).
La guarda ``AND state='open'`` en el UPDATE es defensa en profundidad adicional.

``CREATE OR REPLACE`` preserva dueño (``takab_ingest``) y GRANTs existentes.

Revision ID: 0003_gov_ack_lock
Revises: 0002_ingest_support
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_gov_ack_lock"
down_revision: str | None = "0002_ingest_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Versión con candado de fila (upgrade). El SELECT toma FOR UPDATE OF i y el UPDATE
# reafirma state='open'; el resto es idéntico a la migración 0001.
_LOCKED = """
CREATE OR REPLACE FUNCTION gov_ack_incident(p_incident_id uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_tenant uuid;
  v_state  text;
  v_vis    text;
  v_actor  text;
BEGIN
  IF app_role() <> 'gov_operator' THEN
    RAISE EXCEPTION 'gov_ack_incident: solo gov_operator (rol actual=%)', app_role();
  END IF;

  SELECT i.tenant_id, i.state, t.visibility
    INTO v_tenant, v_state, v_vis
    FROM incidents i JOIN tenants t ON t.tenant_id = i.tenant_id
   WHERE i.incident_id = p_incident_id
     FOR UPDATE OF i;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'gov_ack_incident: incidente % inexistente', p_incident_id;
  END IF;
  IF v_vis <> 'gov_shared' THEN
    RAISE EXCEPTION 'gov_ack_incident: tenant no es gov_shared';
  END IF;
  IF v_state <> 'open' THEN
    RAISE EXCEPTION 'gov_ack_incident: transicion invalida % -> acked', v_state;
  END IF;

  UPDATE incidents SET state = 'acked'
   WHERE incident_id = p_incident_id AND state = 'open';

  v_actor := 'gov:' || coalesce(nullif(current_setting('app.user_id', true), ''), 'unknown');
  INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
  VALUES (v_tenant, v_actor, 'ack', 'incident:' || p_incident_id::text,
          jsonb_build_object('via', 'gov_ack_incident'));
END $fn$;
"""

# Versión original (downgrade): sin candado de fila ni guarda en el UPDATE.
_UNLOCKED = """
CREATE OR REPLACE FUNCTION gov_ack_incident(p_incident_id uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_tenant uuid;
  v_state  text;
  v_vis    text;
  v_actor  text;
BEGIN
  IF app_role() <> 'gov_operator' THEN
    RAISE EXCEPTION 'gov_ack_incident: solo gov_operator (rol actual=%)', app_role();
  END IF;

  SELECT i.tenant_id, i.state, t.visibility
    INTO v_tenant, v_state, v_vis
    FROM incidents i JOIN tenants t ON t.tenant_id = i.tenant_id
   WHERE i.incident_id = p_incident_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'gov_ack_incident: incidente % inexistente', p_incident_id;
  END IF;
  IF v_vis <> 'gov_shared' THEN
    RAISE EXCEPTION 'gov_ack_incident: tenant no es gov_shared';
  END IF;
  IF v_state <> 'open' THEN
    RAISE EXCEPTION 'gov_ack_incident: transicion invalida % -> acked', v_state;
  END IF;

  UPDATE incidents SET state = 'acked' WHERE incident_id = p_incident_id;

  v_actor := 'gov:' || coalesce(nullif(current_setting('app.user_id', true), ''), 'unknown');
  INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
  VALUES (v_tenant, v_actor, 'ack', 'incident:' || p_incident_id::text,
          jsonb_build_object('via', 'gov_ack_incident'));
END $fn$;
"""


def _exec(sql: str) -> None:
    """Ejecuta una sentencia por el cursor psycopg crudo (sin binding de params).

    El cuerpo tiene ``%`` (RAISE) y ``:`` que el binding interpretaría como
    placeholders; se corre igual que en la migración 0001. ``CREATE OR REPLACE``
    mantiene dueño y GRANTs, así que no hace falta re-ALTER OWNER.
    """
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_LOCKED)


def downgrade() -> None:
    _exec(_UNLOCKED)
