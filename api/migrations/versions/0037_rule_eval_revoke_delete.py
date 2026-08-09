"""T-2.81.c · `rule_evaluations` recupera la segunda cerradura que sus hermanas ya tenían.

De las tablas que llevan un guard `BEFORE DELETE` append-only, `rule_evaluations`
era la ÚNICA sobre la que `takab_app` seguía teniendo el privilegio `DELETE`. La
T-2.80 hizo el `REVOKE` sobre doce tablas —auditoría, evidencia, dictámenes,
consentimientos, PII— y esta se quedó fuera, aunque lleva su trigger
`trg_rule_evaluations_append_only` desde el 0001.

QUÉ ERA EXPLOTABLE Y QUÉ NO
───────────────────────────
No lo era. Y la razón medida no es la que la ficha suponía: el `DELETE` de
`takab_app` sobre esta tabla no llegaba al trigger. La RLS de `rule_evaluations`
tiene **solo política de lectura** (`re_read`), así que un `DELETE` no encontraba
ninguna fila borrable y volvía con cero filas **sin error ni excepción**. Lo que
paraba el borrado era la ausencia de una política, no el guard.

Eso es peor de lo que parecía, no mejor: la protección efectiva descansaba en el
detalle más frágil de los tres —que a nadie se le ocurriera escribir una política
`FOR DELETE` o `FOR ALL` sobre esta tabla al añadir una superficie nueva—. Con el
`REVOKE`, escribir esa política deja de bastar: PostgreSQL niega antes de mirar
la fila, y si alguien conectara como el DUEÑO (los jobs de TimescaleDB corren
así) el trigger sigue detrás. Dos capas, como en las otras once.

POR QUÉ EN UNA MIGRACIÓN Y NO SOLO EN `db/schema.sql`
─────────────────────────────────────────────────────
Es la trampa que ya mordió en la 0028, se repitió en la 0030, en la 0033 y en la
0034: el `0001_initial_schema` ejecuta

    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO takab_app;

**después** de aplicar `db/schema.sql`. Un `REVOKE` que viviera solo en el schema
quedaría deshecho en cualquier base NUEVA y el defecto volvería intacto sin que
nada lo dijera. El espejo en `db/schema.sql` va igualmente —el archivo es la
fuente de verdad del DDL— y va al final, en el bloque de la T-2.80, que es donde
los `GRANT` de arriba ya han pasado.

INVARIANTES
───────────
Tabla PREEXISTENTE y sentencia de privilegios ⇒ **sin `SET ROLE`**: corre como el
usuario de la conexión (que en la nube es `takab_migrator`, dueño de la tabla y
por tanto capaz de revocar; en local es el superusuario). `REVOKE` es idempotente
por naturaleza: revocar lo ya revocado es un no-op, no un error.

Revision ID: 0037_rule_eval_revoke_delete
Revises: 0036_device_health_relays_state
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0037_rule_eval_revoke_delete"
down_revision: str | None = "0036_device_health_relays_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UP = """
-- [T-2.81.c] La segunda capa. La primera —el trigger append-only— está puesta
-- desde el 0001; esta faltaba. Ver la cabecera: el `GRANT ... ON ALL TABLES` del
-- 0001 corre DESPUÉS de db/schema.sql, así que el REVOKE tiene que vivir aquí.
REVOKE DELETE ON rule_evaluations FROM takab_app;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Devolver el privilegio dejaría la tabla otra vez apoyada en una sola capa,
    # que es el defecto que esta migración cierra. Mismo criterio que las
    # 0021/0022/0023/0025/0028/0029/0036.
    pass
