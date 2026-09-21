"""T-7.25 · el INTENTO de preguntarle al catálogo externo se registra, y el worker escribe

## Por qué hace falta una tabla y no bastan las tres columnas de la 0060

`shared/glossary/procedencia.json` nombra cinco estados y uno de ellos —
``consultando``, «se le preguntó a la fuente y todavía no contestó»— **era
inalcanzable**. `procedencia.de_fila()` deriva el estado de UNA fila de
`reference_earthquakes`, y mientras la consulta está en vuelo esa fila **no
existe**: no hay dónde escribir «pregunté». El resultado es que un timeout, un
5xx o un worker que muere a mitad se leían igual que «nadie ha preguntado nunca»
(`sin_dato_externo`), que es justo la confusión que el glosario existe para
impedir — y la familia de defecto que este repositorio lleva una fase cazando:
*una superficie que dice «no sé» cuando lo que quiere decir es «no pude»*.

`catalog_consultations` registra el intento **antes** de salir a la red y su
desenlace **después**. Las dos mitades importan, y el orden también: la fila se
escribe y se COMMITEA antes de la llamada HTTP, así que un worker que se muera a
mitad deja el hecho escrito.

## Las columnas, y la que parece redundante y no lo es

* ``asked_at`` — la PRIMERA vez que se preguntó. **No se reescribe jamás**
  (regla de oro 3): es la fecha que el papel cita.
* ``last_attempt_at`` — el último intento. Es lo que mide el reloj del reintento.
  Sin ella el reintento tendría que correr `asked_at`, y entonces «cuándo se
  preguntó» pasaría a significar «cuándo se preguntó por última vez», que no es
  lo mismo y es lo que se cita.
* ``answered_at`` — NULL = **no contestó**. Es el único bit que separa
  ``consultando`` de un desenlace, y por eso es una fecha y no un booleano: sin
  ella, «contestó» no se puede fechar.
* ``outcome`` — vocabulario cerrado de TRES: ``correlacionado`` /
  ``sin_correlacion`` / ``sin_respuesta``. NULL = la pregunta salió y todavía no
  ha vuelto (o el worker murió con ella en vuelo).
* ``catalog_key`` — la fila de `reference_earthquakes` que resultó ser ésta.
  ⚠️ Es una clave NUESTRA; el identificador del proveedor vive en
  `reference_earthquakes.provider_event_id` y son cosas distintas.
* ``detail`` — la razón, en castellano, para quien lea la tabla a las 3 de la
  mañana. Un desenlace sin razón obliga a releer el log del worker.

## El índice único que impide que el mismo sismo entre DOS veces

`reference_earthquakes.catalog_key` es una clave que nos inventamos nosotros
(`'USGS-2017-09-19-PUE'` en el seed) y el worker no puede reproducirla. Si la
identidad de una fila fuera `catalog_key`, reconsultar el evento `us2000ar20`
—que YA está sembrado— insertaría un segundo Puebla-Morelos 2017 y el catálogo
tendría dos verdades sobre el mismo sismo. La identidad real es
``(source, provider_event_id)``, y aquí se vuelve una restricción de la base en
vez de una buena intención del worker.

Va PARCIAL (`WHERE provider_event_id IS NOT NULL`) porque las siete filas del
seed que no llevan identificador de proveedor no pueden colisionar entre sí: en
un índice único ordinario todas serían `(SSN, NULL)` —que en SQL no colisiona—
pero el predicado deja dicho, y no adivinado, que esas filas están fuera.

## Los GRANT, y por qué se escriben aunque la 0001 ya los diera

La `0001` termina con `GRANT SELECT, INSERT, UPDATE ON ALL TABLES … TO
takab_ingest`, así que sobre una base nueva el worker YA podía escribir
`reference_earthquakes` pese a que `db/schema.sql` solo le concede `SELECT`.
Eso no es un permiso: es un efecto colateral del orden de la migración inicial,
y este repositorio ya se quemó con él (un rol salió con privilegios en la nube
que no tenía en local). Aquí el permiso se ESCRIBE, y el espejo de
`db/schema.sql` deja de mentir.

`catalog_consultations` nace después de ese `ON ALL TABLES`, así que sus
privilegios no los hereda de nadie: `takab_app` recibe **solo SELECT**. Eso es el
criterio 1 de la ficha —«el worker es el ÚNICO escritor»— convertido en
privilegio, no en costumbre.

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+: `db/schema.sql` es el
esquema final y la `0001` lo aplica ANTES, así que esta migración se encuentra su
propio trabajo hecho.

Revision ID: 0068_consulta_al_catalogo
Revises: 0067_evidencia_retenida
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0068_consulta_al_catalogo"
down_revision: str | None = "0067_evidencia_retenida"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
-- Objeto NUEVO ⇒ `SET ROLE takab_migrator` (invariante de dueños): las tablas de
-- negocio son de un rol NO-superusuario, sin lo cual `FORCE ROW LEVEL SECURITY`
-- sería inverificable. Los GRANT y los ALTER sobre tablas PREEXISTENTES van
-- fuera, como usuario de conexión.
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS catalog_consultations (
  incident_id     uuid NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  provider        text NOT NULL CHECK (provider IN ('USGS')),
  tenant_id       uuid NOT NULL REFERENCES tenants(tenant_id),
  asked_at        timestamptz NOT NULL,
  last_attempt_at timestamptz NOT NULL,
  attempts        int NOT NULL DEFAULT 1 CHECK (attempts > 0),
  answered_at     timestamptz,
  outcome         text CHECK (outcome IS NULL OR outcome IN
                              ('correlacionado','sin_correlacion','sin_respuesta')),
  catalog_key     text,
  detail          text NOT NULL DEFAULT '',
  PRIMARY KEY (incident_id, provider)
);

-- Los pendientes son los que hay que reintentar; el índice parcial los aísla para
-- que la pasada no barra la tabla entera cada cinco segundos.
CREATE INDEX IF NOT EXISTS idx_catalog_consult_pendientes
  ON catalog_consultations (last_attempt_at)
  WHERE answered_at IS NULL;

-- El índice que impide que el mismo sismo entre DOS veces (ver el encabezado).
-- Es un objeto nuevo sobre una tabla ajena: un índice hereda el dueño de su tabla,
-- así que se crea con el rol que la posee.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_eq_provider_event
  ON reference_earthquakes (source, provider_event_id)
  WHERE provider_event_id IS NOT NULL;

RESET ROLE;

COMMENT ON TABLE catalog_consultations IS
  '[T-7.25] El INTENTO de preguntarle a una fuente sismologica externa por un '
  'incidente. Existe para que `consultando` sea alcanzable: la fila se escribe '
  'ANTES de salir a la red, asi que un timeout o un worker muerto a mitad dejan '
  'el hecho escrito en vez de parecer que nadie pregunto nunca.';
COMMENT ON COLUMN catalog_consultations.asked_at IS
  'La PRIMERA vez que se pregunto. No se reescribe jamas: es la fecha que cita '
  'el papel (regla de oro 3).';
COMMENT ON COLUMN catalog_consultations.last_attempt_at IS
  'El ultimo intento. Es el reloj del reintento; separarla de asked_at evita que '
  '"cuando se pregunto" acabe significando "cuando se pregunto por ultima vez".';
COMMENT ON COLUMN catalog_consultations.answered_at IS
  'NULL = NO CONTESTO. Es el unico bit que separa `consultando` de un desenlace.';
COMMENT ON COLUMN catalog_consultations.outcome IS
  'correlacionado / sin_correlacion / sin_respuesta. NULL = la pregunta salio y '
  'todavia no ha vuelto (o el worker murio con ella en vuelo).';
COMMENT ON COLUMN catalog_consultations.catalog_key IS
  'La fila de reference_earthquakes que resulto ser esta. Es una clave NUESTRA; '
  'el identificador del proveedor es reference_earthquakes.provider_event_id.';

ALTER TABLE catalog_consultations ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_consultations FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cc_read ON catalog_consultations;
CREATE POLICY cc_read ON catalog_consultations FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());

-- Solo SELECT para la API: el criterio 1 de la ficha —«el worker es el UNICO
-- escritor»— convertido en privilegio en vez de en costumbre. Y no hay politica
-- de escritura, asi que ni con GRANT podria: escribe `takab_ingest` (BYPASSRLS).
GRANT SELECT ON catalog_consultations TO takab_app;
GRANT SELECT, INSERT, UPDATE ON catalog_consultations TO takab_ingest;
-- ⚠️ MEDIDO el 2026-09-20 sobre una base construida DESDE CERO, y el REVOKE no
-- es redundante: la `0001` termina con `GRANT … ON ALL TABLES IN SCHEMA public
-- TO takab_app` y para entonces esta tabla YA existe (la trae `db/schema.sql`),
-- asi que en una base nueva `takab_app` salia con INSERT, UPDATE y DELETE. En
-- una base EXISTENTE —donde la crea esta migracion, despues de aquel GRANT— no
-- pasa. O sea: el privilegio de mas aparece solo en la nube, que es el modo de
-- fallo que ya destapo a `takab_app` con SELECT sobre hashes de credencial.
-- La RLS (FORCE, sin politica de escritura) lo bloquearia igual; esto es la
-- segunda capa, y es la que hace comprobable «el worker es el unico escritor».
REVOKE INSERT, UPDATE, DELETE ON catalog_consultations FROM takab_app;

-- [T-7.25] El worker de consulta ESCRIBE el catalogo: es el unico que lo hace.
-- Hasta aqui solo tenia SELECT (T-7.14) y escribia de todas formas en una base
-- nueva, por el `GRANT ... ON ALL TABLES` con que termina la 0001. Eso no es un
-- permiso: es un efecto colateral del orden de la migracion inicial.
GRANT SELECT, INSERT, UPDATE ON reference_earthquakes TO takab_ingest;
-- Y el mismo REVOKE que arriba, sobre la tabla que esta ficha acaba de volver
-- ESCRIBIBLE. Estaba blindada `catalog_consultations` y quedaba abierta justo
-- `reference_earthquakes`: medido el 2026-09-20 sobre una base construida por
-- migraciones, `takab_app` tenia INSERT, UPDATE y DELETE sobre el catalogo por
-- el `GRANT ... ON ALL TABLES` de la 0001 — mientras el docstring de la prueba
-- que lo vigila afirmaba «takab_app lee las dos tablas y no escribe ninguna».
-- La RLS (FORCE, sin politica de escritura) lo bloquearia igual; esto es la
-- segunda capa, y es la que hace comprobable el criterio 1 de la ficha.
REVOKE INSERT, UPDATE, DELETE ON reference_earthquakes FROM takab_app;
"""

_DOWN = """
REVOKE INSERT, UPDATE ON reference_earthquakes FROM takab_ingest;
DROP INDEX IF EXISTS uq_ref_eq_provider_event;
DROP TABLE IF EXISTS catalog_consultations;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
