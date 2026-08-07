"""T-2.71 · `maintenance_windows`: el registro de qué vigilancia se apagó.

El efecto real de una ventana de mantenimiento NO vive aquí: vive en AWS, en una
CloudWatch alarm mute rule con `Duration` obligatoria que CloudWatch expira sola.
Esta tabla es la otra mitad — quién apagó qué, cuánto y **por qué** — y es la que
la consola lee para poder decirlo en pantalla mientras dure.

Por qué las dos mitades, y no solo una:

- Solo AWS: nadie sabría, sin entrar a la consola de CloudWatch, que las alarmas
  de un edificio están mudas. El criterio 2 de la ficha pide justo lo contrario.
- Solo la fila: silenciaría de mentira. La alarma seguiría paginando.

Y las dos direcciones de divergencia caen del lado seguro, que es lo que hace
aceptable tener dos estados: fila abierta + mute no aplicada ⇒ las alarmas SUENAN
durante el mantenimiento (ruidoso, pero seguro); mute aplicada + fila cerrada ⇒
AWS sigue silenciando, pero acotado por su propia `Duration`, que se fija igual a
la de la fila. Ninguna de las dos deja una alarma apagada indefinidamente.

`active` es un PREDICADO, no una columna (`now() < starts_at + duration`),
calcado de `drills` y de su comentario "sin worker de cierre". Es la respuesta
literal al criterio 3: la pregunta "¿y si el job de vencimiento muere?" se
contesta borrando el job.

Tabla NUEVA ⇒ `SET ROLE takab_migrator` (invariante de dueños del proyecto).
Idempotente (invariante T-1.45): `IF NOT EXISTS` en todo, y las políticas se
recrean con DROP previo.

**El REVOKE no es opcional**: el 0001 ejecuta `GRANT ... ON ALL TABLES IN SCHEMA
public` DESPUÉS de aplicar `db/schema.sql`, así que en una base NUEVA esta tabla
recibe DELETE aunque aquí solo se conceda SELECT/INSERT/UPDATE. Conceder de menos
no basta; hay que revocar. Se manifiesta SOLO en base nueva: en base incremental
pasa en verde y engaña (lección de la 0028).

Revision ID: 0030_maintenance_windows
Revises: 0029_gateway_fw_running
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_maintenance_windows"
down_revision: str | None = "0029_gateway_fw_running"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS maintenance_windows (
  window_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid REFERENCES tenants(tenant_id),
  gateway_id   uuid REFERENCES gateways(gateway_id),
  scope        text NOT NULL CHECK (scope IN ('gateway','platform')),
  opened_by    uuid NOT NULL,
  reason       text NOT NULL CHECK (length(btrim(reason)) >= 8),
  duration_s   integer NOT NULL CHECK (duration_s BETWEEN 300 AND 14400),
  opened_at    timestamptz NOT NULL DEFAULT now(),
  starts_at    timestamptz NOT NULL,
  closed_at    timestamptz,
  alarm_names  text[] NOT NULL DEFAULT '{}',
  missing_names text[] NOT NULL DEFAULT '{}',
  requested    integer NOT NULL DEFAULT 0,
  silenced     integer NOT NULL DEFAULT 0,
  mute_rule    text,
  mute_verified boolean NOT NULL DEFAULT true,
  CONSTRAINT mw_scope_coherente CHECK (
    (scope = 'gateway'  AND tenant_id IS NOT NULL AND gateway_id IS NOT NULL) OR
    (scope = 'platform' AND tenant_id IS     NULL AND gateway_id IS     NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_mw_tenant
  ON maintenance_windows (tenant_id, starts_at DESC);
CREATE INDEX IF NOT EXISTS idx_mw_gateway
  ON maintenance_windows (gateway_id, starts_at DESC)
  WHERE gateway_id IS NOT NULL;

RESET ROLE;

GRANT SELECT, INSERT, UPDATE ON maintenance_windows TO takab_app;
-- Ver la cabecera: sin estos REVOKE, una base NUEVA acaba con DELETE concedido
-- sobre el rastro de una vigilancia apagada.
REVOKE DELETE ON maintenance_windows FROM takab_app;
REVOKE ALL ON maintenance_windows FROM takab_ingest;

ALTER TABLE maintenance_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_windows FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mw_read  ON maintenance_windows;
DROP POLICY IF EXISTS mw_write ON maintenance_windows;
DROP POLICY IF EXISTS mw_admin ON maintenance_windows;

-- Las filas de PLATAFORMA llevan tenant_id NULL: `tenant_id = app_tenant_id()`
-- evalúa a NULL (no a true), así que solo las ve un rol interno. Mismo mecanismo
-- que las filas sin tenant de audit_log — no hace falta una rama aparte.
CREATE POLICY mw_read ON maintenance_windows FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY mw_write ON maintenance_windows FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY mw_admin ON maintenance_windows FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

COMMENT ON TABLE maintenance_windows IS
  'T-2.71: ventana de mantenimiento. `active` NO es columna, es el predicado '
  '`closed_at IS NULL AND now() < starts_at + duration_s` (sin worker de cierre, '
  'igual que drills). El silencio real lo aplica una CloudWatch alarm mute rule '
  'cuya Duration expira AWS: doble candado independiente.';
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Deliberadamente NO se borra la tabla: es el rastro de qué vigilancia estuvo
    # apagada y cuándo. Un downgrade que lo destruyera dejaría sin explicación el
    # hueco en los correos de on-call (mismo criterio de compliance que audit_log).
    pass
