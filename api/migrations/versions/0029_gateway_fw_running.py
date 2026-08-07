"""T-2.70 · `gateways.fw_running`: qué código CORRE, no solo cuál hay en disco.

`gateways.fw_version` guarda lo que el gabinete lee de su archivo ``FW_VERSION``
en CADA latido. Eso responde «¿alguien tocó el disco?» (T-1.74) y lo responde
bien. NO responde «¿se aplicó la actualización?», y la diferencia no es sutil:

`deploy/edge/deploy.sh` escribe ``FW_VERSION`` en la línea 44 y reinicia en la
61. Tiene que ser en ese orden, porque el ``rsync --delete`` de la línea 31
borraría el archivo si se escribiera antes. Entre esas dos líneas —y **para
siempre** si el ``uv sync`` revienta, si el restart nunca ocurre, o si la unidad
agota su ``StartLimitBurst`` y queda en ``failed``— el proceso VIEJO publica la
versión NUEVA en su latido.

Consecuencia medida: un canary cuyo criterio de éxito fuera «volvió el
`fw_version` esperado» daría VERDE a una actualización que no se aplicó, y el
rollback automático colgado de esa señal no dispararía JAMÁS. Es el patrón
«PUBLICADO ≠ ENTREGADO» de esta fase, en su variante «ESCRITO ≠ CORRIENDO».

El edge ya declara ambas (contrato 1.9.0: ``fw_version`` releída del archivo,
``fw_running`` congelada al importar el módulo). Aquí se le da columna a la
segunda. **Aditiva y nullable**: los gabinetes con contrato ≤1.8.0 no la mandan,
no opinan, y su ausencia jamás pisa lo conocido (misma disciplina que
`fw_version`: ausente ≠ null ≠ basura, ver `ingest/handlers.py::_fw_field`).

Sin índice: se lee siempre junto a la fila del gateway, nunca se filtra por ella.

Tabla PREEXISTENTE ⇒ DDL como usuario de conexión, SIN ``SET ROLE``
(invariante de dueños del proyecto). Idempotente (invariante T-1.45).

Revision ID: 0029_gateway_fw_running
Revises: 0028_fw_releases
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029_gateway_fw_running"
down_revision: str | None = "0028_fw_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE gateways ADD COLUMN IF NOT EXISTS fw_running text;

COMMENT ON COLUMN gateways.fw_running IS
  'T-2.70: SHA que el proceso del gabinete cargó AL ARRANCAR (congelado). '
  'Difiere de fw_version cuando hay código escrito en disco que nadie ejecuta: '
  'despliegue a medias. NULL = el gabinete no lo declara o no lo sabe.';
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Borrar la columna volvería a fundir «lo que hay» con «lo que corre» y
    # dejaría sin criterio de éxito a cualquier actualización en vuelo. Mismo
    # criterio que 0021/0022/0023/0025/0028.
    pass
