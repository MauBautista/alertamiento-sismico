"""T-5.18 · cuota de gasto de IA por tenant y mes

Había contabilidad POR LLAMADA —el coste sale de la respuesta del proveedor y se
escribe en `audit_log`— y techo de tokens por llamada. **No había cuota, ni
contador acumulado, ni corte.** Es lo que OWASP llama consumo de recursos sin
restricción, y hoy el riesgo está acotado solo por que la perilla está apagada:
por eso el tope tiene que aterrizar ANTES del shadow-mode, no después.

**Una fila por (tenant, periodo)**, y el periodo es el mes en UTC como texto
`YYYY-MM`. Texto y no `date`: la clave es un MES, y guardarlo como el día 1 de
ese mes invita a que alguien compare rangos y cuente dos veces el borde.

`warned_at` y `blocked_at` **no son cosméticos: son lo que hace que el aviso y el
corte se auditen UNA vez y no una por petición** (regla de oro 10 — registro por
transición). Escribirlos es lo que decide si toca dejar fila, y el `UPDATE …
WHERE blocked_at IS NULL` lo resuelve sin carrera entre dos exportaciones
simultáneas.

Revision ID: 0058_cuota_de_ia
Revises: 0057_tipologia_y_rollback
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0058_cuota_de_ia"
down_revision: str | None = "0057_tipologia_y_rollback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = """
CREATE TABLE IF NOT EXISTS ai_spend (
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  -- Mes UTC 'YYYY-MM'. El CHECK impide que una zona horaria del cliente meta
  -- aquí un formato distinto y parta el acumulado en dos periodos.
  period      text NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  spent_usd   numeric(12,6) NOT NULL DEFAULT 0,
  calls       integer NOT NULL DEFAULT 0,
  --  Instantes de TRANSICIÓN, no banderas: existen para que el aviso y el corte
  --  dejen UNA fila de auditoría en el periodo y no una por petición.
  warned_at   timestamptz,
  blocked_at  timestamptz,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, period)
);
"""

# A diferencia de casi todo lo demás, esta tabla SÍ se actualiza en sitio: es un
# contador, no evidencia. Lo que es evidencia —cuánto costó cada llamada, cuándo
# se avisó y cuándo se cortó— vive en `audit_log`, que es append-only y no se poda.
_GRANTS = "GRANT SELECT, INSERT, UPDATE ON ai_spend TO takab_app;"

_RLS = """
ALTER TABLE ai_spend ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_spend FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_spend_rw ON ai_spend;
CREATE POLICY ai_spend_rw ON ai_spend FOR ALL
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal())
  WITH CHECK (tenant_id = app_tenant_id() OR app_is_takab_internal());
"""


def upgrade() -> None:
    conn = op.get_bind()
    # Objeto NUEVO ⇒ se crea como `takab_migrator` (ver la invariante de dueños en
    # `takab-docs` y la migración 0001): así queda sujeto a FORCE RLS de verdad.
    conn.exec_driver_sql("SET ROLE takab_migrator")
    conn.exec_driver_sql(_TABLA)
    conn.exec_driver_sql(_GRANTS)
    conn.exec_driver_sql(_RLS)
    conn.exec_driver_sql("RESET ROLE")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("SET ROLE takab_migrator")
    conn.exec_driver_sql("DROP TABLE IF EXISTS ai_spend")
    conn.exec_driver_sql("RESET ROLE")
