"""T-2.81.a · La constancia de cada corrida de retención de PII.

El job de retención existía —`python -m takab_api.ops.prune_pii`, igual que
`ops.restore_drill`— y **no lo llamaba nadie**: no había módulo de cron, Lambda
ni EventBridge en `infra/terraform/modules/`. Una retención que nadie ejecuta es
una política escrita, no una cumplida, y la diferencia importa el día que un
cliente pregunta cuánto tiempo guardamos su teléfono.

Ahora lo llama un cron (`modules/database`, documento SSM
`takab-<env>-retencion-pii`, diario). Esta tabla es lo que hace **comprobable**
que corrió, y lo que hace que un fallo **se vea**.

──────────────────────────────────────────────────────────────────────────────
1 · LA FILA SE ESCRIBE FUERA DE LA TRANSACCIÓN DEL JOB
──────────────────────────────────────────────────────────────────────────────
Es el punto entero de esta revisión. La corrida es UNA transacción que se
revierte **entera** si el `ROW_COUNT` no cuadra con el conteo que la autorizó
(`ops/prune_pii`, criterio 3 de T-2.81). Escribir la constancia dentro de esa
transacción habría hecho desaparecer, con el rollback, justamente la constancia
de la corrida que falló — la única que alguien necesita leer.

Por eso `ok` puede valer `false`, y por eso el `CHECK` exige que un fallo lleve
su razón y que un éxito no arrastre una: "un fallo del job se ve" deja de ser una
promesa del código y pasa a ser una condición de la base.

──────────────────────────────────────────────────────────────────────────────
2 · SIN TENANT, y el detalle por cliente DENTRO del informe
──────────────────────────────────────────────────────────────────────────────
Una corrida recorre a todos los clientes: es un hecho de la PLATAFORMA, igual
que `ops_alert_notices` (T-2.78.a). Ponerle `tenant_id` obligaría a inventarle un
dueño y, peor, dejaría que un cliente viera las cifras de otro. Los conteos por
tenant viajan en `report`, que es el mismo JSON que ya imprime el simulacro.

──────────────────────────────────────────────────────────────────────────────
3 · DE AQUÍ SALE LA ALARMA, y por eso el índice parcial
──────────────────────────────────────────────────────────────────────────────
El publicador de la instancia pregunta `max(finished_at) WHERE ok` y publica su
EDAD como `PiiRetentionAgeSeconds`. Así la métrica mide lo que de verdad importa
—cuándo terminó bien la última corrida— y no "el script salió con 0": una
corrida que aborta deja fila con `ok = false`, la edad sigue creciendo y la
alarma suena sola. El silencio también: la alarma va en `breaching`, porque si
nadie publica es que el cron no corre, que es exactamente el estado que esta
ficha existe para eliminar.

Revision ID: 0043_pii_retention_runs
Revises: 0042_user_deactivation_clock
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0043_pii_retention_runs"
down_revision: str | None = "0042_user_deactivation_clock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- 1: la tabla (objeto NUEVO ⇒ SET ROLE takab_migrator) ----------------------
_TABLA = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS pii_retention_runs (
  run_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at    timestamptz NOT NULL,
  finished_at   timestamptz NOT NULL DEFAULT now(),
  mode          text NOT NULL CHECK (mode IN ('simulacro','aplicado')),
  ok            boolean NOT NULL,
  total_due     bigint NOT NULL DEFAULT 0,
  total_applied bigint NOT NULL DEFAULT 0,
  report        jsonb  NOT NULL DEFAULT '{}'::jsonb,
  error         text,
  CONSTRAINT prr_el_fallo_lleva_su_razon CHECK (ok = (error IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_pii_retention_runs_ok
  ON pii_retention_runs (finished_at DESC) WHERE ok;

RESET ROLE;
"""

# --- 2: permisos y RLS ---------------------------------------------------------
# El `REVOKE` cierra la MISMA divergencia que midió T-2.78.a: la 0001 termina con
# `GRANT ... ON ALL TABLES IN SCHEMA public TO takab_app` y ese grant masivo corre
# DESPUES del cuerpo de `db/schema.sql`. En una base NUEVA `takab_app` saldria con
# UPDATE y DELETE sobre el registro de corridas; en una base EXISTENTE no. Dos
# despliegues con permisos distintos sobre la prueba de que la retencion se
# ejecuto — y el local, que es el que se prueba, seria el bueno.
_PERMISOS = """
GRANT SELECT, INSERT ON pii_retention_runs TO takab_app;
REVOKE UPDATE, DELETE ON pii_retention_runs FROM takab_app;
REVOKE ALL ON pii_retention_runs FROM takab_ingest;

ALTER TABLE pii_retention_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_retention_runs FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pii_retention_runs_internal ON pii_retention_runs;
CREATE POLICY pii_retention_runs_internal ON pii_retention_runs FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
"""

_DOWN = """
DROP TABLE IF EXISTS pii_retention_runs;
"""


def upgrade() -> None:
    op.execute(_TABLA)
    op.execute(_PERMISOS)


def downgrade() -> None:
    op.execute(_DOWN)
