"""T-2.04 · Endpoint ARN de SNS por token de push.

El worker de notify mapea cada token FCM/APNs a un platform endpoint de SNS y
CACHEA el ARN aquí (crearlo en cada envío sería una llamada extra por
dispositivo en plena crisis). También necesita UPDATE: sellar el ARN creado y
revocar (``revoked_at``) los endpoints que SNS reporta deshabilitados (token
rotado/app desinstalada) — limpieza honesta, sin reintentos eternos.

Idempotente (invariante T-1.45); ``push_tokens`` es de ``takab_migrator`` en
ambas cadenas (la crea 0018/0001 bajo SET ROLE). ``notification_jobs`` es
PREEXISTENTE con dueño histórico variable ⇒ su ALTER corre como usuario de
conexión (superusuario en local, ``takab_migrator`` en la nube) — misma regla
que 0018.

Revision ID: 0019_push_endpoints
Revises: 0018_mobile_core
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_push_endpoints"
down_revision: str | None = "0018_mobile_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS endpoint_arn text;
GRANT SELECT, UPDATE ON push_tokens TO takab_ingest;

RESET ROLE;
"""

# El canal 'push' entra a la cascada (job paralelo CRISIS, spec móvil §6).
_UP_PREEXISTING_AS_CONNECTION_USER = """
ALTER TABLE notification_jobs DROP CONSTRAINT IF EXISTS notification_jobs_channel_check;
ALTER TABLE notification_jobs ADD CONSTRAINT notification_jobs_channel_check
  CHECK (channel IN ('webhook','whatsapp','sms','email','push'));
"""

_DOWN_PREEXISTING_AS_CONNECTION_USER = """
ALTER TABLE notification_jobs DROP CONSTRAINT IF EXISTS notification_jobs_channel_check;
ALTER TABLE notification_jobs ADD CONSTRAINT notification_jobs_channel_check
  CHECK (channel IN ('webhook','whatsapp','sms','email'));
"""

_DOWN = """
SET ROLE takab_migrator;

REVOKE UPDATE ON push_tokens FROM takab_ingest;
ALTER TABLE push_tokens DROP COLUMN IF EXISTS endpoint_arn;

RESET ROLE;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003-0018."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)
    _exec(_UP_PREEXISTING_AS_CONNECTION_USER)


def downgrade() -> None:
    _exec(_DOWN_PREEXISTING_AS_CONNECTION_USER)
    _exec(_DOWN)
