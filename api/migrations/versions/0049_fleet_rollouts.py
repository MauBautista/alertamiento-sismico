"""T-2.70 · Canary por cohortes: primero uno, se observa, luego el resto.

*«Un despliegue a toda la flota a la vez es un incidente a toda la flota a la
vez.»* El gabinete ya sabe activar con remojo y volver atrás solo; lo que no
existía era la disciplina de ORDEN entre gabinetes — y sin ella el canary es una
buena intención que se salta quien tiene prisa.

**Dos tablas, a imagen de `drills`/`drill_sites`**, que es el precedente exacto:
una cabecera por operación y una fila por sitio con su comando. Y con
`tenant_id` en LAS DOS (regla de oro 5) porque un rollout es POR TENANT a
propósito: actualizar toda la flota de una vez es justo lo que esta ficha existe
para impedir, así que forzar un rollout por cliente no es una limitación del
modelo — es la política, escrita donde no se puede saltar.

**`target_fw` se guarda y no se deriva al leer.** Es el SHA que
`gateways.fw_running` tiene que declarar para que el canary cuente como
CONFIRMADO. Derivarlo en cada consulta obligaría a re-parsear el `release_id`
cada vez y a que dos sitios distintos pudieran discrepar sobre qué se estaba
esperando; guardarlo lo congela en el momento en que se decidió.

Revision ID: 0049_fleet_rollouts
Revises: 0048_command_update_actions
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0049_fleet_rollouts"
down_revision: str | None = "0048_command_update_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Idempotente (invariante de T-1.45: sobre una base donde 0001 aplicó el
# schema.sql FINAL, esto es un no-op lógico). Las políticas se recrean con DROP
# IF EXISTS porque `CREATE POLICY` no admite `IF NOT EXISTS`.
# `SET ROLE takab_migrator` porque estas tablas son objetos NUEVOS, y sin él
# quedarían a nombre del usuario de conexión — que en local es superusuario y en
# la nube no. Es la invariante de T-1.45 medida a golpes: una migración FUTURA
# que hiciera `SET ROLE takab_migrator` moriría sobre una tabla ajena, y el rojo
# aparecería en la nube después de haber salido verde en local.
_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS fleet_rollouts (
  rollout_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  release_id   text NOT NULL,
  target_fw    text NOT NULL,
  created_by   uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  state        text NOT NULL DEFAULT 'canary'
               CHECK (state IN ('canary','desplegado','abortado')),
  finished_at  timestamptz,
  abort_reason text
);

CREATE TABLE IF NOT EXISTS fleet_rollout_sites (
  rollout_id   uuid NOT NULL REFERENCES fleet_rollouts(rollout_id) ON DELETE CASCADE,
  site_id      uuid NOT NULL REFERENCES sites(site_id),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  phase        text NOT NULL CHECK (phase IN ('canary','resto')),
  command_id   uuid REFERENCES commands(command_id),
  activated_at timestamptz,
  PRIMARY KEY (rollout_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_fleet_rollouts_tenant_created
  ON fleet_rollouts (tenant_id, created_at DESC);

RESET ROLE;

GRANT SELECT, INSERT, UPDATE ON fleet_rollouts TO takab_app;
GRANT SELECT, INSERT, UPDATE ON fleet_rollout_sites TO takab_app;

ALTER TABLE fleet_rollouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleet_rollouts FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fleet_rollouts_read ON fleet_rollouts;
CREATE POLICY fleet_rollouts_read ON fleet_rollouts FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
DROP POLICY IF EXISTS fleet_rollouts_admin ON fleet_rollouts;
CREATE POLICY fleet_rollouts_admin ON fleet_rollouts FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE fleet_rollout_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleet_rollout_sites FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fleet_rollout_sites_read ON fleet_rollout_sites;
CREATE POLICY fleet_rollout_sites_read ON fleet_rollout_sites FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
DROP POLICY IF EXISTS fleet_rollout_sites_admin ON fleet_rollout_sites;
CREATE POLICY fleet_rollout_sites_admin ON fleet_rollout_sites FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
"""

# NO hay política de ESCRITURA por tenant, y la ausencia es la decisión: quien
# escribe aquí es `deploy_firmware`, que sólo tiene `takab_superadmin` — o sea
# `app_is_takab_internal()`. Una política de escritura por `tenant_id` abriría la
# tabla a un `tenant_admin` cuya sesión coincidiera en tenant, que es justo el
# rol al que la matriz le niega empujar código. La LECTURA sí es por tenant: un
# cliente puede ver que a sus gabinetes se les está actualizando, y ocultárselo
# sería la clase de opacidad que la regla de oro 7 persigue.

_DOWN = """
DROP TABLE IF EXISTS fleet_rollout_sites;
DROP TABLE IF EXISTS fleet_rollouts;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
