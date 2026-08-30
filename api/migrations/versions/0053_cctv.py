"""T-3.11.b · CCTV: cámaras, clips, capturas y analítica de evacuación.

Cinco tablas para responder tres preguntas que hoy nadie puede contestar después de un
sismo: cuánta gente salió, cuánto tardó la mayor parte en salir, y cuánto se tardó entre
el dictamen y el reingreso.

LOS CLIPS NO VAN EN `evidence_objects`, Y ES LA DECISIÓN QUE GOBIERNA ESTE ARCHIVO
──────────────────────────────────────────────────────────────────────────────────
Su `CHECK (kind IN (...))` no los admite, pero eso es lo de menos: `evidence_objects` es
una de las tablas de `COMPLIANCE_ANCHOR`, y por tanto queda **exenta de la poda**. El
vídeo no puede heredar esa exención —regla de oro 11 protege auditoría y dictámenes, **no
imágenes de personas** (blueprint §4.8/B.4)—. Meter un clip ahí lo volvería
imborrable por diseño, que es exactamente lo contrario de lo que la política de vídeo
exige.

EL HECHO SOBREVIVE, LA IMAGEN NO
────────────────────────────────
`cctv_clips` y `cctv_stills` copian el patrón de DOS TRIGGERS de `life_checkins`:

* `DELETE` → `forbid_update_delete()`, el guard canónico. La fila **no se borra**: es la
  constancia de que hubo un clip, con su `sha256` y su hora, y eso tiene que sobrevivir a
  la poda para que la cadena de custodia del reporte siga siendo verificable.
* `UPDATE` → `cctv_purge_guard()`, que abre UNA rendija: `s3_key → NULL` con su
  `purged_at`. Es lo que permite que el objeto de S3 muera y la fila lo declare.

**Los dos eventos van SEPARADOS a propósito, y no es cosmética.** `ops/restore_check.py`
deriva qué tablas son append-only buscando `BEFORE UPDATE OR DELETE` —tanto en el DDL como
en el catálogo (`tgtype & 8 AND tgtype & 16`)—, y ambas derivaciones toman
`sorted(guards)[0]` para elegir *la* función guarda del esquema. Si alguien juntara los dos
eventos en un solo trigger, `cctv_purge_guard` ordenaría **antes** que
`forbid_update_delete` y pasaría a ser la guarda canónica de todo el esquema, cambiando en
silencio qué verifica el comprobador de restore. Separados, cada verificador ve la verdad
exacta y el nombre da igual.

Y la rendija exige la **transición real** (`OLD.s3_key IS NOT NULL AND NEW.s3_key IS NULL`),
no solo que el resto de la fila no cambie: `restore_check` ejerce un `UPDATE ... SET c = c`
y espera que el guard lo **rechace**. Sin esa condición, el no-op pasaría y el verificador
leería «ACEPTADO (la guarda no existe o está desactivada)» sobre una guarda que sí existe.

LA CREDENCIAL DE LA CÁMARA NO ESTÁ AQUÍ
───────────────────────────────────────
`cameras` guarda host, puerto y una `rtsp_url` **sin secreto**. El usuario y la clave viven
en el entorno del proceso que graba. La razón es que una URL RTSP completa es del tipo
`rtsp://usuario:clave@host/stream`, y **ningún detector de PII del proyecto la reconoce**:
sería una fuga que ningún censo puede ver.

`count_mode` ES LA REVOCACIÓN DE `D-14`, ESCRITA COMO COLUMNA
─────────────────────────────────────────────────────────────
`D-14` exigió que la caída a «solo aforo» fuera posible **por configuración de sitio, no
por reescritura**. Ésta es esa columna: `cloud` (defecto hoy), `local` (cuenta el borde y
no sube imagen) y `off`. Si la revisión legal concluye que el clip exige un consentimiento
que un edificio con público no puede recabar, se cambia un valor por sitio.

Revision ID: 0053_cctv
Revises: 0052_actuation_records
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0053_cctv"
down_revision: str | None = "0052_actuation_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Idempotente (invariante de T-1.45). `SET ROLE takab_migrator` porque TODO lo que se crea
# aquí —cinco tablas y una función— son objetos NUEVOS: sin él quedarían a nombre del
# usuario de conexión, que en local es superusuario y en la nube no.
_UP = """
SET ROLE takab_migrator;

-- La rendija de poda del vídeo. Genérica a propósito: sirve a cualquier tabla con
-- `s3_key` + `purged_at`, y plpgsql resuelve los campos del registro en tiempo de
-- ejecución. El mensaje CONSERVA el literal 'tabla append-only' porque el verificador de
-- restore reconoce la guarda por ese texto y por su SQLSTATE (P0001).
CREATE OR REPLACE FUNCTION cctv_purge_guard() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  -- Red de seguridad: si alguien colgara esta función del evento DELETE en vez de
  -- `forbid_update_delete()`, el borrado seguiria sin pasar.
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'tabla append-only: % no permite %', TG_TABLE_NAME, TG_OP;
  END IF;
  -- La UNICA mutacion admitida: `s3_key` pasa de TENER VALOR a NULL, con el resto de la
  -- fila identica salvo `purged_at`. Exigir la transicion real (y no solo que NEW.s3_key
  -- sea NULL) deja fuera el `UPDATE ... SET c = c`, que es justo lo que ejerce el
  -- verificador de restore para comprobar que la guarda esta viva.
  IF NOT (OLD.s3_key IS NOT NULL AND NEW.s3_key IS NULL)
     OR (to_jsonb(NEW) - 's3_key' - 'purged_at')
        IS DISTINCT FROM (to_jsonb(OLD) - 's3_key' - 'purged_at') THEN
    RAISE EXCEPTION
      'tabla append-only: % no permite % (unica excepcion: anular s3_key, '
      'poda de retencion de video)', TG_TABLE_NAME, TG_OP;
  END IF;
  RETURN NEW;
END $$;

CREATE TABLE IF NOT EXISTS cameras (
  camera_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(tenant_id),
  site_id           uuid NOT NULL REFERENCES sites(site_id),
  -- El punto de reunion al que apunta. `site_assets` YA tiene kind='assembly_point'.
  assembly_asset_id uuid REFERENCES site_assets(asset_id),
  name              text NOT NULL,
  host              text NOT NULL DEFAULT '',
  onvif_port        integer NOT NULL DEFAULT 80 CHECK (onvif_port BETWEEN 1 AND 65535),
  -- SIN credencial. Ver la nota de la cabecera: una URL con usuario y clave seria una
  -- fuga que ningun detector de PII del proyecto reconoce.
  rtsp_url          text NOT NULL DEFAULT '',
  profile           text NOT NULL DEFAULT 'substream'
                    CHECK (profile IN ('substream','main')),
  enabled           boolean NOT NULL DEFAULT false,
  count_mode        text NOT NULL DEFAULT 'cloud'
                    CHECK (count_mode IN ('cloud','local','off')),
  created_at        timestamptz NOT NULL DEFAULT now(),
  created_by        uuid,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  updated_by        uuid,
  UNIQUE (site_id, name)
);
CREATE INDEX IF NOT EXISTS idx_cameras_tenant ON cameras (tenant_id);
CREATE INDEX IF NOT EXISTS idx_cameras_site   ON cameras (site_id) WHERE enabled;

CREATE TABLE IF NOT EXISTS cctv_clips (
  clip_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id    uuid NOT NULL REFERENCES incidents(incident_id),
  camera_id      uuid REFERENCES cameras(camera_id),
  -- NULLABLE, y la nulabilidad ES la funcion: al podar, el objeto muere y la fila lo
  -- declara. El sha256 y las horas sobreviven para la cadena de custodia.
  s3_key         text,
  sha256         text,
  size_bytes     bigint,
  started_at     timestamptz NOT NULL,
  ended_at       timestamptz NOT NULL,
  -- Fraccion [0..1] de la ventana pedida que el anillo pudo cubrir de verdad. Un clip que
  -- dice cubrir T-60s sin cubrirlo es una mentira en un reporte.
  coverage       numeric,
  -- NO hay columna `analysis_state`, y su ausencia es la decision. Una columna de
  -- estado MUTABLE sobre una tabla append-only es una contradiccion: el guard de poda
  -- solo admite `s3_key -> NULL`, asi que el analizador jamas podria moverla de
  -- 'pending'. El estado se DERIVA de si existen filas en `cctv_evacuation_metrics`
  -- para ese incidente — misma doctrina que `calibrated` (derivado de la procedencia)
  -- y que `is_ghost` (derivado de `derived_state`): lo que se puede derivar no se
  -- guarda, porque guardado se desincroniza y derivado no puede.
  purged_at      timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now()
);
-- Idempotencia POR CONTENIDO, con el precedente exacto de `uq_evidence_incident_sha256`
-- (0002). Un `UNIQUE (incident_id, started_at, camera_id)` NO servia: `camera_id` es
-- nullable y en Postgres los NULL son DISTINTOS en un indice unico, asi que dos entregas
-- del mismo objeto no colisionaban y el `ON CONFLICT DO NOTHING` no hacia nada. Lo caza
-- `test_una_REENTREGA_no_dice_que_el_video_salio_dos_veces`, y lo cazo de verdad.
-- Por contenido ademas es lo correcto: la key lleva el sha256 dentro, asi que el MISMO
-- objeto produce la misma fila por construccion. El indice es PARCIAL porque el sha solo
-- falta en filas que aun no tienen objeto.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cctv_clips_incident_sha256
  ON cctv_clips (incident_id, sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cctv_clips_tenant   ON cctv_clips (tenant_id);
CREATE INDEX IF NOT EXISTS idx_cctv_clips_incident ON cctv_clips (incident_id, started_at DESC);

CREATE TABLE IF NOT EXISTS cctv_stills (
  still_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id uuid NOT NULL REFERENCES incidents(incident_id),
  clip_id     uuid REFERENCES cctv_clips(clip_id),
  camera_id   uuid REFERENCES cameras(camera_id),
  -- `drip` es la captura periodica cruda; las otras cuatro son las que ELIGE la nube para
  -- el reporte, ya con la curva de aforo en la mano.
  role        text NOT NULL DEFAULT 'drip'
              CHECK (role IN ('pre','egress','peak','reentry','drip')),
  s3_key      text,
  sha256      text,
  captured_at timestamptz NOT NULL,
  purged_at   timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
-- Misma razon que en `cctv_clips`: por contenido, y parcial.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cctv_stills_incident_sha256
  ON cctv_stills (incident_id, sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cctv_stills_tenant   ON cctv_stills (tenant_id);
CREATE INDEX IF NOT EXISTS idx_cctv_stills_incident ON cctv_stills (incident_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_cctv_stills_reporte
  ON cctv_stills (incident_id, role) WHERE role <> 'drip';

-- La curva de aforo. NO es hypertable: es una serie ACOTADA por incidente (minutos u
-- horas, no continua), y una hypertable traeria chunks, retencion y RLS con columnstore
-- —el conflicto que ya documenta el esquema— a cambio de nada.
CREATE TABLE IF NOT EXISTS cctv_occupancy (
  incident_id uuid NOT NULL REFERENCES incidents(incident_id),
  camera_id   uuid NOT NULL REFERENCES cameras(camera_id),
  ts          timestamptz NOT NULL,
  -- `provenance` no es adorno: el conteo FINAL de la nube sobrescribe al preliminar del
  -- borde, y mezclarlos sin distinguirlos daria una curva con dos modelos dentro.
  provenance  text NOT NULL CHECK (provenance IN ('preliminary','final')),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  n_people    integer NOT NULL CHECK (n_people >= 0),
  PRIMARY KEY (incident_id, camera_id, ts, provenance)
);
CREATE INDEX IF NOT EXISTS idx_cctv_occupancy_tenant ON cctv_occupancy (tenant_id);

CREATE TABLE IF NOT EXISTS cctv_evacuation_metrics (
  incident_id       uuid NOT NULL REFERENCES incidents(incident_id),
  provenance        text NOT NULL CHECK (provenance IN ('preliminary','final')),
  tenant_id         uuid NOT NULL REFERENCES tenants(tenant_id),
  -- Segundos DESDE la señal. `t90_s` es «cuanto tardo en salir la mayor parte».
  t50_s             numeric,
  t90_s             numeric,
  peak_n            integer,
  peak_at           timestamptz,
  reentry_start_at  timestamptz,
  dictamen_lag_s    numeric,
  -- NEGATIVO significa que la gente reentro ANTES del dictamen firmado. Eso no es un
  -- numero: es un hallazgo de seguridad, y el reporte lo dice con palabras.
  reentry_lag_s     numeric,
  -- El otro lado del cruce de T-3.12: se muestra como DISCREPANCIA frente a `peak_n`,
  -- jamas promediado en un numero unico.
  checkin_count     integer,
  computed_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (incident_id, provenance)
);
CREATE INDEX IF NOT EXISTS idx_cctv_metrics_tenant ON cctv_evacuation_metrics (tenant_id);

RESET ROLE;

-- Los dos triggers, con los eventos SEPARADOS (ver la nota de la cabecera).
DROP TRIGGER IF EXISTS trg_cctv_clips_append_only ON cctv_clips;
CREATE TRIGGER trg_cctv_clips_append_only
  BEFORE DELETE ON cctv_clips FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
DROP TRIGGER IF EXISTS trg_cctv_clips_purge_guard ON cctv_clips;
CREATE TRIGGER trg_cctv_clips_purge_guard
  BEFORE UPDATE ON cctv_clips FOR EACH ROW EXECUTE FUNCTION cctv_purge_guard();

DROP TRIGGER IF EXISTS trg_cctv_stills_append_only ON cctv_stills;
CREATE TRIGGER trg_cctv_stills_append_only
  BEFORE DELETE ON cctv_stills FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
DROP TRIGGER IF EXISTS trg_cctv_stills_purge_guard ON cctv_stills;
CREATE TRIGGER trg_cctv_stills_purge_guard
  BEFORE UPDATE ON cctv_stills FOR EACH ROW EXECUTE FUNCTION cctv_purge_guard();

GRANT SELECT, INSERT, UPDATE ON cameras                 TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_clips              TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_stills             TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_occupancy          TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_evacuation_metrics TO takab_app;

-- La otra capa del append-only: sin el privilegio, el guard no es la unica defensa.
-- `test_append_only_dos_capas.py` DERIVA estas dos tablas por su trigger de DELETE y
-- exige exactamente esto.
REVOKE DELETE ON cctv_clips  FROM takab_app;
REVOKE DELETE ON cctv_stills FROM takab_app;

-- El worker de backfill corre como `takab_ingest` (BYPASSRLS), NO como `takab_app`: es
-- quien registra el objeto cuando S3 avisa. Sin estas lineas el clip sube, la
-- notificacion llega y el INSERT muere con «permission denied» — verde en local y rojo
-- en la nube, que es el modo de fallo que este proyecto ya conoce. Y sin DELETE tampoco
-- para el, que el append-only no depende del rol que lo intente.
GRANT SELECT, INSERT ON cctv_clips              TO takab_ingest;
GRANT SELECT, INSERT ON cctv_stills             TO takab_ingest;
GRANT SELECT, INSERT ON cctv_occupancy          TO takab_ingest;
GRANT SELECT, INSERT, UPDATE ON cctv_evacuation_metrics TO takab_ingest;
GRANT SELECT ON cameras TO takab_ingest;

ALTER TABLE cameras                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE cameras                 FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_clips              ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_clips              FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_stills             ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_stills             FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_occupancy          ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_occupancy          FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_evacuation_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_evacuation_metrics FORCE  ROW LEVEL SECURITY;
"""

# Las politicas van aparte para poder generarlas en bucle sin repetir cinco veces lo
# mismo: enumerarlas a mano es como divergen los esquemas.
_TABLAS = (
    "cameras",
    "cctv_clips",
    "cctv_stills",
    "cctv_occupancy",
    "cctv_evacuation_metrics",
)

# SIN rama `app_gov_can_see`, y la ausencia ES la decision: blueprint §4.8/B.4 dice que
# ver video es mas estrecho que ver telemetria — «ver video no es ver telemetria». El
# precedente exacto de omitirla es `privacy_notices`: el aviso de un cliente no es
# evidencia de proteccion civil, y las imagenes de las personas de su edificio, menos.
_POLITICAS = "\n".join(
    f"""
DROP POLICY IF EXISTS {t}_read ON {t};
CREATE POLICY {t}_read ON {t} FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
DROP POLICY IF EXISTS {t}_write ON {t};
CREATE POLICY {t}_write ON {t} FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
DROP POLICY IF EXISTS {t}_admin ON {t};
CREATE POLICY {t}_admin ON {t} FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
"""
    for t in _TABLAS
)

_DOWN = """
DROP TABLE IF EXISTS cctv_evacuation_metrics;
DROP TABLE IF EXISTS cctv_occupancy;
DROP TABLE IF EXISTS cctv_stills;
DROP TABLE IF EXISTS cctv_clips;
DROP TABLE IF EXISTS cameras;
DROP FUNCTION IF EXISTS cctv_purge_guard();
"""


def upgrade() -> None:
    op.execute(_UP + _POLITICAS)


def downgrade() -> None:
    op.execute(_DOWN)
