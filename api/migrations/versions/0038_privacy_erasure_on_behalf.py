"""T-2.80.b · El responsable ejerce un ARCO recibido por escrito.

EL CASO REAL QUE LA T-2.80 NO CUBRÍA
────────────────────────────────────
La T-2.80 dejó ARCO como autoservicio: el sujeto del borrado es siempre
``app_user_id()``. Eso cubre a quien pulsa el botón en la app y no cubre el caso
normal bajo la LFPDPPP — una persona manda su solicitud **por escrito** al
responsable del tratamiento, y es el responsable quien tiene que ejecutarla.

CÓMO SE ENSANCHA SIN PERDER LA GARANTÍA
───────────────────────────────────────
La virtud de la T-2.80 era que ejercer ARCO sobre un tercero, o cruzar tenants,
no estaba *prohibido*: era **inexpresable**. Convertir eso en un ``IF`` que
compara tenants habría degradado la garantía aunque todos los tests pasaran. Así
que el sujeto sigue sin ser un parámetro. Lo que se acepta es el ``request_id``
de una **constancia**, y el sujeto se RESUELVE dentro de la función:

* ``privacy_erasure_requests`` no tiene parámetro de tenant: lo pone
  ``app_tenant_id()`` por DEFAULT y la RLS lo vuelve a exigir en el WITH CHECK;
* su FK **compuesto** ``(tenant_id, user_sub) → user_profiles`` hace que una
  constancia solo pueda nombrar a alguien del PROPIO padrón — un titular ajeno no
  se rechaza por una comprobación, viola integridad referencial;
* ``privacy_erase_subject(p_right, p_via, p_request)`` resuelve el sujeto con un
  JOIN contra ``user_profiles`` por ``app_tenant_id()``. El sujeto no llega: se
  produce, y el único universo que lo produce es el padrón de la sesión.

Por eso la búsqueda de la constancia **no lleva** ``AND r.tenant_id = v_tenant``:
la RLS ya hace que la de otro cliente no exista para esta sesión, y añadir el
predicado sugeriría que el confinamiento es una comprobación en vez del único
universo disponible.

"EXIGE CONSTANCIA" ES UN PRIVILEGIO, NO UN `if` DEL ROUTER
──────────────────────────────────────────────────────────
``app_can_erase_subject(tenant, subject)`` es el predicado "este portador tiene
constancia registrada para este titular", y de él cuelgan cinco políticas nuevas.
Sin fila de solicitud, el responsable no puede tocar **un solo dato** de esa
persona ni escribir su lápida. Y cada política abre exactamente la fila
ANONIMIZADA en su ``WITH CHECK``: con constancia en mano, un
``UPDATE ... SET display_name = 'Otro'`` sigue siendo un error de RLS.

LA FIRMA VIEJA SE VA
────────────────────
``privacy_erase_subject(text,text)`` se DROPea. Dejar las dos convivientes haría
ambigua la llamada de dos argumentos, y —más importante— dejaría en pie una
puerta que no comprueba nada de lo de arriba. Ojo con la secuencia en base NUEVA:
``db/schema.sql`` ya trae la de tres argumentos, así que la guarda
``to_regprocedure`` de la 0034 ve ausente la de dos y **la crea**; el DROP de aquí
la retira otra vez. Por eso el DROP es incondicional y va antes del CREATE.

INVARIANTES DEL PROYECTO
────────────────────────
Objetos NUEVOS (tabla, funciones) ⇒ ``SET ROLE takab_migrator``; DDL sobre tablas
PREEXISTENTES (``user_profiles``, ``privacy_erasures``), triggers, GRANT/REVOKE,
RLS y políticas ⇒ como usuario de conexión, con ``RESET ROLE`` antes. Idempotente
de principio a fin: ``IF NOT EXISTS``, ``ADD COLUMN IF NOT EXISTS``, guardas
``pg_constraint``/``to_regprocedure`` y ``DROP POLICY IF EXISTS`` antes de cada
``CREATE POLICY``.

Revision ID: 0038_privacy_erasure_on_behalf
Revises: 0037_rule_eval_revoke_delete
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038_privacy_erasure_on_behalf"
down_revision: str | None = "0037_rule_eval_revoke_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# 1. El ancla del FK compuesto (tabla PREEXISTENTE ⇒ usuario de conexión).
#    Redundante con el PK (`user_sub` es único global) y aun así obligatoria:
#    PostgreSQL exige una UNIQUE sobre las columnas exactas del FK compuesto.
# ---------------------------------------------------------------------------

_ANCLA = """
DO $do$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_profiles_tenant_sub'
  ) THEN
    ALTER TABLE user_profiles
      ADD CONSTRAINT uq_user_profiles_tenant_sub UNIQUE (tenant_id, user_sub);
  END IF;
END
$do$;
"""


# ---------------------------------------------------------------------------
# 2. La constancia (objeto NUEVO ⇒ SET ROLE takab_migrator)
# ---------------------------------------------------------------------------

_TABLA = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS privacy_erasure_requests (
  request_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL DEFAULT app_tenant_id() REFERENCES tenants(tenant_id),
  user_sub        uuid NOT NULL,
  right_requested text NOT NULL CHECK (right_requested IN ('cancelacion','oposicion')),
  channel         text NOT NULL
    CHECK (channel IN ('written','email','in_person','legal_representative')),
  received_at     timestamptz NOT NULL,
  proof_ref       text NOT NULL CHECK (char_length(proof_ref) BETWEEN 3 AND 200),
  proof_digest    text NOT NULL CHECK (proof_digest ~ '^[0-9a-f]{64}$'),
  created_by      uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_per_padron_del_tenant FOREIGN KEY (tenant_id, user_sub)
    REFERENCES user_profiles (tenant_id, user_sub),
  CONSTRAINT per_no_es_autoservicio CHECK (created_by <> user_sub)
);

CREATE INDEX IF NOT EXISTS idx_privacy_erasure_requests_sujeto
  ON privacy_erasure_requests (tenant_id, user_sub);

RESET ROLE;
"""


# ---------------------------------------------------------------------------
# 3. La lápida gana la constancia que la autoriza (tabla PREEXISTENTE)
# ---------------------------------------------------------------------------

_LAPIDA = """
ALTER TABLE privacy_erasures
  ADD COLUMN IF NOT EXISTS request_id uuid REFERENCES privacy_erasure_requests(request_id);

DO $do$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'pe_la_via_cuadra_con_la_constancia'
  ) THEN
    ALTER TABLE privacy_erasures
      ADD CONSTRAINT pe_la_via_cuadra_con_la_constancia
      CHECK ((request_id IS NULL) = (via IN ('mobile','web')));
  END IF;
END
$do$;
"""


# ---------------------------------------------------------------------------
# 4. El predicado de la constancia (objeto NUEVO ⇒ SET ROLE takab_migrator)
#
# NO se revoca de PUBLIC a propósito: se evalúa dentro de políticas RLS, y una
# política que llama a una función sin EXECUTE hace fallar la sentencia entera
# del rol que toque la tabla (incluido el worker de notificaciones sobre
# `push_tokens`). No filtra nada: el EXISTS corre bajo la RLS del que pregunta.
# ---------------------------------------------------------------------------

_FN_PUEDE = r"""
DO $do$
BEGIN
  IF to_regprocedure('app_can_erase_subject(uuid,uuid)') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION app_can_erase_subject(p_tenant uuid, p_subject uuid)
        RETURNS boolean LANGUAGE sql STABLE AS $body$
        SELECT p_tenant = app_tenant_id()
           AND app_role() IN ('tenant_admin','takab_superadmin')
           AND EXISTS (
                 SELECT 1 FROM privacy_erasure_requests r
                  WHERE r.tenant_id = p_tenant AND r.user_sub = p_subject)
        $body$
    $fn$;
    EXECUTE 'RESET ROLE';
  END IF;
END
$do$;
"""


# ---------------------------------------------------------------------------
# 5. El acto, ensanchado. DROP incondicional de la firma vieja (ver cabecera) y
#    CREATE guardado de la nueva.
# ---------------------------------------------------------------------------

_FN_ERASE = r"""
SET ROLE takab_migrator;
DROP FUNCTION IF EXISTS privacy_erase_subject(text,text);
RESET ROLE;

DO $do$
BEGIN
  IF to_regprocedure('privacy_erase_subject(text,text,uuid)') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION privacy_erase_subject(p_right text, p_via text, p_request uuid)
        RETURNS jsonb LANGUAGE plpgsql AS $body$
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
          -- AUTOSERVICIO: el sujeto ES la sesion (T-2.80, intacto).
          v_user := v_actor;
        ELSE
          -- POR CUENTA DE OTRO: el sujeto no se acepta, se RESUELVE contra el
          -- padron de app_tenant_id(). Sin filtro de tenant sobre la constancia a
          -- proposito: la RLS ya hace que la de otro cliente no exista aqui.
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

        UPDATE user_profiles
           SET display_name = '(titular anonimizado)', phone = NULL, updated_at = now()
         WHERE tenant_id = v_tenant AND user_sub = v_user
           AND (display_name IS DISTINCT FROM '(titular anonimizado)'
                OR phone IS NOT NULL);
        GET DIAGNOSTICS v_n = ROW_COUNT;
        v_af := v_af || jsonb_build_object('user_profiles', v_n);

        UPDATE push_tokens
           SET token = 'arco:' || push_token_id::text,
               endpoint_arn = NULL,
               revoked_at = coalesce(revoked_at, now())
         WHERE tenant_id = v_tenant AND user_sub = v_user
           AND token IS DISTINCT FROM 'arco:' || push_token_id::text;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        v_af := v_af || jsonb_build_object('push_tokens', v_n);

        UPDATE device_keys SET revoked_at = now()
         WHERE tenant_id = v_tenant AND user_sub = v_user AND revoked_at IS NULL;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        v_af := v_af || jsonb_build_object('device_keys', v_n);

        UPDATE life_checkins SET geom = NULL
         WHERE tenant_id = v_tenant AND user_id = v_user AND geom IS NOT NULL;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        v_af := v_af || jsonb_build_object('life_checkins', v_n);

        SELECT coalesce(max(audit_id), 0) INTO v_wm
          FROM audit_log WHERE tenant_id = v_tenant;

        INSERT INTO privacy_erasures
          (tenant_id, user_sub, right_exercised, requested_by, request_id, via,
           affected, audit_watermark, audit_digest)
        VALUES
          (v_tenant, v_user, v_right, v_actor, p_request, p_via,
           v_af, v_wm, privacy_audit_digest(v_tenant, v_wm))
        ON CONFLICT (tenant_id, user_sub) DO NOTHING
        RETURNING * INTO v_row;

        IF v_row.erasure_id IS NULL THEN
          v_created := false;
          SELECT * INTO v_row FROM privacy_erasures
           WHERE tenant_id = v_tenant AND user_sub = v_user;
        END IF;

        RETURN to_jsonb(v_row) || jsonb_build_object('created', v_created);
      END $body$
    $fn$;
    EXECUTE 'RESET ROLE';
  END IF;
END
$do$;
"""


# ---------------------------------------------------------------------------
# 6. Triggers, privilegios, RLS y políticas (usuario de conexión)
# ---------------------------------------------------------------------------

_RESTO = """
CREATE OR REPLACE TRIGGER trg_privacy_erasure_requests_append_only
  BEFORE UPDATE OR DELETE ON privacy_erasure_requests
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_erasure_requests TO takab_app;
REVOKE UPDATE, DELETE ON privacy_erasure_requests FROM takab_app;
REVOKE ALL ON privacy_erasure_requests FROM takab_ingest;

REVOKE ALL ON FUNCTION privacy_erase_subject(text,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION privacy_erase_subject(text,text,uuid) TO takab_app;

ALTER TABLE privacy_erasure_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_erasure_requests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS per_admin           ON privacy_erasure_requests;
DROP POLICY IF EXISTS per_internal_read   ON privacy_erasure_requests;
DROP POLICY IF EXISTS pe_on_behalf        ON privacy_erasures;
DROP POLICY IF EXISTS up_arco_on_behalf   ON user_profiles;
DROP POLICY IF EXISTS pt_arco_on_behalf   ON push_tokens;
DROP POLICY IF EXISTS dk_arco_on_behalf   ON device_keys;
DROP POLICY IF EXISTS lc_arco_on_behalf   ON life_checkins;

CREATE POLICY per_admin ON privacy_erasure_requests FOR ALL
  USING      (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'))
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));
CREATE POLICY per_internal_read ON privacy_erasure_requests FOR SELECT
  USING (app_is_takab_internal());

-- El `request_id IS NOT NULL` no es decorativo: sin él, el responsable podría
-- fabricar una lápida sin solicitud registrada y "exige constancia" dependería
-- del router. Aquí depende de la base.
CREATE POLICY pe_on_behalf ON privacy_erasures FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND request_id IS NOT NULL
              AND app_can_erase_subject(tenant_id, user_sub));

-- Cada política abre EXACTAMENTE la fila anonimizada: el `USING` dice a quién se
-- puede tocar (solo a alguien con constancia) y el `WITH CHECK`, en qué estado
-- puede quedar. Con constancia en mano, `SET display_name = 'Otro'` sigue siendo
-- un error de RLS: el responsable no hereda "editar al ocupante".
CREATE POLICY up_arco_on_behalf ON user_profiles FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND display_name = '(titular anonimizado)' AND phone IS NULL);
CREATE POLICY pt_arco_on_behalf ON push_tokens FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND token = 'arco:' || push_token_id::text
              AND endpoint_arn IS NULL AND revoked_at IS NOT NULL);
CREATE POLICY dk_arco_on_behalf ON device_keys FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND revoked_at IS NOT NULL);
CREATE POLICY lc_arco_on_behalf ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_id))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_id)
              AND geom IS NULL);

-- Regla de oro 11: la constancia se registra, no se edita ni se poda. El REVOKE
-- va después del `GRANT ... ON ALL TABLES` que el 0001 ejecuta tras el schema
-- (misma lección que la 0028/0030/0033/0034).
REVOKE DELETE ON privacy_erasure_requests FROM takab_app;
"""


def upgrade() -> None:
    op.execute(_ANCLA)
    op.execute(_TABLA)
    op.execute(_LAPIDA)
    op.execute(_FN_PUEDE)
    # Va DESPUÉS de la tabla y de la columna: declara `privacy_erasures%ROWTYPE`
    # y escribe `request_id`.
    op.execute(_FN_ERASE)
    op.execute(_RESTO)


def downgrade() -> None:
    # Deliberadamente NO se borra `privacy_erasure_requests` ni la columna
    # `request_id`: son la constancia de que un titular pidió y de quién ejecutó
    # su solicitud. Un downgrade que las destruyera dejaría lápidas cuya autoría
    # ya no se puede explicar — mismo criterio que `privacy_erasures` en la 0034
    # (regla de oro 11).
    #
    # Tampoco se restaura `privacy_erase_subject(text,text)`: la firma de tres
    # argumentos hace lo mismo con `p_request => NULL`, y volver atrás dejaría
    # lápidas con `request_id` que ninguna función sabría ya escribir.
    pass
