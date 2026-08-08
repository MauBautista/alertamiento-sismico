"""T-2.70.a·B1 · `device_health.relays_state`: si el gabinete pudo mirar sus relés.

D3 sacó al dueño de los pines a su propio proceso (`takab-gpio`, gobernado por
`TAKAB_EDGE_GPIO_OWNER`). Desde entonces existe un estado alcanzable en
producción que antes no lo era: `gpio_owner=gpio` con `takab-gpio` caído o sin
habilitar. En ese estado el gabinete **no tiene sirena, ni cierre de gas, ni
retorno de ascensores, ni retenedores** — y `takab-edge` sigue latiendo
perfectamente.

Consecuencia MEDIDA antes de esta migración: el latido salía idéntico al de un
gabinete sano salvo por `relays: []`, que la nube no podía distinguir de «el
módulo de relés está detenido» (benigno). Ninguna de las 8 alarmas de
observabilidad mira los relés; `gateway_offline` no dispara porque el proceso que
late está vivo; el único aviso era un `log.critical` en el journal del Pi. El SOC
veía verde un edificio sin ninguna de sus cuatro protecciones.

El edge ya lo declara (contrato 1.10.0: `relays` nullable). Aquí se le da columna
al hecho, con TRES valores y un cuarto implícito:

  · `reported`   el gabinete publicó su censo de relés.
  · `stopped`    preguntó y no hay filas (módulo detenido / sin relés cableados).
  · `unreadable` **no pudo preguntar**. Nadie contesta como dueño de los pines.
  · NULL         el gabinete no opina (contrato viejo, o payload sin la clave).

POR QUÉ EN `device_health` Y NO EN `gateways`. Es un hecho FECHADO, no un
atributo del inventario: importa cuándo dejó de poder mirarse los relés y cuándo
volvió. La fila de salud es append-only por instante (`ON CONFLICT (ts,
gateway_id) DO NOTHING`), así que un reenvío no pisa lo escrito y el `unreadable`
jamás sobrescribe un censo bueno anterior — sólo añade el instante en que se
perdió. Además la consola lo lee GRATIS: el `LATERAL` de `queries/fleet.py` ya
trae el último `device_health` por gabinete.

NO se persiste el censo de relés en sí (canal a canal). No tiene consumidor en la
nube, y un jsonb por latido sobre una hypertable con 12 meses de retención es
coste real por cero lectores. Lo que la nube necesita para dejar de mentir es
saber SI el dato existe.

COMPATIBILIDAD HACIA ATRÁS. Un gabinete con firmware ≤1.9.0 sigue latiendo y
sigue mandando `relays: []` o su lista; nada se rompe. Su `[]` aterriza como
`stopped`, y esa lectura es honesta para él: hasta D3 el dueño de los pines vivía
en el mismo proceso, no había transporte que caerse, y el `null` que significa
«no pude preguntar» ese firmware no lo sabe emitir. Por eso `stopped` NO degrada
el estado de flota —sería degradar sobre un dato que en el firmware viejo es
ambiguo— y `unreadable`, que sólo puede emitir un gabinete ≥1.10.0 y sólo cuando
de verdad no pudo leer, SÍ.

`device_health` es hypertable SIN compresión ([ANALISIS-00] v1.2: columnstore y
RLS son incompatibles), así que un `ADD COLUMN` no choca con chunks comprimidos.

Sin índice: se lee siempre por el `LATERAL` que ya ordena por `(gateway_id, ts
DESC)`, nunca se filtra por este valor.

Tabla PREEXISTENTE ⇒ DDL como usuario de conexión, SIN ``SET ROLE``
(invariante de dueños del proyecto). Idempotente (invariante T-1.45): el
``ADD COLUMN IF NOT EXISTS`` y el ``DO`` que consulta ``pg_constraint`` permiten
re-aplicarla sin error.

Revision ID: 0036_device_health_relays_state
Revises: 0035_retention_geom_policy
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0036_device_health_relays_state"
down_revision: str | None = "0035_retention_geom_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE device_health ADD COLUMN IF NOT EXISTS relays_state text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'device_health'::regclass
       AND conname  = 'device_health_relays_state_check'
  ) THEN
    ALTER TABLE device_health ADD CONSTRAINT device_health_relays_state_check
      CHECK (relays_state IS NULL
             OR relays_state IN ('reported','stopped','unreadable'));
  END IF;
END $$;

COMMENT ON COLUMN device_health.relays_state IS
  'T-2.70.a: si el gabinete pudo leer el censo de sus reles en este latido. '
  'reported = lo publico; stopped = pregunto y no hay filas (modulo detenido); '
  'unreadable = NO PUDO PREGUNTAR (nadie contesta como dueno de los pines: '
  'gpio_owner=gpio con takab-gpio caido ⇒ sin sirena, sin gas, sin ascensores y '
  'sin retenedores mientras takab-edge sigue latiendo). NULL = el gabinete no '
  'opina (contrato <=1.9.0 o clave ausente) ⇒ S/D, nunca verde.';
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Borrar la columna devolveria «no pude preguntar» y «no hay relés» al mismo
    # rótulo, que es exactamente el defecto que esta migración cierra: un
    # edificio sin ninguna de sus cuatro protecciones, invisible desde el SOC.
    # Mismo criterio que 0021/0022/0023/0025/0028/0029.
    pass
