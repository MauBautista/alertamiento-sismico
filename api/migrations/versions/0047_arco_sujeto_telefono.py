"""T-2.151 · La lápida y la constancia admiten un sujeto que no tiene `sub` (D-23).

`store.forget_msisdn()` sabía destruir el número desde `T-2.150`, pero el flujo
ARCO entero está tecleado por `user_sub`: la constancia lo exige `NOT NULL` con un
FK compuesto contra `user_profiles`, y la lápida igual. Un titular que solo dio su
teléfono **no tiene fila en el padrón**, así que no había forma de registrar ni de
acreditar su borrado — y sin lápida, «se ejecutó» y «se dijo que se ejecutó» son
indistinguibles.

──────────────────────────────────────────────────────────────────────────────
1 · QUIÉN ACREDITA — `D-23`
──────────────────────────────────────────────────────────────────────────────
El cliente institucional que recogió el consentimiento. TAKAB ejecuta y audita;
no verifica identidades por su cuenta ni custodia documentos. En la base eso es
el responsable del tratamiento (`tenant_admin` / `takab_superadmin`) y nadie más,
y con la prueba del escrito — la política `pe_phone_on_behalf` exige constancia
igual que hace `pe_on_behalf` con los sujetos del padrón: **el criterio no
depende del router, depende de la base**.

──────────────────────────────────────────────────────────────────────────────
2 · LO QUE NO SE GUARDA, Y POR QUÉ ES LA MITAD DE LA TAREA
──────────────────────────────────────────────────────────────────────────────
Ni el número ni su índice quedan en ninguna de las dos tablas. El índice
—`HMAC(pimienta, tenant‖msisdn)`— es **determinista**: quien lo tenga puede
comprobar cualquier número candidato. Y estas dos tablas son **append-only por
trigger**, así que lo que caiga en ellas no se puede quitar jamás: guardarlo
sería dejar sobreviviendo al borrado justo el artefacto que permite deshacerlo.

De ahí sale la única diferencia de forma con el ARCO por escrito de `T-2.80.b`,
que separa *registrar* de *ejecutar* en dos endpoints: **para ejecutar hay que
tener el número delante**, así que registrar hoy y ejecutar la semana que viene
obligaría a persistir su índice. Los dos actos se funden en una transacción y el
número entra por el cuerpo, se usa y no se escribe.

Las dos fechas no se pierden: `received_at` sale del escrito (lo pone el cliente)
y `erased_at` lo pone la base, así que el plazo legal sigue corriendo desde que
el cliente recibió la solicitud y no desde que TAKAB la ejecutó.

──────────────────────────────────────────────────────────────────────────────
3 · `affected` ES CONSTANTE, Y NO POR PEREZA
──────────────────────────────────────────────────────────────────────────────
En el ARCO del padrón, `affected` son conteos por tabla y son útiles. Aquí un
`{"privacy_subject_secrets": 1}` frente a un `0` **sería un oráculo de
existencia**: con una credencial de responsable se barre un rango de números y se
descubre cuáles constan — y con ellos, en qué edificio está quien los lleva. La
respuesta y la fila son idénticas exista el número o no.

──────────────────────────────────────────────────────────────────────────────
4 · IDEMPOTENCIA: LA UNIDAD ES LA CONSTANCIA, NO EL SUJETO
──────────────────────────────────────────────────────────────────────────────
`uq_privacy_erasures_sujeto` garantiza que un titular del padrón se anonimiza una
vez. Aquí no puede aplicarse, porque **el sujeto es exactamente lo que nos negamos
a registrar**. La unidad pasa a ser el documento: una constancia, una lápida
(`uq_privacy_erasures_constancia`). Dos escritos sobre el mismo número producen
dos actos, que es lo que de verdad ocurrió.

`UNIQUE (tenant_id, user_sub)` sigue en pie y no estorba: en SQL varios NULL no
colisionan entre sí.

──────────────────────────────────────────────────────────────────────────────
5 · IDEMPOTENCIA Y DUEÑOS (los dos invariantes de la casa)
──────────────────────────────────────────────────────────────────────────────
Las dos tablas son PREEXISTENTES: sus `ALTER` corren como el usuario de conexión,
sin `SET ROLE`. La función y la política son objetos nuevos sobre esas tablas —
van con el mismo dueño que ya las gobierna, que es quien puede definirlas.

Revision ID: 0047_arco_sujeto_telefono
Revises: 0046_privacy_subject_sealing
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0047_arco_sujeto_telefono"
down_revision: str | None = "0046_privacy_subject_sealing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UP = """
-- ---------------------------------------------------------------- constancia
ALTER TABLE privacy_erasure_requests ALTER COLUMN user_sub DROP NOT NULL;
ALTER TABLE privacy_erasure_requests
  ADD COLUMN IF NOT EXISTS subject_kind text NOT NULL DEFAULT 'user_sub';

ALTER TABLE privacy_erasure_requests DROP CONSTRAINT IF EXISTS per_subject_kind;
ALTER TABLE privacy_erasure_requests ADD CONSTRAINT per_subject_kind
  CHECK (subject_kind IN ('user_sub','msisdn'));

-- El sujeto y su forma cuentan la misma historia. Sin esto, una constancia
-- podria declararse 'msisdn' y llevar un `user_sub`, o al reves: la fila
-- mentiria sobre a quien nombra y el FK compuesto dejaria de significar nada.
ALTER TABLE privacy_erasure_requests DROP CONSTRAINT IF EXISTS per_sujeto_coherente;
ALTER TABLE privacy_erasure_requests ADD CONSTRAINT per_sujeto_coherente
  CHECK ((subject_kind = 'user_sub') = (user_sub IS NOT NULL));

-- ------------------------------------------------------------------- lapida
ALTER TABLE privacy_erasures ALTER COLUMN user_sub DROP NOT NULL;
ALTER TABLE privacy_erasures
  ADD COLUMN IF NOT EXISTS subject_kind text NOT NULL DEFAULT 'user_sub';

ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_subject_kind;
ALTER TABLE privacy_erasures ADD CONSTRAINT pe_subject_kind
  CHECK (subject_kind IN ('user_sub','msisdn'));

ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_sujeto_coherente;
ALTER TABLE privacy_erasures ADD CONSTRAINT pe_sujeto_coherente
  CHECK ((subject_kind = 'user_sub') = (user_sub IS NOT NULL));

-- No hay autoservicio para un sujeto-telefono, y no es una omision: el
-- autoservicio se apoya en `app_user_id()`, y quien solo dio su numero no tiene
-- sesion con la que probar que es suyo. Su unica via es la constancia del
-- responsable (D-23), asi que una lapida de telefono SIN constancia seria una
-- que nadie autorizo.
ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_telefono_exige_constancia;
ALTER TABLE privacy_erasures ADD CONSTRAINT pe_telefono_exige_constancia
  CHECK (subject_kind <> 'msisdn' OR request_id IS NOT NULL);

-- Una constancia, una lapida. Ver la cabecera, seccion 4.
CREATE UNIQUE INDEX IF NOT EXISTS uq_privacy_erasures_constancia
  ON privacy_erasures (tenant_id, request_id) WHERE subject_kind = 'msisdn';

-- ---------------------------------------------------------------------- RLS
-- El gemelo de `pe_on_behalf` para el sujeto que no esta en el padron. No puede
-- reutilizar `app_can_erase_subject`, que busca la constancia POR `user_sub`:
-- con un sujeto nulo esa comparacion no encuentra nada y la insercion caeria.
-- La constancia se exige igual, pero por `request_id`.
DROP POLICY IF EXISTS pe_phone_on_behalf ON privacy_erasures;
CREATE POLICY pe_phone_on_behalf ON privacy_erasures FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND subject_kind = 'msisdn'
              AND user_sub IS NULL
              AND request_id IS NOT NULL
              AND app_role() IN ('tenant_admin','takab_superadmin')
              AND EXISTS (
                    SELECT 1 FROM privacy_erasure_requests r
                     WHERE r.request_id = privacy_erasures.request_id
                       AND r.tenant_id  = privacy_erasures.tenant_id
                       AND r.subject_kind = 'msisdn'));

-- --------------------------------------------------------------------- acto
-- Registrar y ejecutar, en UNA sentencia. Un borrado a medias —constancia sin
-- lapida, o lapida sin el sello destruido— no es un estado alcanzable.
--
-- **No recibe el numero ni su indice.** El sello lo destruye el llamador antes,
-- porque hace falta la pimienta del despliegue y esa no esta en esta base; aqui
-- solo se registra el acto. Si esta insercion falla, la transaccion entera se
-- deshace y el sello vuelve: por eso el orden es destruir-y-luego-registrar y no
-- al reves.
CREATE OR REPLACE FUNCTION privacy_erase_phone_subject(
  p_right text, p_channel text, p_received_at timestamptz,
  p_proof_ref text, p_proof_digest text, p_via text)
  RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  v_tenant  uuid := app_tenant_id();
  v_actor   uuid := app_user_id();
  v_request uuid;
  v_wm      bigint;
  v_row     privacy_erasures%ROWTYPE;
BEGIN
  IF v_tenant IS NULL OR v_actor IS NULL THEN
    RAISE EXCEPTION
      'ARCO exige una sesion con portador identificado: quien ejecuta el borrado '
      'de un sujeto-telefono es el responsable del tratamiento, nunca un anonimo'
      USING ERRCODE = 'TK403';
  END IF;

  INSERT INTO privacy_erasure_requests
    (user_sub, subject_kind, right_requested, channel, received_at,
     proof_ref, proof_digest, created_by)
  VALUES
    (NULL, 'msisdn', p_right, p_channel, p_received_at,
     p_proof_ref, p_proof_digest, v_actor)
  RETURNING request_id INTO v_request;

  SELECT coalesce(max(audit_id), 0) INTO v_wm FROM audit_log WHERE tenant_id = v_tenant;

  INSERT INTO privacy_erasures
    (tenant_id, user_sub, subject_kind, right_exercised, requested_by, request_id,
     via, affected, audit_watermark, audit_digest)
  VALUES
    (v_tenant, NULL, 'msisdn', p_right, v_actor, v_request,
     -- `affected` CONSTANTE: un conteo aqui seria un oraculo de existencia.
     p_via, '{}'::jsonb, v_wm, privacy_audit_digest(v_tenant, v_wm))
  RETURNING * INTO v_row;

  RETURN to_jsonb(v_row);
END $$;

GRANT EXECUTE ON FUNCTION privacy_erase_phone_subject(
  text, text, timestamptz, text, text, text) TO takab_app;
"""

_DOWN = """
DROP FUNCTION IF EXISTS privacy_erase_phone_subject(
  text, text, timestamptz, text, text, text);
DROP POLICY IF EXISTS pe_phone_on_behalf ON privacy_erasures;
DROP INDEX IF EXISTS uq_privacy_erasures_constancia;

DELETE FROM privacy_erasures         WHERE subject_kind = 'msisdn';
DELETE FROM privacy_erasure_requests WHERE subject_kind = 'msisdn';

ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_telefono_exige_constancia;
ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_sujeto_coherente;
ALTER TABLE privacy_erasures DROP CONSTRAINT IF EXISTS pe_subject_kind;
ALTER TABLE privacy_erasures DROP COLUMN IF EXISTS subject_kind;
ALTER TABLE privacy_erasures ALTER COLUMN user_sub SET NOT NULL;

ALTER TABLE privacy_erasure_requests DROP CONSTRAINT IF EXISTS per_sujeto_coherente;
ALTER TABLE privacy_erasure_requests DROP CONSTRAINT IF EXISTS per_subject_kind;
ALTER TABLE privacy_erasure_requests DROP COLUMN IF EXISTS subject_kind;
ALTER TABLE privacy_erasure_requests ALTER COLUMN user_sub SET NOT NULL;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
