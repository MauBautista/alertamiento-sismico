"""T-2.80 · ARCO por anonimización con tombstone.

El derecho de cancelación del titular y la obligación de conservar auditoría,
evidencia y dictámenes (regla de oro 11) parecen incompatibles. No lo son: el
derecho es sobre la PERSONA y la obligación es sobre el HECHO. Se anonimiza a la
persona sin borrar el hecho.

QUÉ IMPIDE FÍSICAMENTE BORRAR EN VEZ DE ANONIMIZAR
──────────────────────────────────────────────────
Un comentario no impide nada. Esta migración instala tres capas:

1. **Privilegio ausente.** ``REVOKE DELETE`` sobre las doce tablas protegidas.
   Ojo: el 0001 ejecuta ``GRANT ... ON ALL TABLES IN SCHEMA public`` DESPUÉS de
   aplicar ``db/schema.sql``, así que conceder de menos NO basta — hay que
   revocar, y el fallo solo se ve en base NUEVA (lección de la 0028, repetida en
   la 0030 y en la 0033).
2. **Privilegio por COLUMNA.** Sobre ``life_checkins`` la API pasa a tener
   exactamente ``UPDATE (geom)``. Reescribir `status` o `user_id` deja de ser
   una decisión del código y pasa a ser un error de permisos de PostgreSQL. El
   ``REVOKE UPDATE`` previo es obligatorio: un GRANT a nivel de tabla concede
   todas las columnas y el GRANT por columna no lo estrecha.
3. **Triggers, en plural y con los eventos SEPARADOS.** El DELETE se queda con
   ``forbid_update_delete()``, el guard canónico de auditoría/dictámenes/
   evidencia: **no hay excepción de ARCO para borrar**. El UPDATE pasa a
   ``life_checkin_arco_guard()``, que rechaza todo cambio que no sea "anular
   geom" comparando la fila entera con ``to_jsonb`` — así cubre también las
   columnas que se añadan mañana sin que nadie vuelva a tocar el trigger. Los
   dos cubren al DUEÑO de la tabla, que es justo a quien el privilegio no cubre.

POR QUÉ SE ANULA `geom` Y NO SE TOCA `user_id`
──────────────────────────────────────────────
``user_id`` es un `sub` de Cognito: un UUID opaco que solo es dato personal
mientras exista el mapeo en ``user_profiles``. ARCO destruye ese mapeo. Y el
`sub` **tiene que quedarse** porque ``COUNT(DISTINCT user_id)`` es "cuántas
PERSONAS confirmaron estar bien en esta zona": colapsarlo a un seudónimo común
hundiría ese número, y en un sismo ese número decide si sube o no una brigada.
Lo que sí muere es ``geom``, la ubicación GPS exacta de una persona, que el
conteo no necesita.

LA FIRMA DE `privacy_erase_subject(p_right, p_via)`
───────────────────────────────────────────────────
No recibe sujeto. Opera sobre ``app_user_id()``. Ejercer ARCO sobre un tercero
no está *prohibido*: es **inexpresable**, que es una garantía más fuerte que
cualquier comprobación. Cruzar tenants tampoco tiene parámetro por donde entrar.

INVARIANTES DEL PROYECTO
────────────────────────
Objetos NUEVOS ⇒ ``SET ROLE takab_migrator``; DDL sobre tablas PREEXISTENTES
(``life_checkins``) y triggers/GRANT/RLS/políticas ⇒ como usuario de conexión,
con ``RESET ROLE`` antes. Idempotente de principio a fin: ``IF NOT EXISTS``,
``DROP POLICY IF EXISTS`` antes de cada ``CREATE POLICY``, ``CREATE OR REPLACE
TRIGGER`` y la guarda ``to_regprocedure`` en las funciones (mismo criterio que la
0033: en base NUEVA ya vienen de ``db/schema.sql`` y recrearlas chocaría con el
dueño).

Revision ID: 0034_privacy_erasure
Revises: 0033_privacy_consent
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034_privacy_erasure"
down_revision: str | None = "0033_privacy_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Funciones. Guarda `to_regprocedure` (no `CREATE OR REPLACE`): en base NUEVA ya
# existen —las creó `db/schema.sql` dentro del 0001— y reemplazarlas desde otro
# rol fallaría por dueño. Cambiar un cuerpo es tarea de otra migración.
# ---------------------------------------------------------------------------

_FN_DIGEST = r"""
DO $do$
BEGIN
  IF to_regprocedure('privacy_audit_digest(uuid,bigint)') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION privacy_audit_digest(p_tenant uuid, p_watermark bigint)
        RETURNS text LANGUAGE sql STABLE AS $body$
        SELECT encode(sha256(convert_to(
          'takab.audit-chain.v1' || E'\n' ||
          coalesce(string_agg(linea, E'\n' ORDER BY audit_id), '(bitacora vacia)'),
          'UTF8')), 'hex')
        FROM (
          SELECT a.audit_id,
                 'i' || a.audit_id::text ||
                 '|t' || extract(epoch from a.ts)::text ||
                 '|n' || char_length(coalesce(a.tenant_id::text, '')) || ':'
                      || coalesce(a.tenant_id::text, '') ||
                 '|a' || char_length(a.actor)  || ':' || a.actor ||
                 '|v' || char_length(a.verb)   || ':' || a.verb ||
                 '|o' || char_length(a.object) || ':' || a.object ||
                 '|m' || char_length(a.meta::text) || ':' || a.meta::text AS linea
          FROM audit_log a
          WHERE a.tenant_id = p_tenant AND a.audit_id <= p_watermark
        ) s
        $body$
    $fn$;
    EXECUTE 'RESET ROLE';
  END IF;
END
$do$;
"""

_FN_GUARD = r"""
DO $do$
BEGIN
  IF to_regprocedure('life_checkin_arco_guard()') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION life_checkin_arco_guard() RETURNS trigger
        LANGUAGE plpgsql AS $body$
      BEGIN
        -- Red de seguridad: si alguien colgara esta funcion del evento DELETE en
        -- vez de forbid_update_delete(), el borrado seguiria sin pasar.
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'tabla append-only: % no permite %', TG_TABLE_NAME, TG_OP;
        END IF;
        -- Unica mutacion admitida: geom pasa de TENER VALOR a NULL, con el resto
        -- de la fila identica. Exigir la transicion real (y no solo que NEW.geom
        -- sea NULL) deja fuera el `UPDATE ... SET c = c`, que no cambia nada y no
        -- tiene por que aceptarse sobre evidencia. El texto conserva el de
        -- forbid_update_delete(): para todo lo que no sea ARCO, esta tabla ES
        -- append-only, y `ops/restore_check.py` reconoce la guarda por ese texto.
        IF NOT (OLD.geom IS NOT NULL AND NEW.geom IS NULL)
           OR (to_jsonb(NEW) - 'geom') IS DISTINCT FROM (to_jsonb(OLD) - 'geom') THEN
          RAISE EXCEPTION
            'tabla append-only: % no permite % (unica excepcion: anular geom, '
            'anonimizacion ARCO)', TG_TABLE_NAME, TG_OP;
        END IF;
        RETURN NEW;
      END $body$
    $fn$;
    EXECUTE 'RESET ROLE';
  END IF;
END
$do$;
"""

_FN_ERASE = r"""
DO $do$
BEGIN
  IF to_regprocedure('privacy_erase_subject(text,text)') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION privacy_erase_subject(p_right text, p_via text)
        RETURNS jsonb LANGUAGE plpgsql AS $body$
      DECLARE
        v_tenant  uuid := app_tenant_id();
        v_user    uuid := app_user_id();
        v_af      jsonb := '{}'::jsonb;
        v_n       integer;
        v_wm      bigint;
        v_row     privacy_erasures%ROWTYPE;
        v_created boolean := true;
      BEGIN
        IF v_tenant IS NULL OR v_user IS NULL THEN
          RAISE EXCEPTION
            'ARCO exige una sesion con titular identificado: el sujeto del borrado '
            'es siempre app_user_id(), nunca un parametro'
            USING ERRCODE = 'TK403';
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
          (tenant_id, user_sub, right_exercised, requested_by, via,
           affected, audit_watermark, audit_digest)
        VALUES
          (v_tenant, v_user, p_right, v_user, p_via,
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
# La lápida (objeto NUEVO ⇒ SET ROLE takab_migrator)
# ---------------------------------------------------------------------------

_TABLA = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS privacy_erasures (
  erasure_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(tenant_id),
  user_sub        uuid NOT NULL,
  right_exercised text NOT NULL CHECK (right_exercised IN ('cancelacion','oposicion')),
  requested_by    uuid NOT NULL,
  via             text NOT NULL CHECK (via IN ('mobile','web','console_admin','out_of_band')),
  affected        jsonb NOT NULL DEFAULT '{}',
  audit_watermark bigint NOT NULL,
  audit_digest    text NOT NULL CHECK (audit_digest ~ '^[0-9a-f]{64}$'),
  erased_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pe_afectados_son_conteos CHECK (
    NOT jsonb_path_exists(affected, '$.* ? (@.type() <> "number")')
  ),
  CONSTRAINT uq_privacy_erasures_sujeto UNIQUE (tenant_id, user_sub)
);

CREATE INDEX IF NOT EXISTS idx_privacy_erasures_tenant
  ON privacy_erasures (tenant_id, erased_at DESC);

RESET ROLE;
"""


# ---------------------------------------------------------------------------
# Triggers, privilegios y RLS (usuario de conexión, nunca takab_migrator)
# ---------------------------------------------------------------------------

_RESTO = """
CREATE OR REPLACE TRIGGER trg_privacy_erasures_append_only
  BEFORE UPDATE OR DELETE ON privacy_erasures
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

-- El trigger único de `life_checkins` se parte en DOS, con los eventos separados:
-- DELETE se queda con el guard CANÓNICO (`forbid_update_delete`, el mismo de
-- auditoría/dictámenes/evidencia: no hay excepción de ARCO para borrar) y UPDATE
-- pasa al guard de ARCO, que abre una sola rendija (geom → NULL).
--
-- Partirlos mantiene HONESTOS a los dos verificadores del proyecto:
-- `ops/restore_check.py` deriva de `db/schema.sql` qué tablas son append-only
-- buscando `BEFORE UPDATE OR DELETE`, y `tests/contracts/test_compliance_retention.py`
-- cuenta triggers cuya función es `forbid_update_delete`. Con un guard propio
-- sobre ambos eventos, los dos habrían leído "esta tabla dejó de estar
-- protegida" — falso, porque para DELETE lo sigue estando y por el guard de
-- siempre. DROP+CREATE y no `CREATE OR REPLACE`: aquí cambia el EVENTO, no solo
-- el cuerpo.
DROP TRIGGER IF EXISTS trg_life_checkins_append_only ON life_checkins;
DROP TRIGGER IF EXISTS trg_life_checkins_arco_guard  ON life_checkins;
CREATE TRIGGER trg_life_checkins_append_only
  BEFORE DELETE ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER trg_life_checkins_arco_guard
  BEFORE UPDATE ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION life_checkin_arco_guard();

GRANT SELECT, INSERT ON privacy_erasures TO takab_app;
REVOKE UPDATE, DELETE ON privacy_erasures FROM takab_app;
REVOKE ALL ON privacy_erasures FROM takab_ingest;

-- El REVOKE de UPDATE va ANTES y es obligatorio: un GRANT a nivel de tabla
-- concede todas las columnas, y el GRANT por columna no lo estrecha.
REVOKE UPDATE, DELETE ON life_checkins FROM takab_app;
GRANT UPDATE (geom) ON life_checkins TO takab_app;

-- Regla de oro 11 hecha privilegio. Ver la cabecera: sin esto una base NUEVA
-- acaba con DELETE concedido sobre auditoría, evidencia y dictámenes.
REVOKE DELETE ON
  audit_log, incident_actions, dictamens, evidence_objects, damage_reports,
  privacy_notices, privacy_consents, user_profiles, push_tokens, device_keys
FROM takab_app;

REVOKE ALL ON FUNCTION privacy_erase_subject(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION privacy_audit_digest(uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION privacy_erase_subject(text,text) TO takab_app;
GRANT EXECUTE ON FUNCTION privacy_audit_digest(uuid,bigint) TO takab_app;

ALTER TABLE privacy_erasures ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_erasures FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pe_self          ON privacy_erasures;
DROP POLICY IF EXISTS pe_admin_read    ON privacy_erasures;
DROP POLICY IF EXISTS pe_internal_read ON privacy_erasures;
DROP POLICY IF EXISTS lc_arco_geom     ON life_checkins;

-- Ejercer ARCO y consultar la propia lápida es acto del TITULAR, igual que dar
-- o retirar el consentimiento: un derecho, no un permiso que se concede.
CREATE POLICY pe_self ON privacy_erasures FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
-- El responsable del tenant LEE su registro de borrados (necesidad de
-- cumplimiento). Nunca escribe: nadie ejerce ARCO en nombre de otro.
CREATE POLICY pe_admin_read ON privacy_erasures FOR SELECT
  USING (tenant_id = app_tenant_id()
         AND app_role() IN ('tenant_admin','takab_superadmin'));
CREATE POLICY pe_internal_read ON privacy_erasures FOR SELECT
  USING (app_is_takab_internal());

-- El UPDATE del TITULAR sobre sus propias filas. Junto al GRANT por columna y al
-- trigger, la superficie que abre es: "el titular puede anular la geometría de sus
-- propios check-ins". Nada más.
-- [T-2.81] Decía "la ÚNICA política de UPDATE" y dejó de ser cierto en la 0035, que
-- añade la del job de retención. La política dice QUIÉN puede pedir el UPDATE; el
-- trigger sigue decidiendo QUÉ, y solo admite `geom → NULL`.
CREATE POLICY lc_arco_geom ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND user_id = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_id = app_user_id());
"""


def upgrade() -> None:
    op.execute(_FN_DIGEST)
    op.execute(_FN_GUARD)
    op.execute(_TABLA)
    # La función de borrado va DESPUÉS de la tabla: declara `privacy_erasures%ROWTYPE`.
    op.execute(_FN_ERASE)
    op.execute(_RESTO)


def downgrade() -> None:
    # Deliberadamente NO se borra `privacy_erasures`: es la constancia de que
    # alguien ejerció su derecho, y el sello que hace verificable la bitácora de
    # ese momento. Un downgrade que la destruyera dejaría al responsable sin
    # poder probar un borrado que sí ocurrió — mismo criterio que `audit_log`,
    # `privacy_consents` y `maintenance_windows` (regla de oro 11).
    #
    # Tampoco se reinstala `forbid_update_delete()` en `life_checkins`: el guard
    # de ARCO es MÁS restrictivo en DELETE (idéntico) y solo abre geom → NULL.
    # Volver atrás dejaría filas ya anonimizadas sin nada que ganar.
    pass
