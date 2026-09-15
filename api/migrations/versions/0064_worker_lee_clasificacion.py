"""T-7.13 · el worker de incidentes LEE la clasificación.

`D-33` le da a la clasificación terminal (`falso_positivo`, `prueba`) el poder de
cerrar el registro, y quien lo ejecuta es `run_lifecycle_pass` dentro del worker
`takab_api.incident`, que conecta como `takab_ingest`. La tabla la creó `0055`
con un único destinatario —`GRANT SELECT, INSERT ON incident_classifications TO
takab_app`—, porque hasta ahora solo la API la tocaba.

Sin esta migración el worker levanta, corre y muere en cada pasada con
`permission denied for table incident_classifications`: la mitad de la lógica en
verde en local (donde los tests corren como superusuario) y **imposible en la
nube**, que es exactamente la trampa que documenta `migrations-must-be-idempotent`
y que ya costó un despliegue con el `GRANT` de la `0001`.

**Solo SELECT.** El worker decide a partir de la clasificación; no clasifica. Un
`INSERT` aquí le permitiría al sistema escribirse a sí mismo la razón por la que
cerró un incidente, y esa firma tiene que seguir siendo de una persona.

`takab_ingest` es BYPASSRLS, así que el `FORCE ROW LEVEL SECURITY` de la tabla no
le aplica: lo único que le faltaba era el privilegio.

Revision ID: 0064_worker_lee_clasificacion
Revises: 0063_disparo_de_apertura
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0064_worker_lee_clasificacion"
down_revision: str | None = "0063_disparo_de_apertura"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `GRANT` es idempotente por naturaleza (re-ejecutarlo no cambia nada), así que
# no hace falta guarda. Se ejecuta como el usuario de conexión —superusuario en
# local, `takab_migrator` (dueño de la tabla) en la nube—: es DDL sobre una tabla
# PREEXISTENTE y por eso NO lleva `SET ROLE`.
_UP = "GRANT SELECT ON incident_classifications TO takab_ingest;"

_DOWN = "REVOKE SELECT ON incident_classifications FROM takab_ingest;"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
