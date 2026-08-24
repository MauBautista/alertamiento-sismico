"""T-2.164 · El `CHECK` de `privacy_consents` deja de admitir el teléfono en claro.

`T-2.150` selló el sujeto: las filas nuevas guardan un **índice** de 64 hex y
nunca el número. Pero el `CHECK` siguió aceptando **las dos formas** «de manera
PERMANENTE, no transitoria», porque las filas anteriores llevaban el número en
claro y la tabla es append-only por trigger.

## POR QUÉ SE APRIETA AHORA, Y POR QUÉ ANTES NO SE PODÍA

Mientras el `CHECK` acepta las dos formas, **la ausencia de filas viejas no se
puede distinguir de que nadie las haya mirado**. Eso es lo que esta migración
cambia: a partir de aquí la base garantiza el invariante en vez de confiar en él.

Se puede apretar porque se CONTÓ, no porque se supusiera (2026-08-24):

| Entorno | consentimientos | `msisdn` en claro | `msisdn` sellados |
|---|---|---|---|
| local `takab` | 0 | **0** | 0 |
| local `takab_test` | 0 | **0** | 0 |
| nube dev (`takab-dev-db`) | 2 | **0** | 0 |

Los dos de la nube son de sujeto `user`. **No existe ni una fila con el número en
claro en ningún entorno**, así que la rama `+E164` del `CHECK` cubría un caso
hipotético — y al cubrirlo, tapaba la pregunta.

## Y NINGÚN CAMINO DE CÓDIGO PUEDE CREARLAS

`privacy/store.py` sella el sujeto ANTES de insertar y su comentario es
explícito: *«Si los secretos del despliegue no están, esto LANZA — y es lo
correcto: caer a texto en claro escribiría el defecto que la ficha cierra, en
silencio y PARA SIEMPRE, en una tabla que no se puede reescribir.»* O sea que el
`CHECK` apretado no cierra ninguna puerta que el código use: cierra una que
nadie podía abrir y que, existiendo, hacía indistinguible el «no hay» del «no se
miró».

**La lectura sigue tolerando la forma vieja** y eso no cambia:
`store._formas()` busca por índice y por número en claro. Si algún día apareciera
una fila así en un entorno que nadie censó, se seguiría encontrando — lo que no
se podrá es escribir una nueva.

## EL PRE-CHECK NO ES DECORACIÓN

`ADD CONSTRAINT` ya valida las filas existentes, así que la migración fallaría
sola. Pero el error de PostgreSQL dice «check constraint violated» y nombra UNA
fila: no dice *cuántas* hay ni que lo que hace falta es una decisión (¿se sellan
retroactivamente, a costa del append-only, o se declaran intocables?). El `DO`
de abajo cuenta y lo dice, que es lo que un operador necesita a las 3 de la
mañana.

Revision ID: 0051_consent_solo_sellado
Revises: 0050_site_ground_refs_tenant
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_consent_solo_sellado"
down_revision: str | None = "0050_site_ground_refs_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = r"""
DO $$
DECLARE en_claro bigint;
BEGIN
  SELECT count(*) INTO en_claro
    FROM privacy_consents
   WHERE subject_kind = 'msisdn' AND subject_ref ~ '^\+[1-9][0-9]{7,14}$';
  IF en_claro > 0 THEN
    RAISE EXCEPTION 'hay % consentimientos con el teléfono EN CLARO en subject_ref. '
                    'Apretar el CHECK los dejaría fuera, y esta tabla es append-only: '
                    'antes hay que DECIDIR si se sellan retroactivamente (y a costa de qué '
                    'propiedad de la tabla) o si se declaran intocables con su justificación '
                    'legal. Ver T-2.164.', en_claro;
  END IF;
END $$;

ALTER TABLE privacy_consents DROP CONSTRAINT IF EXISTS pc_sujeto_coherente;
ALTER TABLE privacy_consents ADD CONSTRAINT pc_sujeto_coherente CHECK (
  (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
  (subject_kind = 'msisdn' AND user_sub IS     NULL AND subject_ref ~ '^[0-9a-f]{64}$')
);
"""

# El downgrade vuelve a admitir las dos formas. No reescribe ninguna fila: sólo
# relaja el invariante, que es lo que un downgrade puede hacer sin inventarse
# datos.
_DOWN = r"""
ALTER TABLE privacy_consents DROP CONSTRAINT IF EXISTS pc_sujeto_coherente;
ALTER TABLE privacy_consents ADD CONSTRAINT pc_sujeto_coherente CHECK (
  (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
  (subject_kind = 'msisdn' AND user_sub IS     NULL AND (
      subject_ref ~ '^[0-9a-f]{64}$'
      OR subject_ref ~ '^\+[1-9][0-9]{7,14}$'
  ))
);
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
