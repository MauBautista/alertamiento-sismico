"""T-7.53 · la nube puede ver que un gabinete retiene evidencia (y su disco).

## El defecto

La edad del pendiente más viejo sólo la comparaba el **panel LAN** del gabinete
contra su propio umbral, y `HealthSnapshot` no tenía campo para ella. Así que el
2026-09-17, con la evidencia de un incidente **EN REVISIÓN** esperando 49 minutos
en el disco del Pi, la nube no tenía forma de enterarse — lo delató mirar el
panel a mano.

## ⚠️ Y `disk_used_pct` llevaba MESES perdiéndose en silencio

Está en el contrato desde `T-1.53` y **nunca tuvo columna**: el handler lo recibe
y lo tira. El gabinete lo publica en cada latido, el panel LAN lo pinta, y la
nube —que es desde donde se vigila la flota— no lo ha visto jamás. Entra en esta
misma migración porque es el mismo defecto y el mismo fichero: un campo del
contrato sin destino no avisa de nada, simplemente desaparece.

## Las cuatro columnas

* ``disk_used_pct``            — el hueco de `T-1.53`.
* ``evidence_pending``         — NULL = **no pude preguntar**; 0 = no retengo nada.
* ``evidence_oldest_age_s``    — segundos que lleva esperando el más viejo.
* ``evidence_oldest_event_id`` — ⚠️ el vínculo con el incidente. Sin él la nube no
  puede evaluar «retiene evidencia **y** su incidente ya está en revisión», que es
  el predicado que importa: el caso de los 49 minutos pasaba **por debajo** del
  tope del gabinete (3 600 s) sin que sonara nada, así que la hora absoluta no
  sirve como umbral.

## Lo que esta migración NO hace, y por qué

**No lleva el bloque `NO FORCE` de la `0063`/`0066`.** `device_health` tiene RLS
`ENABLE` pero **no** `FORCE`, y es deliberado: los jobs de retención de
TimescaleDB corren como dueño y con FORCE verían cero filas. Además aquí no hay
ningún `UPDATE` de filas —sólo `ADD COLUMN`—, así que no hay nada que la RLS
pueda esconder. Ponerlo endurecería o aflojaría la tabla como efecto colateral, y
`api/tests/ops/test_rls_no_force_declarada.py` compara la lista por IGUALDAD.

**No necesita `GRANT`.** La `0001` concede `SELECT, INSERT, UPDATE` sobre todas
las tablas del esquema a `takab_ingest` después de aplicar `db/schema.sql`, y una
columna nueva de una tabla existente hereda el privilegio de tabla.

⚠️ **IDEMPOTENTE**, como exige el invariante: `db/schema.sql` es el esquema final
y se aplica ANTES, así que esta migración se encuentra su propio trabajo hecho.
"""

from __future__ import annotations

from alembic import op

revision: str = "0067_evidencia_retenida"
down_revision: str | None = "0066_cierre_con_hora"
branch_labels = None
depends_on = None


#: `evidence_oldest_event_id` es `uuid` y no `text` para que el cruce con
#: `incidents.event_uuid` sea directo. El handler VALIDA la forma antes de
#: escribir y manda NULL si no casa: un identificador malformado no puede tumbar
#: el latido entero, que es el dato de salud de un gabinete.
_COLUMNAS = (
    "ALTER TABLE device_health"
    "  ADD COLUMN IF NOT EXISTS disk_used_pct real,"
    "  ADD COLUMN IF NOT EXISTS evidence_pending int,"
    "  ADD COLUMN IF NOT EXISTS evidence_oldest_age_s real,"
    "  ADD COLUMN IF NOT EXISTS evidence_oldest_event_id uuid"
)

_COMENTARIOS = """
COMMENT ON COLUMN device_health.disk_used_pct IS
  '[T-7.53] Porcentaje de disco usado del gabinete. Viajaba en el contrato desde '
  'T-1.53 y no tenia columna: la nube llevaba meses tirandolo en silencio. '
  'NULL = el gabinete no opina (sin dato), jamas un cero.';
COMMENT ON COLUMN device_health.evidence_pending IS
  '[T-7.53] Evidencias que el gabinete RETIENE sin subir. NULL = NO PUDO '
  'PREGUNTAR (barrido del directorio fallido); 0 = pregunto y no retiene nada. '
  'La distincion es el punto: un gabinete con el backfill caido no puede '
  'declarar que no retiene evidencia.';
COMMENT ON COLUMN device_health.evidence_oldest_age_s IS
  '[T-7.53] Segundos que lleva esperando la evidencia pendiente mas vieja, '
  'medidos contra el reloj del GABINETE. NULL = sin pendientes o sin medida.';
COMMENT ON COLUMN device_health.evidence_oldest_event_id IS
  '[T-7.53] event_id de esa evidencia, que es el mismo que la nube convierte en '
  'incidents.event_uuid. Sin el no se puede evaluar el predicado que importa: '
  'retiene evidencia Y su incidente ya esta en revision. NULL = sin pendiente o '
  'identificador malformado (el handler lo valida antes de escribir).';
"""


def upgrade() -> None:
    op.execute(_COLUMNAS)
    op.execute(_COMENTARIOS)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE device_health"
        "  DROP COLUMN IF EXISTS evidence_oldest_event_id,"
        "  DROP COLUMN IF EXISTS evidence_oldest_age_s,"
        "  DROP COLUMN IF EXISTS evidence_pending,"
        "  DROP COLUMN IF EXISTS disk_used_pct"
    )
