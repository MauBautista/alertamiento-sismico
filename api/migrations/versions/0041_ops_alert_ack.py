"""T-2.78.a · Dónde se escribe que alguien contestó — y que nadie contestó.

La cadena de operación (CloudWatch → SNS → correo) no dejaba rastro en ninguna
tabla de TAKAB, y AWS tampoco lo da: el registro de estado de entrega de SNS
soporta Firehose, SQS, Lambda, HTTPS y endpoints de aplicación — `email` y
`email-json` **no están en la lista**. Así que "publicado" era todo lo que se
podía afirmar, y "leído por una persona" no se podía afirmar jamás.

──────────────────────────────────────────────────────────────────────────────
1 · TABLA PROPIA, y no el camino de `incidents_ack` — la razón, escrita
──────────────────────────────────────────────────────────────────────────────
La ficha pide decidirlo explícitamente. Se decide **tabla propia**, por tres
cosas que no son de estilo:

* **No hay tenant.** Una alarma de `takab-dev-dlq-backfill`, del archivado de
  WAL o del disco de la EC2 es de la PLATAFORMA. `incidents_ack` cuelga de
  `incidents`, que lleva `tenant_id` y RLS por cliente: meter aquí un acuse de
  operación obligaría a inventarle un dueño — el mismo argumento por el que
  `notify_template_quarantine` (0040) tampoco lo lleva. Y peor que inventarlo:
  cualquier elección haría que un cliente pudiera VER que el on-call de TAKAB no
  contestó a las 3 de la mañana.
* **Son dos cadenas y acreditar una no dice nada de la otra.** CloudWatch→SNS→
  on-call no comparte código, destinatario ni permiso con `notify/orchestrator`.
  El hueco de `ses:SendEmail` de julio-2026 estuvo tapado exactamente por
  confundirlas. Un `kind` más en `incident_actions` las habría vuelto a mezclar
  en la misma consulta, en el mismo tablero y en el mismo informe.
* **`incident_actions` es append-only y exenta de poda por compliance.** Es
  evidencia de un incidente sísmico ante un tercero. Un correo de operación
  contestado a tiempo no es eso, y engordar la tabla de compliance con ruido de
  plataforma degrada lo que esa tabla existe para sostener.

──────────────────────────────────────────────────────────────────────────────
2 · `ops_alert_notices` — la fila NACE SIN ACUSE, y ése es el diseño
──────────────────────────────────────────────────────────────────────────────
"Si nadie acusa, eso también se registra". La pregunta operativa es quién
escribe esa fila: nadie va a llamar a un endpoint para decir "no contesté". La
respuesta es que **no hace falta que nadie la escriba después**: la escribe la
máquina que recibió el aviso, en el instante del aviso, con su plazo ya puesto,
y nace **sin acuse**. El acuse solo puede MODIFICAR una fila que ya existe.

El `CHECK` de acuse completo es el candado del criterio 5 y vive en la base a
propósito, no en el código: **no se puede nombrar a quien acusó sin la hora, ni
poner la hora sin nombre**. Un `UPDATE` a mano lo intenta y la base lo rechaza.

`unacked_at` es lo único que estampa el barrido: la hora en que el silencio dejó
de ser espera y pasó a fallo declarado. No sustituye a la fila — la fecha.

──────────────────────────────────────────────────────────────────────────────
3 · `ops_oncall_contacts` — la credencial que se puede usar a las 3 de la mañana
──────────────────────────────────────────────────────────────────────────────
Un acuse que exija consola + MFA es un acuse que no se va a dar, y entonces la
métrica mide fricción y no atención. Un enlace que cualquiera pueda pulsar no
acredita nada (y los escáneres de los buzones pulsan los enlaces de los correos:
un acuse por `GET` lo fabricaría una máquina). Lo elegido es una **credencial
personal**: 256 bits acuñados una vez, de los que aquí solo vive el **hash**,
con caducidad y revocación por fila.

**NADIE tiene SELECT sobre esta tabla**, ni `takab_app`. No es un olvido: los
hashes no tienen que ser alcanzables desde ninguna sesión de la API, y la única
puerta es `app_ops_alert_ack`, que compara por igualdad y no devuelve nada de la
credencial salvo la etiqueta de quien acusó.

──────────────────────────────────────────────────────────────────────────────
4 · Por qué SECURITY DEFINER (igual que 0040)
──────────────────────────────────────────────────────────────────────────────
El endpoint del suscriptor SNS es PÚBLICO: no trae sesión, luego no hay
`app.tenant_id` ni `app.role`. La API conecta como `takab_app` y la RLS de estas
tablas es default-deny con FORCE, así que ni con un GRANT podría escribir. Mismo
patrón que `app_notify_delivery` / `gov_ack_incident`: función `SECURITY
DEFINER` con dueño `takab_ingest` (BYPASSRLS), `REVOKE ... FROM PUBLIC` y
EXECUTE solo para `takab_app`, con la validación DENTRO. Y la cesión de
propiedad **se comprueba**: sin ella la función correría como el migrador, la
RLS FORCE la dejaría sin ver una fila y el endpoint diría "no reconozco esto"
para siempre, en silencio.

La vista va con `security_invoker = true` (PG15+): así la RLS que se aplica es
la del rol que consulta y no la del dueño de la vista — una vista sobre una
tabla con RLS es, si no, la forma más limpia de saltarse esa RLS sin querer.

──────────────────────────────────────────────────────────────────────────────
Invariantes de este repo
──────────────────────────────────────────────────────────────────────────────
* Idempotente (T-1.45): `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT
  EXISTS`, `CREATE OR REPLACE FUNCTION/VIEW`, políticas con `DROP POLICY IF
  EXISTS`. Corre dos veces seguidas sin cambiar nada.
* Objetos NUEVOS ⇒ `SET ROLE takab_migrator` (así el dueño es el que exige
  0039); no hay DDL sobre tabla preexistente en esta revisión.
* Local migra como superusuario y la nube como `takab_migrator`: la cesión de
  propiedad de la función exige que el usuario de conexión sea miembro de
  `takab_ingest` y que `takab_ingest` tenga CREATE en `public` — las dos las
  abre `deploy/cloud/deploy.sh` alrededor del `alembic upgrade` desde la 0011.

Revision ID: 0041_ops_alert_ack
Revises: 0040_notify_delivery_receipts
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041_ops_alert_ack"
down_revision: str | None = "0040_notify_delivery_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- 1: las dos tablas (objetos NUEVOS ⇒ SET ROLE takab_migrator) -------------
_TABLAS = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS ops_oncall_contacts (
  contact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label      text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  issued_at  timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS ops_alert_notices (
  notice_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sns_message_id   text NOT NULL UNIQUE,
  topic_arn        text NOT NULL,
  alarm_name       text,
  alarm_state      text,
  subject          text,
  state_reason     text,
  published_at     timestamptz,
  received_at      timestamptz NOT NULL DEFAULT now(),
  requires_ack     boolean     NOT NULL DEFAULT false,
  ack_deadline_at  timestamptz,
  acked_at         timestamptz,
  acked_by         text,
  acked_contact_id uuid REFERENCES ops_oncall_contacts(contact_id),
  unacked_at       timestamptz,
  CONSTRAINT ops_alert_notices_acuse_completo
    CHECK ((acked_at IS NULL) = (acked_by IS NULL)),
  CONSTRAINT ops_alert_notices_plazo_si_pide_acuse
    CHECK (NOT requires_ack OR ack_deadline_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ops_alert_notices_abiertos
  ON ops_alert_notices (ack_deadline_at)
  WHERE requires_ack AND acked_at IS NULL AND unacked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ops_alert_notices_recibidos
  ON ops_alert_notices (received_at DESC);

RESET ROLE;
"""

# --- 2: permisos y RLS ---------------------------------------------------------
# `ops_oncall_contacts` NO recibe grants de aplicacion: los hashes de credencial
# no tienen que ser alcanzables desde ninguna sesion. La unica puerta es la
# funcion SECURITY DEFINER de abajo, que corre como su dueño.
_PERMISOS = """
GRANT SELECT ON ops_alert_notices TO takab_app;
GRANT SELECT, INSERT, UPDATE ON ops_alert_notices TO takab_ingest;
GRANT SELECT, INSERT, UPDATE ON ops_oncall_contacts TO takab_ingest;

-- LOS DOS REVOKE SON EL CIERRE DE UNA DIVERGENCIA MEDIDA, no cinturon de mas.
--
-- La 0001 termina con `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN
-- SCHEMA public TO takab_app` y ese grant masivo corre DESPUES del cuerpo de
-- `db/schema.sql`. Resultado: en una base NUEVA (el camino de la nube) `takab_app`
-- salia con SELECT sobre la tabla de hashes de credencial y con INSERT/UPDATE/
-- DELETE sobre los avisos; en una base EXISTENTE (camino incremental) no, porque
-- estas tablas no existian cuando corrio aquel grant. Dos despliegues con permisos
-- distintos, y el local —el que se prueba— era el bueno: exactamente la forma de
-- "verde aqui, otra cosa en produccion" que ya costo un despliegue.
--
-- La 0041 corre DESPUES de la 0001 tambien en base limpia, asi que revocar aqui
-- iguala los dos caminos sin tocar la migracion inicial. Medido contra base vacia
-- el 2026-08-14: sin estas dos lineas, `has_table_privilege('takab_app',
-- 'ops_oncall_contacts','SELECT')` sale `true` en una base recien creada.
--
-- La RLS ya lo impediria (deny explicito + FORCE, y ninguna politica de escritura),
-- pero una tabla de hashes de credencial es donde SI se ponen dos candados
-- independientes: el dia que alguien añada una politica permisiva por error, el
-- privilegio ausente sigue diciendo que no.
REVOKE ALL ON ops_oncall_contacts FROM takab_app;
REVOKE INSERT, UPDATE, DELETE ON ops_alert_notices FROM takab_app;

ALTER TABLE ops_alert_notices  ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops_alert_notices  FORCE  ROW LEVEL SECURITY;
ALTER TABLE ops_oncall_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops_oncall_contacts FORCE  ROW LEVEL SECURITY;

-- La cadena de operacion es de TAKAB, no de un cliente: que el on-call de la
-- plataforma no contestara a las 3 de la mañana no es dato de nadie mas.
DROP POLICY IF EXISTS ops_alert_notices_read ON ops_alert_notices;
CREATE POLICY ops_alert_notices_read ON ops_alert_notices FOR SELECT
  USING (app_is_takab_internal());

-- `ops_oncall_contacts` no se lee desde NINGUNA sesion. Y la negativa va escrita
-- como politica explicita `USING (false)` en vez de dejar la tabla sin ninguna:
-- las dos cosas son default-deny, pero "cero politicas" es indistinguible de "el
-- restore se comio las politicas" — que es justo lo que el verificador de
-- `ops/restore_check.py` denuncia como daño (`rls_policies`). Una negativa
-- declarada dice que es a proposito y sigue delatando a la que se cayo sola.
DROP POLICY IF EXISTS ops_oncall_contacts_deny ON ops_oncall_contacts;
CREATE POLICY ops_oncall_contacts_deny ON ops_oncall_contacts FOR ALL
  USING (false) WITH CHECK (false);
"""

# --- 3: la vista consultable ---------------------------------------------------
_VISTA = """
CREATE OR REPLACE VIEW v_ops_alert_chain WITH (security_invoker = true) AS
SELECT
  n.notice_id,
  n.sns_message_id,
  n.topic_arn,
  n.alarm_name,
  n.alarm_state,
  n.subject,
  n.state_reason,
  n.published_at,
  n.received_at,
  n.requires_ack,
  n.ack_deadline_at,
  n.acked_at,
  n.acked_by,
  n.unacked_at,
  -- El desenlace se CALCULA de los instantes; no hay columna de estado que
  -- alguien pueda poner en verde por su cuenta. 'acusado' es imposible sin
  -- `acked_at`: es el criterio 5 escrito donde no se puede esquivar.
  CASE
    WHEN NOT n.requires_ack                       THEN 'no_requiere_acuse'
    WHEN n.acked_at IS NOT NULL
     AND n.ack_deadline_at IS NOT NULL
     AND n.acked_at > n.ack_deadline_at           THEN 'acusado_tarde'
    WHEN n.acked_at IS NOT NULL                   THEN 'acusado'
    WHEN n.ack_deadline_at IS NOT NULL
     AND now() > n.ack_deadline_at                THEN 'sin_acuse'
    ELSE                                               'esperando_acuse'
  END AS outcome,
  -- El tiempo hasta el acuse, CONSULTABLE: entre dos instantes que escribio la
  -- propia base. Ya no se reconstruye de las cabeceras de un correo.
  CASE WHEN n.acked_at IS NOT NULL
       THEN extract(epoch FROM (n.acked_at - n.received_at)) END AS ack_latency_s,
  CASE WHEN n.acked_at IS NOT NULL AND n.published_at IS NOT NULL
       THEN extract(epoch FROM (n.acked_at - n.published_at)) END AS ack_latency_publicado_s
FROM ops_alert_notices n;

GRANT SELECT ON v_ops_alert_chain TO takab_app;
"""

# --- 4: registrar el aviso (superficie publica, sin sesion) --------------------
_FN_RECORD = """
CREATE OR REPLACE FUNCTION app_ops_alert_record(
  p_sns_message_id text,
  p_topic_arn      text,
  p_alarm_name     text,
  p_alarm_state    text,
  p_subject        text,
  p_state_reason   text,
  p_published_at   timestamptz,
  p_requires_ack   boolean,
  p_ack_deadline_s double precision
) RETURNS TABLE (
  o_notice_id       uuid,
  o_created         boolean,
  o_requires_ack    boolean,
  o_ack_deadline_at timestamptz
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_now    timestamptz := now();
  v_pide   boolean     := coalesce(p_requires_ack, false);
  v_plazo  double precision := greatest(coalesce(p_ack_deadline_s, 900), 1);
  v_row    ops_alert_notices%ROWTYPE;
BEGIN
  INSERT INTO ops_alert_notices (
    sns_message_id, topic_arn, alarm_name, alarm_state, subject, state_reason,
    published_at, received_at, requires_ack, ack_deadline_at)
  VALUES (
    p_sns_message_id, p_topic_arn, nullif(p_alarm_name, ''), nullif(p_alarm_state, ''),
    nullif(p_subject, ''), nullif(p_state_reason, ''), p_published_at, v_now, v_pide,
    CASE WHEN v_pide THEN v_now + make_interval(secs => v_plazo) END)
  -- SNS REINTENTA. Dos entregas del mismo mensaje son UN aviso, o la metrica de
  -- "cuantas veces nadie contesto" se infla sola.
  ON CONFLICT (sns_message_id) DO NOTHING
  RETURNING * INTO v_row;

  IF FOUND THEN
    RETURN QUERY SELECT v_row.notice_id, true, v_row.requires_ack, v_row.ack_deadline_at;
    RETURN;
  END IF;

  SELECT * INTO v_row FROM ops_alert_notices WHERE sns_message_id = p_sns_message_id;
  RETURN QUERY SELECT v_row.notice_id, false, v_row.requires_ack, v_row.ack_deadline_at;
END
$fn$;

REVOKE ALL ON FUNCTION app_ops_alert_record(text,text,text,text,text,text,timestamptz,
  boolean,double precision) FROM PUBLIC;
"""

# --- 5: acusar (superficie publica, credencial personal) -----------------------
_FN_ACK = """
CREATE OR REPLACE FUNCTION app_ops_alert_ack(p_token_hash text)
RETURNS TABLE (o_token_ok boolean, o_label text, o_acusados jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_now      timestamptz := now();
  v_contacto ops_oncall_contacts%ROWTYPE;
  v_acusados jsonb;
BEGIN
  SELECT * INTO v_contacto
    FROM ops_oncall_contacts
   WHERE token_hash = p_token_hash
     AND revoked_at IS NULL
     AND expires_at > v_now;
  IF NOT FOUND THEN
    -- Credencial inventada, revocada o caducada: las tres, lo mismo. El router
    -- las convierte en la MISMA respuesta que "no habia nada abierto".
    RETURN QUERY SELECT false, NULL::text, '[]'::jsonb;
    RETURN;
  END IF;

  -- Se acusan TODOS los avisos abiertos, no uno elegido por quien llama. Quien
  -- dice "lo tengo" a las 3 de la mañana esta tomando la situacion entera, y
  -- pedirle que teclee un identificador desde el telefono es como no tener
  -- acuse. Cada fila conserva SU `received_at`, asi que la latencia por aviso
  -- sigue siendo la suya.
  WITH acusados AS (
    UPDATE ops_alert_notices n
       SET acked_at         = v_now,
           acked_by         = v_contacto.label,
           acked_contact_id = v_contacto.contact_id
     WHERE n.requires_ack AND n.acked_at IS NULL
    RETURNING n.notice_id, n.alarm_name, n.received_at, n.ack_deadline_at
  )
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'notice_id',  a.notice_id,
           'alarm_name', a.alarm_name,
           'acked_at',   v_now,
           'latency_s',  extract(epoch FROM (v_now - a.received_at)),
           'tarde',      (a.ack_deadline_at IS NOT NULL AND v_now > a.ack_deadline_at)
         )), '[]'::jsonb)
    INTO v_acusados
    FROM acusados a;

  RETURN QUERY SELECT true, v_contacto.label, v_acusados;
END
$fn$;

REVOKE ALL ON FUNCTION app_ops_alert_ack(text) FROM PUBLIC;
"""

# La cesion de propiedad + su comprobacion. Sin dueño `takab_ingest` estas
# funciones no ven una sola fila (RLS FORCE) y las dos superficies mentirian en
# silencio para siempre: el aviso no se registraria y el acuse no acusaria nada.
_DUENO = """
DO $mig$
DECLARE
  v_fn text;
  v_owner text;
BEGIN
  FOREACH v_fn IN ARRAY ARRAY['app_ops_alert_record', 'app_ops_alert_ack'] LOOP
    IF pg_has_role(current_user, 'takab_ingest', 'USAGE') THEN
      EXECUTE format('ALTER FUNCTION %I(%s) OWNER TO takab_ingest', v_fn,
        (SELECT pg_get_function_identity_arguments(p.oid) FROM pg_proc p
          WHERE p.proname = v_fn));
    END IF;
    SELECT pg_get_userbyid(proowner) INTO v_owner FROM pg_proc WHERE proname = v_fn;
    IF v_owner IS DISTINCT FROM 'takab_ingest' THEN
      RAISE EXCEPTION '0041: % debe pertenecer a takab_ingest (es SECURITY DEFINER y '
        'necesita BYPASSRLS). Dueño actual: %. Falta GRANT takab_ingest TO % y '
        'GRANT CREATE ON SCHEMA public TO takab_ingest.', v_fn, v_owner, current_user;
    END IF;
  END LOOP;
END
$mig$;

GRANT EXECUTE ON FUNCTION app_ops_alert_record(text,text,text,text,text,text,timestamptz,
  boolean,double precision) TO takab_app;
GRANT EXECUTE ON FUNCTION app_ops_alert_ack(text) TO takab_app;
"""

# La vuelta atras quita lo añadido; no degrada ningun dato preexistente, porque
# ninguno de estos hechos existia antes de esta revision.
_DOWN = """
DROP VIEW IF EXISTS v_ops_alert_chain;
DROP FUNCTION IF EXISTS app_ops_alert_ack(text);
DROP FUNCTION IF EXISTS app_ops_alert_record(text,text,text,text,text,text,timestamptz,
  boolean,double precision);
DROP TABLE IF EXISTS ops_alert_notices;
DROP TABLE IF EXISTS ops_oncall_contacts;
"""


def upgrade() -> None:
    op.execute(_TABLAS)
    op.execute(_PERMISOS)
    op.execute(_VISTA)
    op.execute(_FN_RECORD)
    op.execute(_FN_ACK)
    op.execute(_DUENO)


def downgrade() -> None:
    op.execute(_DOWN)
