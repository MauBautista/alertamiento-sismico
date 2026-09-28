"""T-9.30/T-9.31 · D-43 · quién firmó el dictamen y en qué banda

``dictamens.signed_by NOT NULL`` seguía significando «lo firmó el inspector». Con
D-43 firman tres: el inspector, una persona que CONFIRMA un AMARILLO y el SISTEMA
(un VERDE tras la gracia). ``signed_by`` conserva su sentido de «firmado» —así el
reingreso lo libera sin tocar su regla— y QUIÉN firmó pasa a una columna explícita:

* ``signature_kind`` ∈ {inspector, system, confirmation}; NULL en filas sin firma
  y en las HISTÓRICAS (no se inventa un firmante que no consta).
* ``band`` ∈ {verde, amarillo, rojo} de la regla ``dictamen-v2``; NULL en filas v1.
* La firma del sistema usa la identidad fija ``SYSTEM_DICTAMEN_SIGNER_UUID``
  (copia en código: ``takab_api/dictamen/sistema.py``; el test las ata). Un CHECK
  exige que esa identidad vaya SÓLO con ``signature_kind = 'system'`` y viceversa,
  también cuando ``signature_kind`` es NULL (``IS NOT DISTINCT FROM``).

Además el worker del dictamen (``takab_ingest``) pasa a LEER ``damage_reports``:
la 0018 la creó con GRANT sólo a ``takab_app`` y la 0001 da ``ALL TABLES`` sólo en
base NUEVA ⇒ en la nube el worker moriría con «permission denied».

Invariantes: idempotente (0002+); DDL bajo ``SET ROLE takab_migrator`` (dueño de
``dictamens``/``damage_reports``); espejo en ``db/schema.sql``; append-only intacto
(sólo ``ADD COLUMN``, ningún ``UPDATE``).

Revision ID: 0073_firma_y_banda_del_dictamen
Revises: 0072_roles_canonicos
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0073_firma_y_banda_del_dictamen"
down_revision: str | None = "0072_roles_canonicos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Copia CONGELADA de ``takab_api.dictamen.sistema.SYSTEM_DICTAMEN_SIGNER_UUID``.
SYSTEM_DICTAMEN_SIGNER_UUID = "00000000-0000-4000-8000-00000000d043"

#: [F3·r3] La VERSIÓN de ``ck_dictamens_firmante`` (NULL-segura, dos direcciones),
#: escrita como COMMENT de la restricción. Espejo literal en ``db/schema.sql``.
MARCA_FIRMANTE = "ck_dictamens_firmante v2 · NULL-segura · F3"

_COLUMNAS = """
SET ROLE takab_migrator;
ALTER TABLE dictamens ADD COLUMN IF NOT EXISTS signature_kind text;
ALTER TABLE dictamens ADD COLUMN IF NOT EXISTS band text;
RESET ROLE;
"""

_CHECKS = f"""
SET ROLE takab_migrator;
DO $ck$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'dictamens'::regclass
                    AND conname = 'ck_dictamens_signature_kind') THEN
    ALTER TABLE dictamens ADD CONSTRAINT ck_dictamens_signature_kind
      CHECK (signature_kind IN ('inspector','system','confirmation'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'dictamens'::regclass
                    AND conname = 'ck_dictamens_band') THEN
    ALTER TABLE dictamens ADD CONSTRAINT ck_dictamens_band
      CHECK (band IN ('verde','amarillo','rojo'));
  END IF;
  -- [F3·r2] Una base que corrió la 0073 PRIMERA (sin la dirección NULL-segura)
  -- tiene la restricción con el mismo nombre y otra definición: se sustituye.
  -- [F3·r3] La versión se reconoce por su COMMENT, no por el texto deparseado:
  -- Postgres escribe `IS NOT DISTINCT FROM` como `NOT (x IS DISTINCT FROM y)`, así
  -- que buscarlo en `pg_get_constraintdef` fallaba SIEMPRE y cada corrida hacía DROP
  -- + ADD (ACCESS EXCLUSIVE y revalidar la tabla entera). Con la marca, la 2ª
  -- corrida es un no-op.
  IF EXISTS (SELECT 1 FROM pg_constraint
              WHERE conrelid = 'dictamens'::regclass
                AND conname = 'ck_dictamens_firmante'
                AND obj_description(oid, 'pg_constraint')
                      IS DISTINCT FROM '{MARCA_FIRMANTE}') THEN
    ALTER TABLE dictamens DROP CONSTRAINT ck_dictamens_firmante;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'dictamens'::regclass
                    AND conname = 'ck_dictamens_firmante') THEN
    -- Las DOS direcciones, también con `signature_kind` NULL: la identidad del
    -- sistema ⇔ `signature_kind = 'system'`; y un tipo de firma exige firmante.
    ALTER TABLE dictamens ADD CONSTRAINT ck_dictamens_firmante
      CHECK ((signature_kind IS NULL OR signed_by IS NOT NULL)
             AND (signature_kind IS NOT DISTINCT FROM 'system')
               = (signed_by IS NOT DISTINCT FROM '{SYSTEM_DICTAMEN_SIGNER_UUID}'::uuid));
    COMMENT ON CONSTRAINT ck_dictamens_firmante ON dictamens IS '{MARCA_FIRMANTE}';
  END IF;
END $ck$;
RESET ROLE;
"""

_COMENTARIOS = f"""
SET ROLE takab_migrator;
COMMENT ON COLUMN dictamens.signature_kind IS
  '[T-9.31 · D-43] Quién firmó: inspector, system (VERDE tras la gracia, '
  'signed_by = {SYSTEM_DICTAMEN_SIGNER_UUID}) o confirmation (brigada/inspector '
  'confirman un AMARILLO). NULL = sin firma o fila histórica anterior a la 0073.';
COMMENT ON COLUMN dictamens.band IS
  '[T-9.30 · D-43] Banda de la regla dictamen-v2 (verde/amarillo/rojo). NULL = fila v1.';
RESET ROLE;
"""

_GRANT = """
SET ROLE takab_migrator;
GRANT SELECT ON damage_reports TO takab_ingest;
RESET ROLE;
"""

#: En orden; el test los re-ejecuta para medir la idempotencia.
BLOQUES: tuple[str, ...] = (_COLUMNAS, _CHECKS, _COMENTARIOS, _GRANT)


def upgrade() -> None:
    for sql in BLOQUES:
        op.execute(sql)


def downgrade() -> None:
    op.execute(
        """
SET ROLE takab_migrator;
ALTER TABLE dictamens DROP CONSTRAINT IF EXISTS ck_dictamens_firmante;
ALTER TABLE dictamens DROP CONSTRAINT IF EXISTS ck_dictamens_band;
ALTER TABLE dictamens DROP CONSTRAINT IF EXISTS ck_dictamens_signature_kind;
ALTER TABLE dictamens DROP COLUMN IF EXISTS band;
ALTER TABLE dictamens DROP COLUMN IF EXISTS signature_kind;
RESET ROLE;
"""
    )
