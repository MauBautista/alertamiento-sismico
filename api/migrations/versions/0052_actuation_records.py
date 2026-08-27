"""T-2.86.a · La bitácora local de actuación sube cuando vuelve el enlace.

Cierra el criterio 2 de `T-2.86.a`, que era **lo único que quedaba abierto del
hueco `RO-4.e`** — el de más peso contractual de los 18.

El caso exacto para el que existe el gabinete —regla de oro 2, el edge opera sin
nube— era el único que no dejaba constancia en la nube: si el gas se cierra
durante un corte de internet, después nadie podía decir quién lo ordenó ni con
qué causa. El edge ya lo anotaba en disco desde el criterio 1; lo que faltaba era
el otro extremo del cable.

**`record_id` es la PK y viene DEL GABINETE**, no de aquí. Es lo que hace la
subida idempotente (regla de oro 3): el edge no borra su copia local al subir
—el perito la lee meses después—, avanza una marca de agua, y si esa marca se
pierde el gabinete re-sube filas que la nube ya tiene. Con `ON CONFLICT DO
NOTHING` sobre esta PK, re-subir es gratis. Sin ella, un reinicio desafortunado
duplicaría la bitácora justo del incidente que alguien va a peritar.

**`online` es tri-estado a propósito.** `true` = había enlace, `false` = no lo
había —que es la fila que responde a `RO-4.e`—, y `NULL` = **no se pudo saber**.
Colapsar el NULL a `false` sería inventar un dato en la tabla que existe
precisamente para que nadie tenga que inventarlo.

**No se poda nunca** (regla de oro 11): es tabla de auditoría, no de telemetría.
Por eso es una tabla normal y no un hypertable con retención — el volumen lo
permite porque el registro es POR EVENTO (regla de oro 10), no por intervalo.

**Sin `UNIQUE (gateway_id, seq)`**, y la ausencia es deliberada: `seq` es el
contador del fichero del gabinete y **se reinicia si el gabinete se
re-aprovisiona**. Un UNIQUE ahí convertiría un re-aprovisionamiento legítimo en
un rechazo permanente de toda su bitácora nueva. `seq` se guarda porque permite
detectar HUECOS —que es lo que un perito pregunta—, no para identificar.

Revision ID: 0052_actuation_records
Revises: 0051_consent_solo_sellado
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_actuation_records"
down_revision: str | None = "0051_consent_solo_sellado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `SET ROLE takab_migrator` porque la tabla es un objeto NUEVO: sin él quedaría a
# nombre del usuario de conexión, que en local es superusuario y en la nube no.
# Es la invariante de T-1.45, y su rojo aparece SOLO en la nube.
_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS actuation_records (
  record_id   uuid PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  site_id     uuid NOT NULL REFERENCES sites(site_id),
  gateway_id  uuid NOT NULL REFERENCES gateways(gateway_id),
  seq         bigint NOT NULL,
  occurred_at timestamptz NOT NULL,
  cause       text NOT NULL,
  actor       text NOT NULL,
  channel     text NOT NULL,
  action      text NOT NULL,
  success     boolean NOT NULL,
  detail      text NOT NULL DEFAULT '',
  event_id    text NOT NULL DEFAULT '',
  online      boolean,
  ingested_at timestamptz NOT NULL DEFAULT now()
);

-- La consulta del perito: «qué hizo ESTE gabinete, en orden». Y `occurred_at`
-- DESC porque siempre se pregunta por lo último primero.
CREATE INDEX IF NOT EXISTS idx_actuation_records_gateway_at
  ON actuation_records (gateway_id, occurred_at DESC);

-- La otra pregunta real: «¿qué se actuó a oscuras?». Índice PARCIAL porque las
-- filas con enlace son la inmensa mayoria y no interesan aquí.
CREATE INDEX IF NOT EXISTS idx_actuation_records_offline
  ON actuation_records (tenant_id, occurred_at DESC)
  WHERE online IS NOT TRUE;

RESET ROLE;

-- APPEND-ONLY, igual que `audit_log` y por la misma razón: es evidencia. La
-- ingesta solo hace INSERT ... ON CONFLICT DO NOTHING, así que no pierde nada —
-- y el día que alguien "corrija" una fila de la bitácora del incidente que se
-- está peritando, esto lo impide en la base y no en una revisión de código.
-- `DROP` antes de `CREATE` porque los triggers no admiten `IF NOT EXISTS` y esta
-- migración tiene que ser idempotente (invariante de T-1.45).
REVOKE UPDATE, DELETE ON actuation_records FROM PUBLIC;
DROP TRIGGER IF EXISTS trg_actuation_records_append_only ON actuation_records;
CREATE TRIGGER trg_actuation_records_append_only
  BEFORE UPDATE OR DELETE ON actuation_records
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

-- Escritura: SOLO la ingesta, que va con BYPASSRLS y por eso no aparece en las
-- políticas. `takab_app` LEE y no escribe: una bitácora que la API pudiera
-- escribir dejaría de ser prueba de lo que hizo el gabinete.
GRANT SELECT ON actuation_records TO takab_app;
-- La ingesta INSERTA y nada más: sin UPDATE ni DELETE, que es lo que hace de esto
-- una prueba y no un registro editable. El `ON CONFLICT DO NOTHING` de la re-subida
-- no necesita UPDATE — justamente por eso «no hacer nada» es la resolución correcta.
GRANT SELECT, INSERT ON actuation_records TO takab_ingest;

ALTER TABLE actuation_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE actuation_records FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS actuation_records_read ON actuation_records;
CREATE POLICY actuation_records_read ON actuation_records FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
"""

# NO hay política de escritura, y la ausencia ES la decisión (ver el GRANT).

_DOWN = """
DROP TABLE IF EXISTS actuation_records;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
