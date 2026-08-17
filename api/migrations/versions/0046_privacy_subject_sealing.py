"""T-2.150 · El teléfono del consentimiento deja de estar en claro (D-07).

`privacy_consents.subject_ref` guardaba el `msisdn` **en claro** en una tabla
**append-only por trigger**. ARCO no lo alcanzaba: anonimizarlo exigía abrir un
hueco en el guard, y el valor entero de esa tabla es que no los tiene.

`D-07` eligió no elegir entre los dos bienes. Esta migración pone las dos piezas:

──────────────────────────────────────────────────────────────────────────────
1 · `privacy_subject_secrets` — LA TABLA QUE SÍ SE PUEDE BORRAR
──────────────────────────────────────────────────────────────────────────────
Aquí vive el número, sellado con AES-GCM bajo una clave que NO está en la base.
Es **mutable a propósito**, y esa es la idea entera: ejercer ARCO borra una fila
de ESTA tabla y **no toca `privacy_consents`**. El consentimiento queda byte a
byte intacto —su digest sigue probando— y lo que desaparece es la capacidad de
leer a quién.

Sin trigger append-only, sin exención de poda. Es lo contrario de la evidencia:
aquí el objetivo es **poder borrar**.

──────────────────────────────────────────────────────────────────────────────
2 · EL `CHECK` DEL SUJETO ADMITE AHORA LAS DOS FORMAS, Y NO ES PROVISIONAL
──────────────────────────────────────────────────────────────────────────────
`pc_sujeto_coherente` exigía que un sujeto `msisdn` tuviera `subject_ref` con
forma de teléfono. Desde hoy las filas nuevas llevan el ÍNDICE (64 hex).

**Las viejas se quedan como están, y no por descuido: NO SE PUEDEN MIGRAR.** La
tabla es append-only por trigger — no hay `UPDATE` que valga—, y desactivar ese
trigger para reescribirlas sería abrir exactamente el hueco que `D-07` existe
para no abrir. Así que el `CHECK` acepta las dos formas de forma permanente.

> **Y de ahí sale un hecho que conviene mirar de frente:** este mecanismo **no
> protege hacia atrás**. Cada teléfono ya escrito en claro se queda en claro para
> siempre. La única variable que queda es **cuántos más se escriben antes de que
> esto entre en producción** — o sea que la fecha de despliegue es, literalmente,
> la línea que separa los números recuperables de los que no.

──────────────────────────────────────────────────────────────────────────────
3 · IDEMPOTENCIA Y DUEÑOS (los dos invariantes de la casa)
──────────────────────────────────────────────────────────────────────────────
`privacy_subject_secrets` es una tabla **NUEVA**, así que su creación va con
`SET ROLE takab_migrator` —es un objeto con dueño propio— y con sus `GRANT`
explícitos. `privacy_consents` es **PREEXISTENTE**, así que el cambio de `CHECK`
corre como el usuario de conexión, sin `SET ROLE`.

Los `GRANT` son deliberadamente asimétricos:
  · `takab_app` — SELECT/INSERT/DELETE. Escribe al consentir y borra al ejercer
    ARCO. **Sin UPDATE**: un sello no se edita, se crea o se destruye.
  · `takab_ingest` — SELECT y nada más. El worker de notificaciones necesita
    resolver el número para enviar; escribir un consentimiento jamás es cosa de
    un worker (mismo criterio que ya rige sobre `privacy_consents`).

Revision ID: 0046_privacy_subject_sealing
Revises: 0045_catalog_last_checked

NOTA DEL NOMBRE DEL FICHERO: se llama `_sealing` y no `_secrets` porque el
`.gitignore` del repo tiene `*secrets*` y **se tragaba este fichero en silencio** —
una migración que existe en local, pasa los tests contra una base que ya la tiene
aplicada, y NUNCA llega al repositorio. La tabla sigue llamándose
`privacy_subject_secrets`; lo que cambia es el nombre del archivo.
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0046_privacy_subject_sealing"
down_revision: str | None = "0045_catalog_last_checked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS privacy_subject_secrets (
  tenant_id     uuid NOT NULL REFERENCES tenants,
  -- El MISMO valor que `privacy_consents.subject_ref` de las filas nuevas: el
  -- HMAC del (tenant, msisdn). Es la única forma de llegar aquí desde un
  -- consentimiento sin que el consentimiento guarde el número.
  lookup_ref    text NOT NULL CHECK (lookup_ref ~ '^[0-9a-f]{64}$'),
  -- Nonce (12 B) + criptograma AES-GCM. La clave NO está en esta base.
  sealed        bytea NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lookup_ref)
);

GRANT SELECT, INSERT, DELETE ON privacy_subject_secrets TO takab_app;
GRANT SELECT                  ON privacy_subject_secrets TO takab_ingest;

ALTER TABLE privacy_subject_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_subject_secrets FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS privacy_subject_secrets_rw ON privacy_subject_secrets;
CREATE POLICY privacy_subject_secrets_rw ON privacy_subject_secrets FOR ALL
  USING      (tenant_id = app_tenant_id() OR app_is_takab_internal())
  WITH CHECK (tenant_id = app_tenant_id() OR app_is_takab_internal());

RESET ROLE;

-- `privacy_consents` es PREEXISTENTE: sin SET ROLE.
ALTER TABLE privacy_consents DROP CONSTRAINT IF EXISTS pc_sujeto_coherente;
ALTER TABLE privacy_consents ADD CONSTRAINT pc_sujeto_coherente CHECK (
  (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
  (subject_kind = 'msisdn' AND user_sub IS     NULL AND (
      -- Forma NUEVA: el índice de búsqueda (T-2.150).
      subject_ref ~ '^[0-9a-f]{64}$'
      -- Forma VIEJA: el número en claro. Permanente, no transitoria: la tabla es
      -- append-only y estas filas NO SE PUEDEN reescribir.
      OR subject_ref ~ '^\\+[1-9][0-9]{7,14}$'
  ))
);
"""

_DOWN = """
ALTER TABLE privacy_consents DROP CONSTRAINT IF EXISTS pc_sujeto_coherente;
ALTER TABLE privacy_consents ADD CONSTRAINT pc_sujeto_coherente CHECK (
  (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
  (subject_kind = 'msisdn' AND user_sub IS     NULL AND subject_ref ~ '^\\+[1-9][0-9]{7,14}$')
);

DROP TABLE IF EXISTS privacy_subject_secrets;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
