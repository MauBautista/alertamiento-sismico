"""T-5.24 · la pérdida de paquetes llega al centro de operaciones

El gabinete la mide y la PUBLICA en cada latido, y la ingesta la tiraba a
propósito: `device_health` no tenía columna, y el comentario del handler decía
que era «consumo local del panel LAN» (`T-1.53`).

La consecuencia, medida: **el SOC no puede ver la pérdida de paquetes de ningún
gabinete**. Para diagnosticar un enlace sensor→Pi degradado hay que ir al sitio o
abrir el panel por red local — justo el viaje que la flota existe para evitar. Y
es la señal que se degrada ANTES de que falten datos: cuando el hueco aparece en
`seedlink_lag_s`, la ventana de evidencia ya se perdió.

`real` y no `numeric`: es un porcentaje que el gabinete reporta con un decimal, y
la precisión de `real` sobra. NULL sigue significando «el gabinete no opina»
(contrato viejo o clave ausente) ⇒ la flota pinta S/D, nunca un cero — que aquí
sería «enlace perfecto» y es la mentira cara.

`device_health` es hypertable SIN compresión ([ANALISIS-00] v1.2: columnstore y
RLS son incompatibles), así que este `ADD COLUMN` no choca con chunks
comprimidos — es el mismo terreno que ya pisó la `0036`.

Sin índice: se lee siempre por el `LATERAL` que ya ordena por `(gateway_id, ts
DESC)`, nunca se filtra por este valor.

Revision ID: 0059_perdida_de_paquetes
Revises: 0058_cuota_de_ia
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0059_perdida_de_paquetes"
down_revision: str | None = "0058_cuota_de_ia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DDL sobre tabla PREEXISTENTE ⇒ como usuario de conexión, sin `SET ROLE`
    # (la invariante de dueños: `SET ROLE takab_migrator` es solo para objetos
    # nuevos, y aquí romperlo dejaría la columna con otro dueño que la tabla).
    op.get_bind().exec_driver_sql(
        "ALTER TABLE device_health ADD COLUMN IF NOT EXISTS packet_loss_pct real"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("ALTER TABLE device_health DROP COLUMN IF EXISTS packet_loss_pct")
