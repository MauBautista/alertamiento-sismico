"""T-AUDIT · aislamiento por tenant de los caggs site_metrics_1m/1h.

Cierra un hallazgo CRÍTICO de la auditoría pre-frontend: los continuous
aggregates ``site_metrics_1m|1h`` no pueden llevar RLS (limitación de
TimescaleDB con columnstore) y a ``takab_app`` NUNCA se le revocó el SELECT que
sí se revocó del crudo ``waveform_features_1s``. Sin este REVOKE, una sesión de
tenant podía ``SELECT * FROM site_metrics_1m`` y leer PGA/PGV de TODOS los
tenants — el "siempre JOIN sites" era solo convención de la API, no impuesto por
la DB.

Fix, espejo del patrón del waveform: vistas ``*_secure`` (security_barrier +
JOIN a ``sites`` con RLS+FORCE) creadas bajo ``takab_migrator`` (dueño
NO-superusuario → el FORCE RLS de ``sites`` SÍ lo sujeta), SELECT concedido solo
sobre las vistas y REVOCADO sobre los caggs base. La API lee por ``*_secure``.

Revision ID: 0008_cagg_secure_views
Revises: 0007_billing_meters
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_cagg_secure_views"
down_revision: str | None = "0007_billing_meters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Todo bajo takab_migrator: las vistas quedan de su propiedad (NO-superusuario),
# así el FORCE RLS de `sites` filtra por app.tenant_id de sesión al leerlas. Si
# las creara el superusuario de la migración, el owner saltaría RLS y la vista
# "segura" devolvería todos los tenants.
#
# Idempotente (DROP IF EXISTS + CREATE): en una cadena FRESCA la 0001 ya creó
# estas vistas al aplicar db/schema.sql verbatim (la fuente de verdad las
# incluye desde este fix); en DBs vivas pre-0008 no existen. Ambas rutas
# convergen aquí a owner=takab_migrator + grants correctos.
_UP = """
SET ROLE takab_migrator;

DROP VIEW IF EXISTS site_metrics_1m_secure;
DROP VIEW IF EXISTS site_metrics_1h_secure;

CREATE VIEW site_metrics_1m_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1m m JOIN sites s ON s.site_id = m.site_id;
CREATE VIEW site_metrics_1h_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1h m JOIN sites s ON s.site_id = m.site_id;

REVOKE ALL ON site_metrics_1m, site_metrics_1h FROM takab_app;
GRANT SELECT ON site_metrics_1m_secure, site_metrics_1h_secure TO takab_app;

RESET ROLE;
"""

_DOWN = """
SET ROLE takab_migrator;
DROP VIEW IF EXISTS site_metrics_1m_secure;
DROP VIEW IF EXISTS site_metrics_1h_secure;
GRANT SELECT ON site_metrics_1m, site_metrics_1h TO takab_app;
RESET ROLE;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003-0007."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
