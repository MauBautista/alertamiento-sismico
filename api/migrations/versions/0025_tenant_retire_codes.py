"""T-2.36 · Código de retiro por tenant (segundo factor para apagar una estación).

Retirar un gabinete deja un edificio sin protección: el worker de config firmada
(``commands/sync.py``) y el emisor de comandos (``queries/commands.py``) lo excluyen
de inmediato. Un clic en la consola no es fricción suficiente, así que el retiro pasa
a exigir un código que TAKAB entrega fuera de banda y solo el superadmin rota.

El hash NUNCA sale de Postgres:
- ``pgcrypto`` (ya instalada, ``db/schema.sql``) calcula ``crypt(code, gen_salt('bf',12))``
  — bcrypt, coste 12. Cero dependencias nuevas en ``api/pyproject.toml``.
- La verificación entra por ``app_verify_retire_code``, ``SECURITY DEFINER`` con
  ``search_path`` fijado (patrón de ``app_can_view_meta``, 0017). La API pregunta
  "¿coincide?" y recibe un booleano; nunca lee el hash.
- No hay política de lectura para roles de tenant: ni el ``tenant_admin`` que usa el
  código puede leer su propio hash. Solo el superadmin (``trc_admin``) toca la fila.

Tabla NUEVA ⇒ ``SET ROLE takab_migrator`` (patrón de dueños del proyecto).
Idempotente (invariante T-1.45).

Revision ID: 0025_tenant_retire_codes
Revises: 0024_retire_ghost_gateways
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_tenant_retire_codes"
down_revision: str | None = "0024_retire_ghost_gateways"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS tenant_retire_codes (
  tenant_id  uuid PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  code_hash  text NOT NULL,
  version    integer NOT NULL DEFAULT 1,
  rotated_by uuid NOT NULL,
  rotated_at timestamptz NOT NULL DEFAULT now()
);

-- takab_app necesita escribir (rotación) pero NO leer: el SELECT lo hacen las
-- funciones SECURITY DEFINER de abajo, que corren como el dueño.
GRANT SELECT, INSERT, UPDATE ON tenant_retire_codes TO takab_app;

-- ENABLE sin FORCE, a diferencia del resto de tablas del esquema, y a propósito:
-- FORCE sujeta también al DUEÑO, y el dueño es justo quien tiene que poder leer el
-- hash desde las funciones SECURITY DEFINER de abajo (SECURITY DEFINER cambia el
-- USUARIO, no los GUC: `app_role()` seguiría siendo 'tenant_admin' y la política
-- devolvería 0 filas, con lo que verificar el código sería imposible).
-- La propiedad que importa se conserva intacta: `takab_app` —el rol con el que se
-- conecta la API— NO es dueño, así que sí queda sujeto a RLS, y no hay ninguna
-- política que le permita leer. El único rol que conecta como dueño es
-- `takab_migrator`, y solo corre Alembic.
ALTER TABLE tenant_retire_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_retire_codes NO FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS trc_admin ON tenant_retire_codes;
CREATE POLICY trc_admin ON tenant_retire_codes FOR ALL
  USING (app_role() = 'takab_superadmin') WITH CHECK (app_role() = 'takab_superadmin');

-- ¿El candidato coincide? Devuelve un booleano y nada más: el hash no cruza la
-- frontera de la base. STABLE + search_path fijado (SECURITY DEFINER sin
-- search_path es una escalada de privilegios esperando a ocurrir).
CREATE OR REPLACE FUNCTION app_verify_retire_code(t uuid, candidate text)
  RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM tenant_retire_codes c
     WHERE c.tenant_id = t AND c.code_hash = crypt(candidate, c.code_hash)
  )
$$;

-- Metadatos publicables (¿hay código? ¿de cuándo?) sin exponer el hash.
CREATE OR REPLACE FUNCTION app_retire_code_state(t uuid)
  RETURNS TABLE (version integer, rotated_at timestamptz)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT c.version, c.rotated_at FROM tenant_retire_codes c WHERE c.tenant_id = t
$$;

REVOKE ALL ON FUNCTION app_verify_retire_code(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_retire_code_state(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_verify_retire_code(uuid, text) TO takab_app;
GRANT EXECUTE ON FUNCTION app_retire_code_state(uuid) TO takab_app;

RESET ROLE;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Material de seguridad: un downgrade no borra credenciales de los clientes.
    # Mismo criterio que 0021/0022/0023.
    pass
