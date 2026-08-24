"""T-2.84.e · `site_ground_refs` gana su `tenant_id` — la lectura LITERAL de la regla 5.

El aislamiento de esta tabla **ya era real** antes de esta migración: la RLS lo
imponía con un `EXISTS` contra `sites`, y el cruce de tenants estaba verificado
(el tenant B veía 0 filas, el dueño 1). Lo que faltaba era la lectura literal de
la regla de oro 5 —*`tenant_id` en toda tabla de negocio*— y con ella una línea
menos en la lista de exenciones del censo. Cada exención es algo que alguien
tiene que volver a justificar; una menos es una menos.

## EL BACKFILL SE FILTRABA A SÍ MISMO, y está MEDIDO

`site_ground_refs`, `sites` y `sensors` las **posee `takab_migrator`** y las tres
llevan `FORCE ROW LEVEL SECURITY`, que aplica RLS **también al dueño**. Alembic
conecta como ese dueño. Así que el backfill obvio —el que la ficha describía—

    UPDATE site_ground_refs sgr SET tenant_id = s.tenant_id
      FROM sites s WHERE s.site_id = sgr.site_id

actualiza **CERO filas y no se queja**: `sgr_write` exige
`s.tenant_id = app_tenant_id()`, y en una migración `app_tenant_id()` es NULL.
Medido sobre una fila real: variante obvia → **0**; con `FORCE` levantado → **1**.

En una base con datos el `SET NOT NULL` de abajo habría abortado la migración —
ruidoso, y por suerte. En una base sin filas de suelo habría pasado en verde
dejando el invariante sin demostrar. Ninguno de los dos desenlaces es aceptable
para algo que se aplica a la nube después de salir verde en local.

## POR QUÉ SE LEVANTA `FORCE` SÓLO AQUÍ, Y NO EN `sites`

Hay tres formas de que el backfill vea lo que necesita y sólo una es mínima:

* levantar `FORCE` en `sites` — funciona, y toca la isolación de la tabla más
  central del esquema aunque sea un instante. **Descartada.**
* declarar `app.role = 'takab_superadmin'` a secas — no basta: eso abre
  `sites_read`, pero el que bloquea es `sgr_write` sobre la tabla destino.
  **Medido: 0 filas.**
* levantar `FORCE` **sólo en `site_ground_refs`** (la tabla que esta migración
  está alterando, y de la que ya es dueña) **y** declarar `app.role` para que
  `sites_read` deje leer. **Es lo que se hace**, y `FORCE` se restaura dos
  sentencias después, dentro de la misma transacción.

## LAS DOS POLÍTICAS CONSERVAN A QUIÉN DEJABAN PASAR

`sgr_read` era `EXISTS (SELECT 1 FROM sites …)` **sin condición de tenant**: bajo
RLS, ese `SELECT` anidado ve exactamente lo que `sites_read` permite — o sea el
propio tenant, TAKAB interno, `gov_operator` sobre tenants `gov_shared` y los
grants de metadatos de T-1.73. Escribir `tenant_id = app_tenant_id()` a secas
habría **quitado** las tres últimas sin que nada se quejara, que es la clase de
regresión que una migración de "sólo añadir una columna" no debería poder
introducir. Así que la política nueva enumera los cuatro caminos explícitamente.

Y NO se añade una política `sgr_admin`: hoy no existe, así que TAKAB interno
puede LEER pero no ESCRIBIR esta tabla, y cambiar eso sería ampliar permisos en
una migración que nadie revisó por eso.

**Sin `SET ROLE takab_migrator`**: la tabla es PREEXISTENTE. El invariante de
T-1.45 pide el `SET ROLE` sólo para objetos NUEVOS; usarlo aquí es lo que mata a
la migración siguiente.

Revision ID: 0050_site_ground_refs_tenant
Revises: 0049_fleet_rollouts
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050_site_ground_refs_tenant"
down_revision: str | None = "0049_fleet_rollouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE site_ground_refs
  ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES tenants(tenant_id);

-- Ventana ACOTADA y declarada: sólo esta tabla, sólo para el backfill, y
-- restaurada dos sentencias más abajo. Ver el docstring.
ALTER TABLE site_ground_refs NO FORCE ROW LEVEL SECURITY;
SET LOCAL app.role = 'takab_superadmin';

UPDATE site_ground_refs sgr
   SET tenant_id = s.tenant_id
  FROM sites s
 WHERE s.site_id = sgr.site_id
   AND sgr.tenant_id IS NULL;

ALTER TABLE site_ground_refs FORCE ROW LEVEL SECURITY;
RESET app.role;

-- Fail-closed: si algo quedó sin tenencia, la migración PARA. Una fila de
-- referencia de suelo sin dueño es exactamente lo que esta tarea existe para que
-- no exista, y descubrirlo aquí es infinitamente más barato que en una consulta.
DO $$
DECLARE huerfanas bigint;
BEGIN
  SELECT count(*) INTO huerfanas FROM site_ground_refs WHERE tenant_id IS NULL;
  IF huerfanas > 0 THEN
    RAISE EXCEPTION 'quedan % filas de site_ground_refs sin tenant_id: el backfill no '
                    'las alcanzó (¿RLS?), y poner NOT NULL encima las escondería', huerfanas;
  END IF;
END $$;

ALTER TABLE site_ground_refs ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_site_ground_refs_tenant
  ON site_ground_refs (tenant_id);

-- Las dos políticas, ahora por COLUMNA. Conservan exactamente a quién dejaban
-- pasar: el `EXISTS` heredaba de `sites_read` cuatro caminos, no uno.
DROP POLICY IF EXISTS sgr_read ON site_ground_refs;
CREATE POLICY sgr_read ON site_ground_refs FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id) OR app_can_view_meta(tenant_id));
DROP POLICY IF EXISTS sgr_write ON site_ground_refs;
CREATE POLICY sgr_write ON site_ground_refs FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
"""

# El downgrade devuelve las políticas al `EXISTS` y suelta la columna. No
# reconstruye la tenencia porque no hace falta: se deriva de `sites` igual que
# antes de esta migración.
_DOWN = """
DROP POLICY IF EXISTS sgr_read ON site_ground_refs;
CREATE POLICY sgr_read ON site_ground_refs FOR SELECT
  USING (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id));
DROP POLICY IF EXISTS sgr_write ON site_ground_refs;
CREATE POLICY sgr_write ON site_ground_refs FOR ALL
  USING (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id
                   AND s.tenant_id = app_tenant_id()) AND app_role() <> 'gov_operator')
  WITH CHECK (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id
                        AND s.tenant_id = app_tenant_id()) AND app_role() <> 'gov_operator');
DROP INDEX IF EXISTS idx_site_ground_refs_tenant;
ALTER TABLE site_ground_refs DROP COLUMN IF EXISTS tenant_id;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
