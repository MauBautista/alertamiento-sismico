"""T-2.77.b + T-2.77.c · Dónde se escribe el desenlace TARDÍO, y dónde vive la memoria.

UNA migración para las dos fichas porque tocan la misma tabla y el mismo
subsistema; dos revisiones encadenadas habrían sido dos ventanas de despliegue
para un solo cambio coherente.

──────────────────────────────────────────────────────────────────────────────
1 · T-2.77.b — `notification_jobs` no tenía DÓNDE poner "llegó"
──────────────────────────────────────────────────────────────────────────────
Hoy `sent_at` significa «el proveedor lo aceptó»: SES aceptó el correo, Twilio
encoló el SMS, Meta aceptó el mensaje. Ninguno de los tres afirma que un humano
lo tenga en la mano. Lo que faltaba no era el endpoint —eso es código—: era el
sitio donde escribir «salió a las 12:00:03 y llegó a las 12:00:19».

* `provider_message_id` — el identificador que el proveedor le dio al mensaje
  (`MessageSid` de Twilio, el id de mensaje de Meta). **Sin persistirlo no hay
  con qué casar nada**: el recibo vivía en memoria del worker y moría con él.
* `delivered_at`  — el instante de la entrega CONFIRMADA. Distinto de `sent_at`
  a propósito: son dos hechos y la consola tiene que poder mostrar los dos.
* `last_status` / `last_status_at` — la última palabra del proveedor y cuándo
  se recibió, que es lo que permite ordenar callbacks que llegan desordenados.

El índice es **UNIQUE** sobre `(channel, provider_message_id)`: un identificador
de proveedor pertenece a UN job y a ninguno más. Cuesta que un proveedor que
repitiera identificador rompiera el pase con un 23505 en vez de seguir en
silencio — y ese es el trato que se quiere: atribuir una entrega al job
equivocado es peor que un fallo ruidoso.

──────────────────────────────────────────────────────────────────────────────
2 · T-2.77.c — la memoria de UN worker no es memoria
──────────────────────────────────────────────────────────────────────────────
La cuarentena de plantillas y la guarda de duplicados eran estado EN PROCESO.
Dos consecuencias medidas, ninguna teórica: al reiniciar el worker se olvidaba
la cuarentena y se volvía a martillear algo que Meta ya había pausado (que es
justo lo que degrada su calificación de calidad y termina costando el canal
entero); y con más de una instancia la guarda de duplicados no existía entre
instancias — mientras el orquestador de al lado YA asume varias (usa
`pg_advisory_xact_lock`).

* `inflight_until` (en `notification_jobs`) — la guarda de duplicados. **No es
  una tabla nueva a propósito**: la clave del dominio era `(destino, incidente)`
  y para los dos canales guardados —sms y whatsapp— eso es EXACTAMENTE una fila
  de `notification_jobs` (`plan_jobs` emite un solo job por canal e incidente;
  el único canal que recibe dos, `email`, no tiene guarda). Ponerla en el job
  hereda gratis el `tenant_id`, la RLS y la retención de la tabla, y no añade
  una fila que borrar el día de un ARCO.
* `notify_template_quarantine` — la cuarentena. Ésta sí necesita tabla: no
  pertenece a ningún cliente. La plantilla es de la cuenta de negocio del
  DESPLIEGUE (una WABA para toda la flota), así que una `tenant_id` aquí tendría
  que inventarse un dueño. Va declarada como exención en
  `tests/test_censo_multitenancy.py`, con su razón, que es como este repo admite
  una tabla sin `tenant_id`.

**Levantar una cuarentena es un acto humano deliberado**, y por eso ningún rol
de aplicación tiene `DELETE`: hasta hoy la levantaba un reinicio —el defecto
exacto de esta ficha—. Se levanta con un `DELETE` del dueño del esquema cuando
alguien ha vuelto a someter la plantilla y Meta la ha vuelto a aprobar.

──────────────────────────────────────────────────────────────────────────────
3 · `app_notify_delivery` — por qué SECURITY DEFINER y no un UPDATE normal
──────────────────────────────────────────────────────────────────────────────
El webhook es PÚBLICO: no lleva sesión, luego no hay `app.tenant_id` ni
`app.role`. La API conecta como `takab_app`, que sobre `notification_jobs` tiene
`SELECT` y nada más, y cuya RLS es default-deny (`FORCE`) — así que ni con un
`GRANT UPDATE` podría escribir: sin contexto de tenant ninguna política le abre.
Y `takab_app` **no puede** volverse `takab_ingest` (no es miembro; el DSN de la
API lo dice con todas las letras: "La API NUNCA usa takab_ingest").

La salida es la que ya usan `gov_ack_incident`, `app_verify_retire_code` y
`relocate_incident_epicenter`: una función `SECURITY DEFINER` cuyo dueño es
`takab_ingest` (BYPASSRLS), con la validación dura DENTRO y con
`REVOKE ... FROM PUBLIC` + `GRANT EXECUTE` solo a `takab_app`. La superficie que
se abre no es "escribir en notification_jobs": es "mover el desenlace de UN job
identificado por un id de proveedor, y solo hacia adelante".

**El orden lo decide quien llama, y la escala vive en Python** (`p_outranks`,
derivado de `notify/callbacks.STATUS_RANK`). Es deliberado: una segunda copia de
la escala aquí dentro sería la fuente de la próxima divergencia. Esta función es
mecanismo puro — compara, escribe y deja evidencia.

Y el `ALTER FUNCTION ... OWNER TO takab_ingest` **se comprueba**: si fallara, la
función correría como el migrador, la RLS `FORCE` la dejaría sin ver ni una fila
y el endpoint devolvería «no reconozco este callback» para siempre, en silencio.
Un despliegue muerto es infinitamente mejor que eso, así que la migración revienta.

──────────────────────────────────────────────────────────────────────────────
Invariantes de este repo
──────────────────────────────────────────────────────────────────────────────
* Idempotente (T-1.45): `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`,
  `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, políticas con
  `DROP POLICY IF EXISTS`. Corre dos veces seguidas sin cambiar nada.
* DDL sobre tabla PREEXISTENTE (`notification_jobs`) ⇒ como usuario de conexión,
  **sin** `SET ROLE`. `SET ROLE takab_migrator` **solo** para el objeto NUEVO.
* Local migra como superusuario y la nube como `takab_migrator`: la cesión de
  propiedad exige que el usuario de conexión sea miembro de `takab_ingest` y que
  `takab_ingest` tenga `CREATE` en `public` — las dos cosas las abre
  `deploy/cloud/deploy.sh` alrededor del `alembic upgrade` desde la 0011.

Revision ID: 0040_notify_delivery_receipts
Revises: 0039_table_owners_migrator
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0040_notify_delivery_receipts"
down_revision: str | None = "0039_table_owners_migrator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- 1 y 2: columnas sobre tabla PREEXISTENTE (sin SET ROLE) -------------------
_COLUMNAS = """
ALTER TABLE notification_jobs
  ADD COLUMN IF NOT EXISTS provider_message_id text,
  ADD COLUMN IF NOT EXISTS delivered_at        timestamptz,
  ADD COLUMN IF NOT EXISTS last_status         text,
  ADD COLUMN IF NOT EXISTS last_status_at      timestamptz,
  ADD COLUMN IF NOT EXISTS inflight_until      timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_jobs_provider_msg
  ON notification_jobs (channel, provider_message_id)
  WHERE provider_message_id IS NOT NULL;
"""

# --- 2: la cuarentena persistente (objeto NUEVO ⇒ SET ROLE takab_migrator) -----
_CUARENTENA = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS notify_template_quarantine (
  channel        text NOT NULL,
  template_name  text NOT NULL,
  reason         text NOT NULL,
  quarantined_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (channel, template_name)
);

RESET ROLE;

GRANT SELECT ON notify_template_quarantine TO takab_app;
GRANT SELECT, INSERT, UPDATE ON notify_template_quarantine TO takab_ingest;

ALTER TABLE notify_template_quarantine ENABLE ROW LEVEL SECURITY;
ALTER TABLE notify_template_quarantine FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ntq_read ON notify_template_quarantine;
CREATE POLICY ntq_read ON notify_template_quarantine FOR SELECT
  USING (app_role() IS NOT NULL);
"""

# --- 3: el desenlace tardío, en una sola sentencia atómica --------------------
_FUNCION = """
CREATE OR REPLACE FUNCTION app_notify_delivery(
  p_channel     text,
  p_message_id  text,
  p_status      text,
  p_outranks    text[],
  p_delivered   boolean,
  p_undelivered boolean,
  p_at          timestamptz,
  p_detail      text
) RETURNS TABLE (
  o_job_id       uuid,
  o_applied      boolean,
  o_job_status   text,
  o_last_status  text,
  o_delivered_at timestamptz
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_job      notification_jobs%ROWTYPE;
  v_at       timestamptz := LEAST(coalesce(p_at, now()), now());
  v_kind     text := NULL;
  v_opened   timestamptz;
BEGIN
  -- El identificador de proveedor es la ÚNICA llave de entrada. Ni tenant, ni
  -- job_id, ni nada que quien llama pueda elegir de un catálogo.
  SELECT * INTO v_job
    FROM notification_jobs
   WHERE channel = p_channel
     AND provider_message_id = p_message_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;  -- cero filas: quien llama NO puede distinguir esto de una firma mala
  END IF;

  -- Reenvío o callback fuera de orden: no se toca nada. `p_outranks` trae los
  -- estados que el nuevo puede pisar; lo que no está en la lista —incluido él
  -- mismo— se queda como está.
  IF v_job.last_status IS NOT NULL AND NOT (v_job.last_status = ANY (p_outranks)) THEN
    RETURN QUERY SELECT v_job.job_id, false, v_job.status, v_job.last_status,
                        v_job.delivered_at;
    RETURN;
  END IF;

  UPDATE notification_jobs j
     SET last_status    = p_status,
         last_status_at = v_at,
         -- La PRIMERA confirmación manda: un `read` posterior no reescribe el
         -- instante en que llegó al teléfono.
         delivered_at   = CASE WHEN p_delivered AND j.delivered_at IS NULL
                               THEN v_at ELSE j.delivered_at END,
         -- Una entrega confirmada gana sobre cualquier cosa; un fallo declarado
         -- pone el job en rojo SALVO que ya constara entregado.
         status         = CASE WHEN p_delivered THEN 'sent'
                               WHEN p_undelivered AND j.delivered_at IS NULL THEN 'failed'
                               ELSE j.status END,
         error          = CASE WHEN p_undelivered AND j.delivered_at IS NULL
                               THEN left(coalesce(p_detail, p_status), 500) ELSE j.error END
   WHERE j.job_id = v_job.job_id
  RETURNING j.* INTO v_job;

  -- Evidencia SOLO en los dos hechos terminales (regla de oro 10: por
  -- transición, no por intervalo). Los estados de vuelo mueven `last_status` y
  -- no dejan fila: `incident_actions` es append-only y exenta de poda, y una
  -- fila por cada `queued`/`sent` la inflaría para siempre.
  IF p_delivered AND v_job.delivered_at = v_at THEN
    v_kind := 'notify_delivered';
  ELSIF p_undelivered AND v_job.status = 'failed' THEN
    v_kind := 'notify_failed';
  END IF;

  IF v_kind IS NOT NULL THEN
    SELECT opened_at INTO v_opened FROM incidents WHERE incident_id = v_job.incident_id;
    INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
    VALUES (
      v_job.incident_id, v_job.tenant_id, v_kind,
      -- El actor se concatena en tres trozos y no en un literal de una pieza.
      -- Alembic pasa este SQL por `sqlalchemy.text()`, que toma dos puntos
      -- seguidos de una palabra por un parámetro de enlace y aborta la
      -- migración; dos puntos seguidos de comilla no le disparan.
      'system:notify:' || p_channel || ':' || 'callback',
      jsonb_build_object(
        'job_id',              v_job.job_id,
        'channel',             p_channel,
        'mode',                v_job.mode,
        'provider_status',     p_status,
        'provider_message_id', p_message_id,
        'detail',              left(coalesce(p_detail, ''), 500),
        'sent_at',             v_job.sent_at,
        'delivered_at',        v_job.delivered_at,
        -- Latencia de la ENTREGA de verdad, no de la aceptación. Es la cifra
        -- que la ficha pedía poder decir: "salió a las …03 y llegó a las …19".
        'latency_s',           CASE WHEN v_opened IS NOT NULL
                                    THEN extract(epoch FROM (v_at - v_opened)) END,
        'deadline_met',        CASE WHEN v_job.deadline_at IS NULL THEN NULL
                                    ELSE v_at <= v_job.deadline_at END
      )
    )
    -- Un lote de Meta puede traer dos estados del mismo job en la MISMA
    -- transacción, y `uq_incident_actions_ack` usa el ts de transacción.
    ON CONFLICT (incident_id, kind, actor, ts) DO NOTHING;
  END IF;

  RETURN QUERY SELECT v_job.job_id, true, v_job.status, v_job.last_status, v_job.delivered_at;
END
$fn$;

REVOKE ALL ON FUNCTION app_notify_delivery(text,text,text,text[],boolean,boolean,
  timestamptz,text) FROM PUBLIC;
"""

# La cesión de propiedad + su comprobación. Ver el docstring: sin dueño
# `takab_ingest` la función no ve una sola fila (RLS FORCE) y el endpoint
# mentiría en silencio para siempre.
_DUENO = """
DO $mig$
BEGIN
  IF pg_has_role(current_user, 'takab_ingest', 'USAGE') THEN
    ALTER FUNCTION app_notify_delivery(text,text,text,text[],boolean,boolean,
      timestamptz,text) OWNER TO takab_ingest;
  END IF;

  IF (SELECT pg_get_userbyid(proowner) FROM pg_proc
       WHERE proname = 'app_notify_delivery') <> 'takab_ingest' THEN
    RAISE EXCEPTION '0040: app_notify_delivery debe pertenecer a takab_ingest '
      '(es SECURITY DEFINER y necesita BYPASSRLS). Dueño actual: %. '
      'Falta GRANT takab_ingest TO % y GRANT CREATE ON SCHEMA public TO takab_ingest.',
      (SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE proname = 'app_notify_delivery'),
      current_user;
  END IF;
END
$mig$;

GRANT EXECUTE ON FUNCTION app_notify_delivery(text,text,text,text[],boolean,boolean,
  timestamptz,text) TO takab_app;
"""

# La vuelta atrás no degrada ningún dato: quita lo añadido. Las columnas se van
# con su información —era información que ANTES no existía—, y la cuarentena
# vuelve a ser lo que era: memoria de un proceso.
_DOWN = """
DROP FUNCTION IF EXISTS app_notify_delivery(text,text,text,text[],boolean,boolean,
  timestamptz,text);
DROP TABLE IF EXISTS notify_template_quarantine;
DROP INDEX IF EXISTS uq_notification_jobs_provider_msg;
ALTER TABLE notification_jobs
  DROP COLUMN IF EXISTS provider_message_id,
  DROP COLUMN IF EXISTS delivered_at,
  DROP COLUMN IF EXISTS last_status,
  DROP COLUMN IF EXISTS last_status_at,
  DROP COLUMN IF EXISTS inflight_until;
"""


def upgrade() -> None:
    op.execute(_COLUMNAS)
    op.execute(_CUARENTENA)
    op.execute(_FUNCION)
    op.execute(_DUENO)


def downgrade() -> None:
    op.execute(_DOWN)
