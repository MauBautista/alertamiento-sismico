"""T-5.13 · una plantilla de simulacro se define una vez y se lanza en dos clics

Hasta aquí el alta de un simulacro tenía **cinco campos y ninguno era una
plantilla**. Lo más cercano —ejecutar una agenda ya armada (`from_scheduled`,
T-2.48)— **la consume** (`stop_reason='executed'`), así que no se puede
reutilizar: para el macrosimulacro de septiembre había que teclear los sitios, la
duración y la nota a mano, cada vez, en el caso de uso más visible del producto.

**Dos tablas y una columna.**

* `drill_templates` — nombre, duración y nota. El nombre es único **por tenant**
  para que «Macrosimulacro septiembre» signifique una sola cosa dentro de un
  cliente y no estorbe a los demás.
* `drill_template_sites` — el conjunto de sitios. **Vacío significa «todos los
  comandables»**, exactamente la misma convención que `DrillCreateIn.site_ids =
  None` y que el rótulo del modal («SIN SELECCIÓN ⇒ TODOS LOS SITIOS CON GABINETE
  COMANDABLE»). Dos convenciones distintas para lo mismo acabarían divergiendo.
* `drills.from_template_id` — **procedencia, no dependencia.** El simulacro copia
  los valores al crearse; esta columna solo dice de dónde salieron. Nada del
  camino de lectura la desreferencia para pintar el nombre actual de la
  plantilla: eso sería justo la reescritura que el criterio 2 prohíbe.
  `ON DELETE SET NULL` no hace falta —las plantillas se ARCHIVAN, no se
  borran— pero se declara igual: un `DELETE` manual en una consola de soporte no
  puede llevarse por delante el registro de un simulacro que ya sonó.

**Se archiva, no se borra.** `archived_at` sigue el patrón de la casa
(`sites.status='retired'`, `gateways`, `sensors`): una plantilla borrada de
verdad dejaría huérfana la procedencia de cada simulacro que salió de ella, y
esos registros son evidencia de cumplimiento. Desde fuera se comporta como un
borrado —desaparece de la lista y su nombre vuelve a estar libre—, que es lo que
pide el CRUD de la ficha.

**Sin rol nuevo.** El CRUD va con `drill_start`, el mismo permiso que ya autoriza
a disparar un simulacro (criterio 1). Un permiso nuevo habría obligado a mover la
matriz RBAC y sus dos espejos sin ganar nada: quien puede lanzar el simulacro
puede definir cómo se lanza.

Tabla PREEXISTENTE (`drills`) ⇒ su `ALTER` va **fuera** del `SET ROLE`; las dos
tablas nuevas, dentro (invariante de dueños de T-1.45, cuyo rojo aparece solo en
la nube). Idempotente: `IF NOT EXISTS` en todo, políticas con `DROP ... IF
EXISTS` antes de crearlas.

Revision ID: 0061_plantillas_de_simulacro
Revises: 0060_procedencia_del_catalogo
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0061_plantillas_de_simulacro"
down_revision: str | None = "0060_procedencia_del_catalogo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS drill_templates (
  template_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  name         text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
  -- Mismo rango que `drills.duration_s`: una plantilla que no se pudiera lanzar
  -- sería una trampa que solo salta al usarla.
  duration_s   integer NOT NULL CHECK (duration_s BETWEEN 30 AND 3600),
  note         text,
  created_by   uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  -- Se ARCHIVA, no se borra: cada simulacro que salió de ella la cita como
  -- procedencia, y eso es evidencia de cumplimiento.
  archived_at  timestamptz
);

-- El nombre identifica a la plantilla DENTRO de un cliente. Parcial sobre las
-- vivas: archivar libera el nombre, que es lo que espera quien «la borró».
CREATE UNIQUE INDEX IF NOT EXISTS uq_drill_templates_tenant_name
  ON drill_templates (tenant_id, lower(btrim(name))) WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_drill_templates_tenant
  ON drill_templates (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS drill_template_sites (
  template_id uuid NOT NULL REFERENCES drill_templates(template_id) ON DELETE CASCADE,
  site_id     uuid NOT NULL REFERENCES sites(site_id),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  PRIMARY KEY (template_id, site_id)
);

RESET ROLE;

ALTER TABLE drill_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE drill_templates FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS drill_templates_tenant ON drill_templates;
-- Una plantilla es configuración operativa, NO evidencia: `gov_operator` lee el
-- registro de simulacros (`drills_read` lo contempla) y aquí no pinta nada.
CREATE POLICY drill_templates_tenant ON drill_templates FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
DROP POLICY IF EXISTS drill_templates_admin ON drill_templates;
CREATE POLICY drill_templates_admin ON drill_templates FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE drill_template_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE drill_template_sites FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS drill_template_sites_tenant ON drill_template_sites;
CREATE POLICY drill_template_sites_tenant ON drill_template_sites FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
DROP POLICY IF EXISTS drill_template_sites_admin ON drill_template_sites;
CREATE POLICY drill_template_sites_admin ON drill_template_sites FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

GRANT SELECT, INSERT, UPDATE ON drill_templates TO takab_app;
GRANT SELECT, INSERT, DELETE ON drill_template_sites TO takab_app;

-- PROCEDENCIA del simulacro, no dependencia: los valores ya se copiaron. Tabla
-- PREEXISTENTE ⇒ este ALTER va como usuario de conexión, sin SET ROLE.
ALTER TABLE drills
  ADD COLUMN IF NOT EXISTS from_template_id uuid
  REFERENCES drill_templates(template_id) ON DELETE SET NULL;

COMMENT ON COLUMN drills.from_template_id IS
  'De qué plantilla se copió este simulacro (T-5.13). Es PROCEDENCIA: los valores '
  'del simulacro son suyos y editar la plantilla después no los reescribe. Nada '
  'del camino de lectura desreferencia esta columna para pintar el nombre actual.';
"""

_DOWN = """
ALTER TABLE drills DROP COLUMN IF EXISTS from_template_id;
DROP TABLE IF EXISTS drill_template_sites;
DROP TABLE IF EXISTS drill_templates;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
