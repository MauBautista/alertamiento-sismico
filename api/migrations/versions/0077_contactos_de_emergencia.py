"""T-9.80 · D-48 · contactos de emergencia: quien pide ayuda avisa a los SUYOS

Hasta tres personas por titular —nombre, correo y, opcional, teléfono E.164— a
quienes TAKAB avisa por correo si el titular marca «NECESITO AYUDA» tras un sismo.
Son datos de TERCEROS que el titular declara con su consentimiento: se guarda la
versión del aviso (``privacy/texts/contactos_es_mx.json``) que aceptó y cuándo.

## ``emergency_contacts``

* ``posicion`` 1..3 con ``UNIQUE (tenant_id, user_sub, posicion)``: el tope de tres
  lo pone la base, no sólo el router.
* RLS ``ec_self``: SOLO el titular ve y edita su lista. Ningún rol —ni el
  administrador del cliente ni el de TAKAB— la lee por la API: la política filtra
  por ``user_sub`` y no sólo por tenant.
* ``ec_arco_on_behalf`` (+ su lectura): el responsable con CONSTANCIA los borra
  dentro de ``privacy_erase_subject`` (T-2.80.b).
* ``ec_retention_*``: el job de retención, interno y SIN portador, borra los de
  quien se dio de baja (``privacy/retention.py``, regla ``emergency_contacts.rows``).

## ``uq_need_help_contacts``

UN aviso a los contactos por persona y por incidente: el check-in ``need_help``
inserta la acción ``need_help_contacts`` con ``ON CONFLICT DO NOTHING`` sobre este
índice, así que reenviarlo no manda un segundo correo.

## ``privacy_erase_subject``

ARCO gana un paso: BORRA los contactos del sujeto (fila entera) y lo cuenta en
``affected.emergency_contacts``. Se REEMPLAZA la función con la misma firma (el
ancla ``ERASE_FN_ARGS`` no se mueve) y como ``takab_migrator``, su dueño desde 0038.

## Permisos

``takab_app``: SELECT/INSERT/UPDATE/DELETE, siempre bajo RLS. ``takab_ingest``:
SELECT, ESCRITO aquí (el notificador lee los correos al encolar; en la nube la
``ALL TABLES`` de la 0001 no alcanza a una tabla que nace después).

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+. El cuerpo de la función
lleva ``%ROWTYPE``: se ejecuta por el cursor crudo, como la 0071.

Revision ID: 0077_contactos_de_emergencia
Revises: 0076_catalogo_de_mexico
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0077_contactos_de_emergencia"
down_revision: str | None = "0076_catalogo_de_mexico"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = r"""
-- Objeto NUEVO y DDL sobre `incident_actions` ⇒ `SET ROLE takab_migrator`
-- (invariante de dueños).
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS emergency_contacts (
  contact_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(tenant_id),
  user_sub        uuid NOT NULL,
  posicion        smallint NOT NULL CHECK (posicion BETWEEN 1 AND 3),
  display_name    text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
  email           text NOT NULL CHECK (char_length(email) <= 254
                                       AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone           text NULL CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{7,14}$'),
  consent_version text NOT NULL,
  consented_at    timestamptz NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_emergency_contacts_pos UNIQUE (tenant_id, user_sub, posicion)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_need_help_contacts
  ON incident_actions (incident_id, (payload->>'user_sub')) WHERE kind = 'need_help_contacts';

RESET ROLE;

COMMENT ON TABLE emergency_contacts IS
  '[T-9.80 · D-48] Hasta 3 contactos por titular, avisados por correo si marca '
  'NECESITO AYUDA. Datos de TERCEROS: solo el titular los ve (RLS por user_sub).';

GRANT SELECT, INSERT, UPDATE, DELETE ON emergency_contacts TO takab_app;
GRANT SELECT ON emergency_contacts TO takab_ingest;

ALTER TABLE emergency_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE emergency_contacts FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ec_self ON emergency_contacts;
CREATE POLICY ec_self ON emergency_contacts FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
DROP POLICY IF EXISTS ec_arco_on_behalf_read ON emergency_contacts;
CREATE POLICY ec_arco_on_behalf_read ON emergency_contacts FOR SELECT
  USING (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub));
DROP POLICY IF EXISTS ec_arco_on_behalf ON emergency_contacts;
CREATE POLICY ec_arco_on_behalf ON emergency_contacts FOR DELETE
  USING (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub));
DROP POLICY IF EXISTS ec_retention_read ON emergency_contacts;
CREATE POLICY ec_retention_read ON emergency_contacts FOR SELECT
  USING (tenant_id = app_tenant_id() AND app_is_takab_internal() AND app_user_id() IS NULL);
DROP POLICY IF EXISTS ec_retention_delete ON emergency_contacts;
CREATE POLICY ec_retention_delete ON emergency_contacts FOR DELETE
  USING (tenant_id = app_tenant_id() AND app_is_takab_internal() AND app_user_id() IS NULL);
"""

# El acto ARCO, con el paso nuevo. Misma firma ⇒ `CREATE OR REPLACE` conserva los
# privilegios (EXECUTE sólo a `takab_app`); se repiten igualmente, son idempotentes.
_FUNCION = (
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

# La vuelta atrás deja la función como estaba en la 0038 salvo por el paso de los
# contactos: sin la tabla, ese DELETE fallaría. Se quita la tabla y se restituye el
# cuerpo sin ese paso.
_DOWN = r"""
SET ROLE takab_migrator;
DROP INDEX IF EXISTS uq_need_help_contacts;
DROP TABLE IF EXISTS emergency_contacts;
RESET ROLE;
"""


_PASO_CONTACTOS = r"""
  -- [T-9.80 · 0077] Los contactos de emergencia se BORRAN, fila entera: son datos
  -- de TERCEROS que el titular declaró y sólo sirven para avisarles. No documentan
  -- ningún hecho (el aviso enviado vive en `incident_actions`/`notification_jobs`),
  -- así que anonimizarlos dejaría filas que no significan nada.
  DELETE FROM emergency_contacts
   WHERE tenant_id = v_tenant AND user_sub = v_user;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('emergency_contacts', v_n);

"""


def _exec(sql: str) -> None:
    """Por el cursor psycopg crudo: el cuerpo lleva `%ROWTYPE` y `:=`, que el
    binding de SQLAlchemy tomaría por marcadores."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_TABLA)
    _exec(_FUNCION)


def downgrade() -> None:
    _exec(_FUNCION.replace(_PASO_CONTACTOS, ""))
    _exec(_DOWN)
