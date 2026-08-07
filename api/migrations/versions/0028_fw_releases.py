"""T-2.69 · Registro de releases de firmware: contra QUÉ se mide la deriva.

Hoy `gateways.fw_version` guarda lo que el gabinete declara en cada latido, y eso
basta para decir *qué* corre. No basta para decir *si eso es lo actual*, porque
`deploy/edge/deploy.sh` escribe ``git describe --always --dirty --abbrev=7`` sobre
un repo **sin tags**: el valor es siempre un SHA de 7 hex (a veces con sufijo
``-dirty``). No es semver, no es monótono, **no es ordenable** — la única relación
decidible entre dos valores es la IGUALDAD. Y el contenedor de la API no tiene el
repo git, así que tampoco puede contar commits entre dos SHAs.

Sin este registro, "cuántos releases atrás y cuánto tiempo" NO TIENE RESPUESTA
HONESTA, y "el gabinete corre una versión que nadie publicó" es INDETECTABLE.
Con él, ambas se derivan: el orden lo da ``released_at`` (con ``seq`` de
desempate) y la ausencia de una versión en la tabla deja de ser un vacío para
convertirse en una CONTRADICCIÓN que la consola puede gritar.

**De plataforma, no de tenant** — excepción documentada a "tenant_id en toda
tabla", misma familia que ``reference_earthquakes``: qué firmware existe lo decide
TAKAB, no el cliente. Lectura para cualquier rol autenticado (cada tenant sigue
viendo SOLO la deriva de SUS gabinetes, porque esa la acota la RLS de
``gateways``); escritura solo ``takab_superadmin``.

**Append-only por privilegio**: se concede ``SELECT, INSERT`` y NO
``UPDATE/DELETE``. Reescribir la fecha de un release reescribiría a posteriori la
deriva de toda la flota — el "cuánto lleva corriendo código viejo" dejaría de ser
comprobable. No lleva el trigger ``forbid_update_delete`` porque eso está
reservado a evidencia/compliance (regla de oro 11); aquí basta con no dar el
privilegio.

Tabla NUEVA ⇒ ``SET ROLE takab_migrator`` (patrón de dueños del proyecto).
Idempotente (invariante T-1.45).

Revision ID: 0028_fw_releases
Revises: 0027_gateway_status_notify
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028_fw_releases"
down_revision: str | None = "0027_gateway_status_notify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS fw_releases (
  release_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- UNIQUE: publicar dos veces el mismo SHA no crea dos releases (la API
  -- devuelve 409). El límite de 64 es el MISMO de la ingesta
  -- (`ingest/handlers.py::_FW_VERSION_MAX_LEN`): una versión que no cabe en la
  -- ficha del gabinete tampoco puede figurar aquí, o el registro contendría
  -- objetivos inalcanzables.
  version      text NOT NULL UNIQUE CHECK (length(version) BETWEEN 1 AND 64),
  released_at  timestamptz NOT NULL DEFAULT now(),
  -- Desempate ESTABLE cuando dos releases comparten `released_at` (backfill,
  -- reloj con poca resolución). Sin él, el orden de dos filas empatadas
  -- dependería del plan de ejecución y "cuántos atrás" cambiaría entre recargas.
  seq          bigint GENERATED ALWAYS AS IDENTITY,
  notes        text,
  published_by text
);

CREATE INDEX IF NOT EXISTS idx_fw_releases_order
  ON fw_releases (released_at DESC, seq DESC);

-- Sin UPDATE ni DELETE: append-only por privilegio (ver cabecera).
GRANT SELECT, INSERT ON fw_releases TO takab_app;

-- …y REVOKE explícito, porque conceder de menos NO basta en una base nueva.
--
-- [T-2.70] Defecto encontrado al correr la suite completa contra una base recién
-- creada. La migración 0001 aplica `db/schema.sql` —que YA crea `fw_releases`— y
-- DESPUÉS ejecuta `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA
-- public TO takab_app`. Ese blanket grant alcanza a esta tabla y le devuelve
-- UPDATE/DELETE, así que la garantía «append-only por privilegio» se cumplía en
-- una base migrada de forma incremental (donde la tabla nace después del 0001) y
-- NO se cumplía en una base nueva — que es justo lo que provisiona un despliegue
-- limpio de la nube. Medido con `psql \\dp`: mostraba `takab_app=arwd`.
--
-- El REVOKE va aquí, y no en el 0001, para que valga en los DOS caminos: en una
-- base nueva deshace el blanket grant, y en una incremental es un no-op.
-- Mismo patrón que el `REVOKE ALL ON waveform_features_1s` del propio 0001.
REVOKE UPDATE, DELETE ON fw_releases FROM takab_app;
-- takab_ingest tampoco publica firmware: solo lo hace la API como superadmin.
REVOKE ALL ON fw_releases FROM takab_ingest;

ALTER TABLE fw_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE fw_releases FORCE  ROW LEVEL SECURITY;

-- Lectura: cualquier rol autenticado (patrón `ref_eq_read` de
-- reference_earthquakes). El catálogo de firmware no es un secreto; lo que sí
-- está acotado por tenant es QUÉ gabinete corre qué, y eso vive en `gateways`.
DROP POLICY IF EXISTS fw_rel_read ON fw_releases;
CREATE POLICY fw_rel_read ON fw_releases FOR SELECT
  USING (app_role() IS NOT NULL);

-- Escritura: solo el dueño de la plataforma. Ni el tenant_admin de un cliente
-- decide qué firmware corre el gabinete que protege su edificio.
DROP POLICY IF EXISTS fw_rel_publish ON fw_releases;
CREATE POLICY fw_rel_publish ON fw_releases FOR INSERT
  WITH CHECK (app_role() = 'takab_superadmin');

RESET ROLE;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Borrar el registro convertiría a TODA la flota en "SIN REFERENCIA" y dejaría
    # sin fechar los despliegues ya hechos. Mismo criterio que 0021/0022/0023/0025.
    pass
