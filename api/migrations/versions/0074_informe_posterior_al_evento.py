"""T-9.42 · D-48 · el informe posterior al evento lo genera el sistema, solo

Un PDF por incidente, al estilo ShakeReport, que llega en ≤ 30 min desde la
apertura sin que nadie pulse «generar». Lo escribe el worker ``informes``
(``takab_ingest``) y lo lee la consola: el patrón de ``incident_shakemap`` (0069).

## Las columnas

* ``incident_id`` UNIQUE — la clave natural. El worker inserta con
  ``ON CONFLICT (incident_id) DO NOTHING``: dos pasadas no pueden dejar dos
  informes del mismo sismo (regla de oro 3).
* ``trigger`` ∈ {firma, cierre, plazo} — lo que llegó PRIMERO y lo disparó. Queda
  escrito porque es lo que explica por qué un informe salió PRELIMINAR.
* ``state`` ∈ {pendiente, ok, fallido}. ``pendiente`` SÍ es un estado aquí (a
  diferencia del mapa): es la fila reclamada que el worker está generando, y la
  que se reintenta si murió a medias.
* ``evidence_id`` → ``evidence_objects``: el PDF inmutable con su sha256. El CHECK
  ``per_ok_con_evidencia`` hace que **nunca haya un `ok` sin evidencia**, también
  si mañana otro escritor se equivoca.
* ``preliminar`` — la CABEZA de la cadena de dictámenes NO estaba firmada al
  generarlo. NULL mientras no hay PDF.
* ``dictamen_vigente`` — la cabeza con que se renderizó el papel, como la estampa
  ``export_pdf`` en su ``meta``.
* ``attempts`` / ``error`` — el reintento acotado (3) y la causa, recortada.

## Escritura: el worker y nadie más

``takab_app`` recibe **sólo SELECT** y el ``REVOKE`` (lección de la 0069: la
``0001`` aplica ``db/schema.sql`` y DESPUÉS concede ``ALL TABLES`` a
``takab_app``). Sin política de escritura: escribe ``takab_ingest`` (BYPASSRLS).

## ``ai_spend`` y ``user_profiles`` para el worker

El informe se redacta con la MISMA ``build_narrative`` que la consola, que apunta
el gasto de IA en ``ai_spend``. La 0058 se lo concedió sólo a ``takab_app`` y en
la nube la ``0001`` no la cubre (la tabla es posterior): sin este GRANT el worker
moriría con «permission denied» al primer informe con la IA encendida, y en local
saldría verde. El tope de gasto sigue siendo el del cliente: el worker lo gasta
por la misma puerta. Y el builder une ``user_profiles`` para imprimir quién firmó,
que la 0011 sólo concedió a ``takab_app`` (SELECT, y nada más).

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+.

Revision ID: 0074_informe_posterior_al_evento
Revises: 0073_firma_y_banda_del_dictamen
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0074_informe_posterior_al_evento"
down_revision: str | None = "0073_firma_y_banda_del_dictamen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
-- Objeto NUEVO ⇒ `SET ROLE takab_migrator` (invariante de dueños).
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS post_event_reports (
  report_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id      uuid NOT NULL UNIQUE REFERENCES incidents(incident_id),
  trigger          text NOT NULL CHECK (trigger IN ('firma','cierre','plazo')),
  state            text NOT NULL DEFAULT 'pendiente'
                   CHECK (state IN ('pendiente','ok','fallido')),
  variant          text NOT NULL,
  evidence_id      uuid NULL REFERENCES evidence_objects(evidence_id),
  preliminar       boolean NULL,
  dictamen_vigente uuid NULL,
  attempts         integer NOT NULL DEFAULT 0,
  error            text NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT per_ok_con_evidencia CHECK (state <> 'ok' OR evidence_id IS NOT NULL)
);

RESET ROLE;

COMMENT ON TABLE post_event_reports IS
  '[T-9.42 · D-48] El informe posterior al evento que el sistema genera solo: uno '
  'por incidente. Lo escribe el worker informes (takab_ingest) y lo lee la consola.';
COMMENT ON COLUMN post_event_reports.trigger IS
  'Lo que llego PRIMERO: firma (la cabeza de la cadena firmada), cierre (state = '
  'closed) o plazo (informe_plazo_s desde la apertura; sale PRELIMINAR sin firma).';
COMMENT ON COLUMN post_event_reports.preliminar IS
  'true = la cabeza de la cadena de dictamenes NO estaba firmada al generarlo. '
  'NULL mientras no hay PDF.';

ALTER TABLE post_event_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_event_reports FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS per_read ON post_event_reports;
CREATE POLICY per_read ON post_event_reports FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());

GRANT SELECT ON post_event_reports TO takab_app;
GRANT SELECT, INSERT, UPDATE ON post_event_reports TO takab_ingest;
-- ⚠️ No redundante (0069): en una base NUEVA la `0001` concede ALL TABLES a
-- `takab_app` DESPUES de crear esta tabla desde `db/schema.sql`.
REVOKE INSERT, UPDATE, DELETE ON post_event_reports FROM takab_app;

-- El worker redacta con `build_narrative`, que apunta el gasto en `ai_spend`.
GRANT SELECT, INSERT, UPDATE ON ai_spend TO takab_ingest;
-- Y el builder une `user_profiles` para el nombre de quien firmo. La 0011 solo se
-- la dio a `takab_app`: mismo criterio que la 0073 con `damage_reports`.
GRANT SELECT ON user_profiles TO takab_ingest;
-- La portada lee `compliance_labels` (la 0018 solo se la dio a `takab_app`) y el
-- CCTV de `cctv.build_cctv`. Medido el 2026-09-28 corriendo el worker contra una base
-- migrada paso a paso: «permission denied for table compliance_labels», y el informe
-- quedo `fallido`. En CI no se ve: la 0001 concede ALL TABLES a `takab_ingest` en base
-- nueva. Los del CCTV ya los da la 0053, pero una base que la aplico antes de que los
-- llevara no los tiene; repetir un GRANT no hace nada.
GRANT SELECT ON compliance_labels TO takab_ingest;
GRANT SELECT ON cameras, cctv_clips, cctv_stills, cctv_evacuation_metrics TO takab_ingest;
"""

_DOWN = """
DROP TABLE IF EXISTS post_event_reports;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
