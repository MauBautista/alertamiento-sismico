"""T-5.15 · el acuse de gobierno también entra en la bitácora del incidente

``gov_ack_incident`` movía el incidente ``open→acked`` y escribía **solo**
``audit_log``. El resultado, encontrado haciendo `T-5.15`: un incidente acusado
por Protección Civil salía ``acked`` en la consola **con la bitácora sin un solo
acuse**. La pantalla que existe para reconstruir lo ocurrido afirmaba que nadie
había acusado, al lado del estado que decía lo contrario.

No es un hueco, es una contradicción — y la bitácora es evidencia de compliance
exenta de poda: lo que no se escribe ahí no existe para un perito.

La fila lleva ``latency_s`` igual que la del acuse de tenant y que las de
``notify_sent``/``notify_delivered``, calculada dentro de la misma función y con
el reloj de la base. El actor mantiene el prefijo ``gov:`` que ya usaba
``audit_log``, así que las dos vías se distinguen sin mirar nada más.

``CREATE OR REPLACE`` preserva dueño (``takab_ingest``, BYPASSRLS: la política
``actions_insert`` niega a ``gov_operator`` la escritura DIRECTA, y esta función
es justamente la vía sancionada) y los GRANTs existentes.

Revision ID: 0056_gov_ack_bitacora
Revises: 0055_clasificacion_y_acuse
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0056_gov_ack_bitacora"
down_revision: str | None = "0055_clasificacion_y_acuse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CON_BITACORA = """
CREATE OR REPLACE FUNCTION gov_ack_incident(p_incident_id uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_tenant uuid;
  v_state  text;
  v_vis    text;
  v_actor  text;
  v_opened timestamptz;
BEGIN
  IF app_role() <> 'gov_operator' THEN
    RAISE EXCEPTION 'gov_ack_incident: solo gov_operator (rol actual=%)', app_role();
  END IF;

  SELECT i.tenant_id, i.state, t.visibility, i.opened_at
    INTO v_tenant, v_state, v_vis, v_opened
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

  -- [T-5.15] La fila que faltaba. Mismo `latency_s` y mismo `t0` que el acuse de
  -- tenant y que `notify_sent`: las tres cifras se comparan sin traducir nada.
  INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
  VALUES (p_incident_id, v_tenant, 'ack', v_actor,
          jsonb_build_object('via', 'gov_ack_incident',
                             'latency_s', EXTRACT(EPOCH FROM (now() - v_opened))));

  INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
  VALUES (v_tenant, v_actor, 'ack', 'incident:' || p_incident_id::text,
          jsonb_build_object('via', 'gov_ack_incident'));
END $fn$;
"""

# Versión previa (downgrade): sin la fila en `incident_actions`.
_SIN_BITACORA = """
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


def _exec(sql: str) -> None:
    """Por el cursor psycopg crudo: el cuerpo lleva ``%`` (RAISE) y ``:`` que el
    binding tomaría por placeholders. ``CREATE OR REPLACE`` mantiene dueño y
    GRANTs, así que no hace falta re-ALTER OWNER."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_CON_BITACORA)


def downgrade() -> None:
    _exec(_SIN_BITACORA)
