"""T-2.148 · «Miré el catálogo y era el mismo» necesita dónde escribirse.

`push_catalog` publicaba SIEMPRE: versión nueva, firma, publish por IoT, upsert y
un renglón `catalog_published`, aunque el catálogo fuera byte a byte el que el
gabinete ya tiene. Con una persona llamando a mano no duele; con el job de `D-06`
cada pasada haría lo mismo, y las tres consecuencias son acumulativas:

  · la versión monótona escala sin motivo;
  · `audit_log` es append-only y EXENTA DE PODA (regla de oro 11), así que el
    renglón de ruido es **permanente**;
  · y cada publish DESPIERTA AL GABINETE y cuesta su línea en la política de flota.

Al no publicar hace falta lo contrario del silencio: constancia de que se miró.
Sin ella, «el job corre y no hay novedad» sería indistinguible de «el job murió»
— que es exactamente el modo de fallo que `D-06` quería evitar al automatizar
contra una fuente de terceros. `published_at` no sirve para eso: significa
«cuándo se publicó por última vez», y su virtud es justamente NO moverse cuando
no se publica.

──────────────────────────────────────────────────────────────────────────────
IDEMPOTENCIA Y DUEÑOS (los dos invariantes de la casa)
──────────────────────────────────────────────────────────────────────────────
`gateway_catalog_state` es una tabla PREEXISTENTE (0001), así que aquí NO se hace
`SET ROLE takab_migrator`: el DDL corre como el usuario de conexión —superusuario
en local, `takab_migrator` (que es su dueño) en la nube—. Una columna no es un
objeto con dueño propio: hereda el de la tabla.

Tampoco hay `GRANT` nuevo: el `UPDATE`/`INSERT` sobre la tabla ya está concedido a
nivel de TABLA, que cubre toda columna nueva. Es la divergencia que midió
`T-2.78.a` (base nueva vs. existente) y aquí no se abre.

La columna nace NULL a propósito: en un gabinete que nunca se ha comprobado, «no
se ha mirado nunca» y «se miró hace mucho» son hechos distintos, y NULL es el
único valor que no miente sobre el primero.

Revision ID: 0045_catalog_last_checked
Revises: 0044_audit_dedupe_reentrega
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0045_catalog_last_checked"
down_revision: str | None = "0044_audit_dedupe_reentrega"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UP = """
ALTER TABLE gateway_catalog_state
  ADD COLUMN IF NOT EXISTS last_checked_at timestamptz;
"""

_DOWN = """
ALTER TABLE gateway_catalog_state
  DROP COLUMN IF EXISTS last_checked_at;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
