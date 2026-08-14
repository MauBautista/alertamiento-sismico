"""T-2.138 · Clave de reentrega para `audit_log` (huella + cubeta).

`T-2.136` midió los 7 caminos de la ingesta contra una reentrega real de SQS y
encontró UNO que no es idempotente: `ingest_reject`. `audit_log` es
`GENERATED ALWAYS AS IDENTITY` + `ts DEFAULT now()` y **no tiene clave natural**,
así que la evidencia del rechazo se escribía POR ENTREGA y no por hecho. La tabla
es append-only por trigger y no se poda jamás (regla de oro 11): el renglón de
más es permanente.

──────────────────────────────────────────────────────────────────────────────
1 · POR QUÉ LA CLAVE NO ES `(tenant, actor, verb, object, meta)`
──────────────────────────────────────────────────────────────────────────────
Porque colapsaría rechazos GENUINAMENTE DISTINTOS, que es peor que duplicar uno,
y esa es la razón escrita por la que `T-2.136` dejó el defecto abierto en vez de
taparlo. La razón del rechazo la compone el cross-check de identidad
(`ingest/handlers.check_identity`) y se repite igual cada vez: `station
desconocida para el gateway: 'XYZ'` sale idéntica para mensajes distintos. Una
clave permanente sobre el contenido borraría el segundo rechazo, el tercero y el
del año que viene.

Por eso la clave es **huella del contenido + CUBETA de tiempo**. La huella dice
"esto es el mismo hecho"; la cubeta lo acota a la ventana en la que una reentrega
de SQS es físicamente posible. Fuera de esa ventana el mismo rechazo vuelve a
dejar su fila, que es exactamente lo que se quería conservar.

──────────────────────────────────────────────────────────────────────────────
2 · POR QUÉ DOS COLUMNAS Y NO UNA
──────────────────────────────────────────────────────────────────────────────
La huella va sola en la columna de la izquierda del índice para que la
comprobación previa (`... WHERE dedupe_digest = X AND dedupe_bucket >= c - 1`)
use el MISMO índice que impone la unicidad. Un solo texto concatenado obligaría a
un segundo índice o a un `LIKE 'huella:%'`.

El `CHECK` cierra la media clave: una fila con huella y sin cubeta no la vigila
el índice parcial y se colaría. Lo impide la base, no el llamador.

──────────────────────────────────────────────────────────────────────────────
3 · IDEMPOTENCIA Y DUEÑOS (los dos invariantes de la casa)
──────────────────────────────────────────────────────────────────────────────
`audit_log` es una tabla PREEXISTENTE (0001), así que aquí NO se hace
`SET ROLE takab_migrator`: el DDL corre como el usuario de conexión —superusuario
en local, `takab_migrator` (que es su dueño) en la nube—. Un índice y un `CHECK`
no son objetos con dueño propio: heredan el de la tabla, así que no hay nada que
ceder. El `DROP CONSTRAINT IF EXISTS` antes del `ADD` es lo que hace idempotente
lo único que no tiene forma `IF NOT EXISTS`.

Tampoco hay `GRANT` nuevo: el `INSERT` sobre `audit_log` ya está concedido a
nivel de TABLA, que cubre toda columna nueva. Es la divergencia que midió
`T-2.78.a` (base nueva vs. existente) y aquí no se abre.

Revision ID: 0044_audit_dedupe_reentrega
Revises: 0043_pii_retention_runs
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044_audit_dedupe_reentrega"
down_revision: str | None = "0043_pii_retention_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UP = """
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS dedupe_digest text;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS dedupe_bucket bigint;

ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_dedupe_completa;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_dedupe_completa
  CHECK ((dedupe_digest IS NULL) = (dedupe_bucket IS NULL));

CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_log_dedupe
  ON audit_log (dedupe_digest, dedupe_bucket)
  WHERE dedupe_digest IS NOT NULL;
"""

_DOWN = """
DROP INDEX IF EXISTS idx_audit_log_dedupe;
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_dedupe_completa;
ALTER TABLE audit_log DROP COLUMN IF EXISTS dedupe_bucket;
ALTER TABLE audit_log DROP COLUMN IF EXISTS dedupe_digest;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
