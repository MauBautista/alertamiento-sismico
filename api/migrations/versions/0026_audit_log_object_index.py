"""T-2.60.a · Índice por objeto en la bitácora: "¿qué le pasó a ESTE gabinete?".

`audit_log` solo tenía índices por tiempo — `(ts DESC, audit_id DESC)` para la
lectura keyset de `GET /audit` y `(tenant_id, ts DESC)` para acotar por cliente.
Preguntar por un objeto concreto ("quién retiró el gabinete X y cuándo") exigía
un escaneo secuencial completo.

Eso no es un detalle de rendimiento cualquiera: por la regla de oro 11 la
bitácora **no se poda nunca**, así que es la única tabla del esquema que crece de
forma no acotada por diseño. Un escaneo secuencial ahí empieza barato y se hace
caro sin que nadie lo note, justo en el camino del inventario de flota, que es la
pantalla que más se refresca de la consola.

Lo pide T-2.60.a: el listado de flota delata al gabinete retirado que sigue
latiendo y dice CUÁNDO y QUIÉN lo retiró; ese dato solo vive aquí.

`object` es texto libre con forma `'<tipo>:<uuid>'`, así que el índice ordena
además por `ts DESC` para que el `LIMIT 1` del LATERAL salga del índice sin
ordenar nada.

Tabla PREEXISTENTE ⇒ **sin `SET ROLE`**: el DDL corre como el usuario de la
conexión (invariante de dueños del proyecto — el `SET ROLE takab_migrator` se
reserva a objetos NUEVOS, y usarlo aquí rompería el apply en la nube, donde
migra `takab_migrator` y no un superusuario).
Idempotente (invariante T-1.45).

Revision ID: 0026_audit_log_object_index
Revises: 0025_tenant_retire_codes
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_audit_log_object_index"
down_revision: str | None = "0025_tenant_retire_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# CONCURRENTLY queda descartado a propósito: alembic corre dentro de una
# transacción y CREATE INDEX CONCURRENTLY no puede. La tabla se bloquea lo que
# dure la construcción; en el tamaño actual son milisegundos, y hacerlo ahora es
# precisamente lo barato — dentro de un año no lo será.
_UP = """
CREATE INDEX IF NOT EXISTS idx_audit_log_object_ts
    ON audit_log (object, ts DESC);
"""

_DOWN = """
DROP INDEX IF EXISTS idx_audit_log_object_ts;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
