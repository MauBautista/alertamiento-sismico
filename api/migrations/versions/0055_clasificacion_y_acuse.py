"""T-5.12 + T-5.14 · Clasificar un incidente, y cronometrar el acuse de un simulacro.

**T-5.12 — `incident_classifications`.** Hasta hoy cerrar un incidente no pedía
ni admitía una razón: `incidents.state` llegaba a `closed` y ahí moría la
pregunta. La consecuencia, medida en la auditoría V1-COMERCIAL: la tasa de falsos
positivos —la métrica que decide si un cliente renueva— **no era calculable ni a
mano sobre la base**, y el documento de entrega se deslinda de una tasa que el
sistema no mide.

Es **tabla propia y encadenada**, no una columna de `incidents`, por la misma
razón que los dictámenes: una corrección **inserta y declara a cuál sustituye**,
nunca reescribe. Quien clasificó mal a las 3 de la mañana no puede hacer
desaparecer su clasificación; la corrige, y las dos quedan.

**Y no hay valor por defecto.** `indeterminado` es una opción que se ELIGE, no el
sitio donde caen los que nadie miró: un default silencioso convertiría «nadie lo
revisó» en «se revisó y no se supo», que son cosas distintas y solo la primera
pide trabajo. Los no clasificados no tienen fila, y el endpoint de agregados los
cuenta aparte en vez de excluirlos del denominador.

**T-5.14 — `commands.acked_at` y `evidence_objects.drill_id`.**

`commands` guardaba el ack en un `jsonb` con el `executed_at` que manda el
GABINETE, y nada más. Para cronometrar un simulacro eso no sirve: el reloj del
gabinete es justo lo que el sistema vigila (`ntp_offset_s`), así que restarle
`issued_at` sería mezclar dos relojes. `acked_at` lo pone el SERVIDOR, con el
mismo reloj que `issued_at`, y por eso la diferencia significa algo.

`evidence_objects` ya tenía tres dueños posibles —incidente, sensor, o ninguno—;
el reporte de un simulacro es el cuarto. Va como columna nueva y no reutilizando
`incident_id` porque un simulacro **jamás crea incidente**
(`test_un_drill_jamas_crea_incidentes`), y colgarlo de uno sería inventar el
vínculo que esa prueba existe para negar.

Revision ID: 0055_clasificacion_y_acuse
Revises: 0054_demo_mode
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0055_clasificacion_y_acuse"
down_revision: str | None = "0054_demo_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `SET ROLE takab_migrator` SOLO para la tabla nueva. Los `ALTER` de abajo van
# fuera: son objetos PREEXISTENTES y su DDL lo hace el usuario de conexión
# (invariante de T-1.45, cuyo rojo aparece solo en la nube).
_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS incident_classifications (
  classification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id    uuid NOT NULL REFERENCES incidents(incident_id),
  -- Catálogo CERRADO y corto. `indeterminado` se ELIGE; no es donde caen los que
  -- nadie miró — ésos no tienen fila.
  classification text NOT NULL CHECK (classification IN
                 ('real','falso_positivo','prueba','indeterminado')),
  note           text NOT NULL DEFAULT '',
  classified_by  uuid NOT NULL,
  classified_at  timestamptz NOT NULL DEFAULT now(),
  -- Cadena de versiones, igual que `dictamens.supersedes_dictamen_id`: corregir
  -- INSERTA y declara a cuál sustituye. La vigente es la que nadie sustituye.
  supersedes_id  uuid REFERENCES incident_classifications(classification_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_classifications_incident
  ON incident_classifications (incident_id, classified_at DESC);

-- La consulta de la tasa: «qué pasó en este cliente entre estas dos fechas».
CREATE INDEX IF NOT EXISTS idx_incident_classifications_tenant_at
  ON incident_classifications (tenant_id, classified_at DESC);

RESET ROLE;

-- APPEND-ONLY con las DOS capas, igual que `dictamens` y `audit_log`: el
-- privilegio y el trigger. Con una sola, quitar el trigger «para una migración»
-- dejaría la clasificación editable sin que nada más lo impidiera.
REVOKE UPDATE, DELETE ON incident_classifications FROM PUBLIC;
REVOKE UPDATE, DELETE ON incident_classifications FROM takab_app;
DROP TRIGGER IF EXISTS trg_incident_classifications_append_only ON incident_classifications;
CREATE TRIGGER trg_incident_classifications_append_only
  BEFORE UPDATE OR DELETE ON incident_classifications
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

ALTER TABLE incident_classifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_classifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS incident_classifications_tenant ON incident_classifications;
CREATE POLICY incident_classifications_tenant ON incident_classifications
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

GRANT SELECT, INSERT ON incident_classifications TO takab_app;

-- [T-5.14] El instante del acuse, puesto por el SERVIDOR. El `executed_at` del
-- `ack` jsonb lo manda el gabinete y su reloj es justo lo que el sistema vigila:
-- restarle `issued_at` mezclaría dos relojes. Éste comparte reloj con `issued_at`
-- y por eso su diferencia significa algo.
ALTER TABLE commands ADD COLUMN IF NOT EXISTS acked_at timestamptz;

-- [T-5.14] El cuarto dueño posible de una evidencia. NO se reutiliza
-- `incident_id` porque un simulacro jamás crea incidente, y colgarlo de uno
-- sería inventar el vínculo que `test_un_drill_jamas_crea_incidentes` niega.
ALTER TABLE evidence_objects ADD COLUMN IF NOT EXISTS drill_id uuid REFERENCES drills(drill_id);
"""

_DOWN = """
DROP TABLE IF EXISTS incident_classifications;
ALTER TABLE commands DROP COLUMN IF EXISTS acked_at;
ALTER TABLE evidence_objects DROP COLUMN IF EXISTS drill_id;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
