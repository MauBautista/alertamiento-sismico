"""T-9.80 · D-48 · ARCO vacía los correos de los contactos en los avisos YA enviados

La 0077 borra la lista de contactos de emergencia del titular. Pero el aviso que les
llegó cuando marcó NECESITO AYUDA guarda sus correos en
``notification_jobs.target.to``, y ahí se quedaban: ni ARCO ni la retención los
cubrían (hueco declarado en la ficha T-9.80).

## El estado borrado

La FILA se conserva: el aviso existió, a tal hora, y es un hecho del incidente. Su
``target`` pasa a ser exactamente ``{"to": [], "pii_borrada": true}``. Es el MISMO
valor que escribe la retención (``privacy/retention.py``), así que ARCO después de la
poda, o al revés, encuentra el aviso ya borrado y no lo vuelve a contar.

## La frontera, en la base

``privacy_erase_subject`` corre como ``takab_app`` y ya resolvió el sujeto (él mismo,
o el de una constancia de SU cliente). El paso nuevo es un ``UPDATE`` normal, y
quien lo acota es la base:

* ``UPDATE`` de UNA columna, ``target``, y ni ``INSERT`` ni ``DELETE``. La 0001
  concede a ``takab_app`` los tres sobre TODA la tabla en una base nueva (``ALL
  TABLES``). Las sesiones de cliente no tenían política de escritura, pero las
  internas sí (``notification_jobs_admin``, ``FOR ALL``): podían reescribir
  cualquier aviso, o borrarlo y volver a meterlo PENDIENTE con otro destinatario. En
  la nube la tabla nació en la 0005 con sólo ``SELECT``; ahora las dos bases
  coinciden.
* ``nj_arco_vaciar`` (permisiva, ``FOR UPDATE``): QUIÉN, el propio cliente.
* ``nj_solo_borrar_avisos`` (RESTRICTIVA, ``FOR UPDATE``): QUÉ, y obliga también a
  las sesiones internas. Sólo el estado borrado, sólo en avisos
  ``need_help_contacts`` de un incidente CERRADO, y sólo si el titular es borrable
  por esta sesión: él mismo o un responsable con constancia
  (``app_can_erase_subject``), aunque el aviso siga pendiente; o el job de retención
  (sesión interna sin portador, como ``ec_retention_*``), sólo si ya salió. No se
  puede redirigir un aviso, tampoco desde una sesión interna. Entre dos titulares
  borrables por el mismo responsable la política no distingue: eso lo hace el
  ``WHERE`` de ``privacy_erase_subject``, y tiene su prueba.

ARCO borra también el aviso PENDIENTE del titular. Si no, una pasada del notificador
que leyó los contactos antes del acto lo marcaba ``sent`` con los correos dentro
(medido), y nadie volvía a barrerlo.

Se descartó una función ``SECURITY DEFINER``: para el caso «por cuenta de otro»
tendría que leer ``privacy_erasure_requests``, que se le NIEGA a propósito a
``takab_ingest`` (``REVOKE ALL``), y devolvérselo revertiría esa decisión.

Lo que esta migración NO cierra: cualquier sesión interna SIN portador pasa por la
rama del job de retención, igual que en ``ec_retention_*`` (0077). La API sólo abre
sesiones así para LEER (el hub de WebSocket, la publicación de releases).

## ``privacy_erase_subject``

Gana el paso ``notification_jobs`` en ``affected``. Misma firma: el ancla
``ERASE_FN_ARGS`` no se mueve. Como ``takab_migrator``, su dueño desde 0038.

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+. El cuerpo lleva
``%ROWTYPE``: va por el cursor crudo, como la 0071 y la 0077.

Revision ID: 0078_arco_vacia_los_avisos
Revises: 0077_contactos_de_emergencia
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0078_arco_vacia_los_avisos"
down_revision: str | None = "0077_contactos_de_emergencia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- 1 · la frontera: quién (permisiva) y qué (restrictiva) -----------------------
# Tabla PREEXISTENTE ⇒ sin SET ROLE: el DDL sobre una tabla que ya existe corre con
# el usuario de conexión (el dueño histórico varía por base), como en la 0047.
_POLITICA = r"""
-- La 0001 concede a `takab_app` UPDATE sobre TODA la tabla (`ALL TABLES`) en una
-- base nueva. Lo acotaba la RLS, y a medias: las sesiones de cliente no tenían
-- política de UPDATE, pero las INTERNAS sí (`notification_jobs_admin`, FOR ALL) y
-- podían reescribir cualquier columna de cualquier aviso, pendientes incluidos
-- (medido: `SET status` como `takab_support`). Queda UNA columna, y la restrictiva
-- de abajo dice qué se puede escribir en ella. Ninguna ruta de la API escribe aquí:
-- el notificador conecta como `takab_ingest`.
--
-- Y sin INSERT ni DELETE, que la 0001 también concede: con ellos, una sesión interna
-- borraba un aviso y lo volvía a meter PENDIENTE con otro destinatario (medido), y el
-- notificador lo mandaba. En la nube la tabla nació en la 0005 con sólo SELECT; así
-- las dos bases quedan iguales.
REVOKE INSERT, UPDATE, DELETE ON notification_jobs FROM takab_app;
GRANT UPDATE (target) ON notification_jobs TO takab_app;

-- QUIÉN: el propio cliente. Las sesiones internas ya entraban por
-- `notification_jobs_admin`.
DROP POLICY IF EXISTS nj_arco_vaciar ON notification_jobs;
CREATE POLICY nj_arco_vaciar ON notification_jobs FOR UPDATE TO takab_app
  USING (tenant_id = app_tenant_id())
  WITH CHECK (tenant_id = app_tenant_id());

-- QUÉ: RESTRICTIVA, para que obligue también a las sesiones internas (una
-- permisiva se suma con OR a `notification_jobs_admin` y no las frenaría). Lo ÚNICO
-- que la API puede escribir en esta tabla es el estado borrado de un aviso a los
-- contactos, de su cliente y de un incidente CERRADO (como ARCO, que con uno
-- abierto se difiere: TK409), cuyo titular esta sesión puede borrar: él mismo o un
-- responsable con constancia (`app_can_erase_subject`), aunque el aviso siga
-- pendiente; o el job de retención (sesión interna SIN portador, como
-- `ec_retention_*`), sólo si ya salió.
DROP POLICY IF EXISTS nj_solo_borrar_avisos ON notification_jobs;
CREATE POLICY nj_solo_borrar_avisos ON notification_jobs AS RESTRICTIVE FOR UPDATE TO takab_app
  USING (
    tenant_id = app_tenant_id()
    -- Sólo `state`, y no también `closed_at` como TK409: un estado a medias bloquea
    -- en vez de permitir, y la política no ata una columna más de `incidents`.
    AND NOT EXISTS (
      SELECT 1 FROM incidents i
       WHERE i.incident_id = notification_jobs.incident_id
         AND i.state <> 'closed')
    AND EXISTS (
      SELECT 1 FROM incident_actions a
       WHERE a.action_id = notification_jobs.action_id
         AND a.tenant_id = notification_jobs.tenant_id
         AND a.kind = 'need_help_contacts'
         AND (   (app_is_takab_internal() AND app_user_id() IS NULL
                  AND notification_jobs.status <> 'pending')
              OR a.payload->>'user_sub' = app_user_id()::text
              -- El cast, sólo sobre un UUID bien formado: un `user_sub` basura en
              -- el aviso de OTRA persona tumbaría ARCO para todo el cliente.
              OR CASE WHEN a.payload->>'user_sub'
                           ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                      THEN app_can_erase_subject(a.tenant_id, (a.payload->>'user_sub')::uuid)
                      ELSE false END)))
  WITH CHECK (target = '{"to": [], "pii_borrada": true}'::jsonb);
"""

# --- 2 · el acto ARCO, con el paso nuevo ------------------------------------------
# Misma firma ⇒ `CREATE OR REPLACE` conserva los privilegios; se repiten igual.
_ARCO = (
    "SET ROLE takab_migrator;\n"
    + r"""CREATE OR REPLACE FUNCTION privacy_erase_subject(p_right text, p_via text, p_request uuid)
  RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  v_tenant  uuid := app_tenant_id();
  v_actor   uuid := app_user_id();
  v_user    uuid;
  v_right   text := p_right;
  v_af      jsonb := '{}'::jsonb;
  v_n       integer;
  v_wm      bigint;
  v_row     privacy_erasures%ROWTYPE;
  v_created boolean := true;
BEGIN
  IF v_tenant IS NULL OR v_actor IS NULL THEN
    RAISE EXCEPTION
      'ARCO exige una sesion con portador identificado: el sujeto del borrado '
      'sale de app_user_id() o de una constancia, nunca de un parametro'
      USING ERRCODE = 'TK403';
  END IF;

  IF p_request IS NULL THEN
    -- AUTOSERVICIO. El sujeto ES la sesión: exactamente lo que hacía la T-2.80.
    v_user := v_actor;
  ELSE
    -- POR CUENTA DE OTRO. El sujeto no se acepta: se RESUELVE. El JOIN contra
    -- `user_profiles` por `app_tenant_id()` es lo que lo PRODUCE, así que el
    -- único universo del que puede salir un sujeto es el padrón del tenant de la
    -- sesión. Y la constancia se busca SIN filtro de tenant a propósito: la RLS
    -- ya hace que la de otro cliente no exista para esta sesión. Añadir aquí un
    -- `AND r.tenant_id = v_tenant` sugeriría que el confinamiento es una
    -- comprobación; no lo es, es el único universo que la sesión tiene.
    SELECT u.user_sub, r.right_requested INTO v_user, v_right
      FROM privacy_erasure_requests r
      JOIN user_profiles u
        ON u.tenant_id = app_tenant_id() AND u.user_sub = r.user_sub
     WHERE r.request_id = p_request;
    IF v_user IS NULL THEN
      RAISE EXCEPTION
        'no hay constancia de esa solicitud en este cliente: ejercer ARCO por '
        'cuenta de otro exige registrar antes la solicitud recibida'
        USING ERRCODE = 'TK404';
    END IF;
  END IF;

  -- DECISIÓN: con un incidente ABIERTO en un sitio del titular, se DIFIERE. La
  -- ubicación de un check-in es dato de rescate EN VIVO y anularla a mitad de
  -- una búsqueda es un fallo de seguridad — la clase de fallo que las reglas de
  -- oro 1 y 2 existen para impedir. El derecho no se niega: se aplaza hasta el
  -- cierre (horas), y la petición queda auditada para que el plazo legal corra.
  IF EXISTS (
    SELECT 1 FROM incidents i
     WHERE i.tenant_id = v_tenant
       AND i.state <> 'closed' AND i.closed_at IS NULL
       AND (i.site_id IN (SELECT c.site_id FROM life_checkins c
                           WHERE c.tenant_id = v_tenant AND c.user_id = v_user)
         OR i.site_id IN (SELECT z.site_id FROM user_zone_assignments z
                           WHERE z.tenant_id = v_tenant AND z.user_id = v_user))
  ) THEN
    RAISE EXCEPTION
      'hay un incidente ABIERTO en un sitio del titular: la anonimizacion se '
      'difiere hasta que cierre, porque la ubicacion de un check-in es dato '
      'de rescate en vivo'
      USING ERRCODE = 'TK409';
  END IF;

  -- El mapeo `sub → persona`. Destruirlo es lo que anonimiza todo lo demás.
  UPDATE user_profiles
     SET display_name = '(titular anonimizado)', phone = NULL, updated_at = now()
   WHERE tenant_id = v_tenant AND user_sub = v_user
     AND (display_name IS DISTINCT FROM '(titular anonimizado)' OR phone IS NOT NULL);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('user_profiles', v_n);

  -- La FILA se queda (hubo un dispositivo registrado: es un hecho); muere el
  -- identificador que enruta a la persona.
  UPDATE push_tokens
     SET token = 'arco:' || push_token_id::text,
         endpoint_arn = NULL,
         revoked_at = coalesce(revoked_at, now())
   WHERE tenant_id = v_tenant AND user_sub = v_user
     AND token IS DISTINCT FROM 'arco:' || push_token_id::text;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('push_tokens', v_n);

  -- Se REVOCA, no se destruye: `public_key` verifica la firma de intención de
  -- `damage_reports` (evidencia). Borrarla dejaría esa evidencia sin poder
  -- verificarse, que es podar su integridad por la puerta de atrás.
  UPDATE device_keys SET revoked_at = now()
   WHERE tenant_id = v_tenant AND user_sub = v_user AND revoked_at IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('device_keys', v_n);

  -- La ubicación GPS exacta de una persona. La FILA no se toca: por eso el
  -- check-in anonimizado sigue contando para el histórico del incidente.
  UPDATE life_checkins SET geom = NULL
   WHERE tenant_id = v_tenant AND user_id = v_user AND geom IS NOT NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('life_checkins', v_n);

  -- [T-9.80 · 0077] Los contactos de emergencia se BORRAN, fila entera: son datos
  -- de TERCEROS que el titular declaró y sólo sirven para avisarles. No documentan
  -- ningún hecho (el aviso enviado vive en `incident_actions`/`notification_jobs`),
  -- así que anonimizarlos dejaría filas que no significan nada.
  DELETE FROM emergency_contacts
   WHERE tenant_id = v_tenant AND user_sub = v_user;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('emergency_contacts', v_n);

  -- [T-9.80 · 0078] Los correos de SUS contactos en los avisos YA enviados: el aviso
  -- de NECESITO AYUDA guarda el destinatario en `notification_jobs.target.to`. La
  -- FILA se conserva (hubo un aviso, a tal hora: es un hecho del incidente) y su
  -- destino queda en el estado borrado, el MISMO que escribe la retención. También
  -- el de un aviso aún `pending` (esperaba un reintento con el incidente ya
  -- cerrado): si no, una pasada del notificador que leyó los contactos ANTES de este
  -- acto lo marcaría `sent` con los correos dentro, y nadie volvería a barrerlo. El
  -- notificador, que no manda a contactos que ya no están, lo omitiría igual.
  -- La base pone la frontera (`nj_solo_borrar_avisos`: sólo ese estado, sólo avisos
  -- de un incidente cerrado de un titular que esta sesión puede borrar); este WHERE
  -- elige, además, los de ESTE titular, que la política no distingue de otro igual
  -- de borrable.
  UPDATE notification_jobs j
     SET target = '{"to": [], "pii_borrada": true}'::jsonb
    FROM incident_actions a
   WHERE a.action_id = j.action_id
     AND a.tenant_id = v_tenant
     AND j.tenant_id = v_tenant
     AND a.kind = 'need_help_contacts'
     AND a.payload->>'user_sub' = v_user::text
     -- Idempotencia, comparando el jsonb ENTERO y no con `jsonb_array_length`:
     -- WhatsApp y SMS guardan `to` como CADENA en la misma tabla.
     AND j.target <> '{"to": [], "pii_borrada": true}'::jsonb;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('notification_jobs', v_n);

  SELECT coalesce(max(audit_id), 0) INTO v_wm FROM audit_log WHERE tenant_id = v_tenant;

  INSERT INTO privacy_erasures
    (tenant_id, user_sub, right_exercised, requested_by, request_id, via,
     affected, audit_watermark, audit_digest)
  VALUES
    (v_tenant, v_user, v_right, v_actor, p_request, p_via,
     v_af, v_wm, privacy_audit_digest(v_tenant, v_wm))
  ON CONFLICT (tenant_id, user_sub) DO NOTHING
  RETURNING * INTO v_row;

  -- Repetir el acto re-barre (por si hubo un alta posterior) pero NO escribe una
  -- segunda lápida: la primera es el testigo sellado y no se reescribe.
  IF v_row.erasure_id IS NULL THEN
    v_created := false;
    SELECT * INTO v_row FROM privacy_erasures
     WHERE tenant_id = v_tenant AND user_sub = v_user;
  END IF;

  RETURN to_jsonb(v_row) || jsonb_build_object('created', v_created);
END $$;"""
    + "\nRESET ROLE;\n"
    "REVOKE ALL ON FUNCTION privacy_erase_subject(text,text,uuid) FROM PUBLIC;\n"
    "GRANT EXECUTE ON FUNCTION privacy_erase_subject(text,text,uuid) TO takab_app;\n"
)

# La vuelta atrás deja `privacy_erase_subject` como en la 0077 (sin el paso) y quita
# las dos políticas y el permiso de columna.
_PASO = r"""
  -- [T-9.80 · 0078] Los correos de SUS contactos en los avisos YA enviados: el aviso
  -- de NECESITO AYUDA guarda el destinatario en `notification_jobs.target.to`. La
  -- FILA se conserva (hubo un aviso, a tal hora: es un hecho del incidente) y su
  -- destino queda en el estado borrado, el MISMO que escribe la retención. También
  -- el de un aviso aún `pending` (esperaba un reintento con el incidente ya
  -- cerrado): si no, una pasada del notificador que leyó los contactos ANTES de este
  -- acto lo marcaría `sent` con los correos dentro, y nadie volvería a barrerlo. El
  -- notificador, que no manda a contactos que ya no están, lo omitiría igual.
  -- La base pone la frontera (`nj_solo_borrar_avisos`: sólo ese estado, sólo avisos
  -- de un incidente cerrado de un titular que esta sesión puede borrar); este WHERE
  -- elige, además, los de ESTE titular, que la política no distingue de otro igual
  -- de borrable.
  UPDATE notification_jobs j
     SET target = '{"to": [], "pii_borrada": true}'::jsonb
    FROM incident_actions a
   WHERE a.action_id = j.action_id
     AND a.tenant_id = v_tenant
     AND j.tenant_id = v_tenant
     AND a.kind = 'need_help_contacts'
     AND a.payload->>'user_sub' = v_user::text
     -- Idempotencia, comparando el jsonb ENTERO y no con `jsonb_array_length`:
     -- WhatsApp y SMS guardan `to` como CADENA en la misma tabla.
     AND j.target <> '{"to": [], "pii_borrada": true}'::jsonb;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('notification_jobs', v_n);
"""

# NO se devuelven INSERT, UPDATE ni DELETE de tabla. En una base nueva los daba la
# 0001, pero la 0005 creó esta tabla concediendo a `takab_app` sólo SELECT, y en una
# base anterior a eso nunca los tuvo: devolverlos abriría MÁS de lo que había.
# Ninguna ruta de la API los usa, así que quedarse corto no rompe nada.
_DOWN = (
    "DROP POLICY IF EXISTS nj_solo_borrar_avisos ON notification_jobs",
    "DROP POLICY IF EXISTS nj_arco_vaciar ON notification_jobs",
    "REVOKE UPDATE (target) ON notification_jobs FROM takab_app",
)


def _exec(sql: str) -> None:
    """Por el cursor psycopg crudo: el cuerpo lleva `%ROWTYPE` y `:=`, que el
    binding de SQLAlchemy tomaría por marcadores."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_POLITICA)
    _exec(_ARCO)


def downgrade() -> None:
    _exec(_ARCO.replace(_PASO, ""))
    for sentencia in _DOWN:
        _exec(sentencia)
