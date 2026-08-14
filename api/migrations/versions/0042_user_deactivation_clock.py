"""T-2.81.b · El reloj de la baja: `user_deactivations`.

`user_profiles.display_name` y `phone` son PII con caducidad y la T-2.81 los dejó
FUERA del plan de retención **con su razón escrita**, que es la parte que hay que
conservar: la única columna temporal de la tabla era `updated_at`, y un perfil
sin tocar en dos años describe a un empleado **estable**, no a uno que se fue.
Usarla como caducidad habría borrado antes los nombres de quien más tiempo lleva
en el edificio — exactamente al revés de lo que la retención pretende. Estaba
declarado en `SIN_RELOJ` con test recíproco: no era un olvido, era una decisión
aplazada.

El reloj correcto es la **baja de la cuenta**, y hasta hoy no se registraba en
ninguna parte. Esta revisión lo registra.

──────────────────────────────────────────────────────────────────────────────
1 · QUIÉN ESCRIBE EL HECHO, Y CUÁNDO — la mitad que hace real a la ficha
──────────────────────────────────────────────────────────────────────────────
Una columna que nadie rellena es el mismo problema con otro nombre. Así que el
hecho **no estrena un acto nuevo**: lo escriben los dos actos que ya existen y
que ya significan "esta persona ya no está", en la misma transacción en que ya
dejan su fila de `audit_log` (`routers/users.py`):

* `PATCH /users/{u} {"enabled": false}` — la baja REVERSIBLE, que es la que la
  consola ofrece primero;
* `DELETE /users/{u}` — la baja definitiva de la identidad.

Y `PATCH {"enabled": true}` **para el reloj** (`reactivated_at`). Sin eso, una
persona readmitida seguiría contando plazo y la retención le borraría el nombre
estando en el edificio.

Quien lo escribe es, por tanto, el **administrador del cliente** (acción
`manage_users` = `tenant_admin` + `takab_superadmin`), en el instante en que da
de baja. No lo escribe Cognito y no se deriva de nada: el directorio de
identidades no llama a TAKAB.

Y **quién** lo hizo no se copia a esta tabla: ya está en `audit_log`, escrito en
la misma transacción y en una bitácora que no se poda jamás. Una columna mutable
con el mismo dato sería la versión peor de la que ya existe.

**El hueco que queda, declarado y no escondido:** una cuenta retirada
directamente en el pool de Cognito —consola de AWS, CLI— no pasa por esta API y
no deja reloj. Esa persona conserva nombre y teléfono indefinidamente, que es el
estado de HOY para todo el mundo: se conserva de más, nunca se borra de menos.
La consola es el camino documentado y el único que reparte `manage_users`; la
reconciliación contra el pool queda fichada, no supuesta.

──────────────────────────────────────────────────────────────────────────────
2 · POR QUÉ UNA TABLA Y NO UNA COLUMNA EN `user_profiles`
──────────────────────────────────────────────────────────────────────────────
La razón es de PRIVILEGIO, no de estilo. El `tenant_admin` **no** es un rol
interno de TAKAB: sobre `user_profiles` sus únicas políticas son "mi propia
fila" y "interno". El reloj como columna habría exigido abrirle una política de
UPDATE sobre las filas de OTROS — y como `WITH CHECK` no puede comparar contra
la fila vieja, esa misma política le habría dejado reescribir `display_name` y
`phone` de cualquiera del padrón. Se habría ensanchado la escritura sobre las
dos columnas de PII que esta ficha existe para proteger, para poder protegerlas.

Con tabla propia, la superficie de escritura de `user_profiles` no cambia ni un
bit: el administrador escribe el HECHO, no el dato personal.

El FK COMPUESTO `(tenant_id, user_sub) → user_profiles` es el mismo candado de
`privacy_erasure_requests` (T-2.80.b): dar de baja a alguien de otro cliente no
se rechaza por una comprobación — viola integridad referencial.

──────────────────────────────────────────────────────────────────────────────
3 · EL `REVOKE DELETE` NO ES CINTURÓN DE MÁS (lección de T-2.78.a)
──────────────────────────────────────────────────────────────────────────────
La 0001 termina con `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN
SCHEMA public TO takab_app`, y ese grant masivo corre **después** del cuerpo de
`db/schema.sql`. O sea: el `REVOKE DELETE` que este fichero espeja en el schema
queda deshecho en una base NUEVA y en pie en una base EXISTENTE — dos
despliegues con permisos distintos sobre el reloj de la retención. Revocar aquí,
que corre después de la 0001 por los dos caminos, es lo que los iguala.

Y el `DELETE` importa: la vuelta se ESCRIBE (`reactivated_at`), no se borra. Una
baja que se puede hacer desaparecer es un reloj que se puede parar sin dejar
rastro.

Revision ID: 0042_user_deactivation_clock
Revises: 0041_ops_alert_ack
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042_user_deactivation_clock"
down_revision: str | None = "0041_ops_alert_ack"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- 1: la tabla (objeto NUEVO ⇒ SET ROLE takab_migrator) ----------------------
_TABLA = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS user_deactivations (
  tenant_id      uuid NOT NULL REFERENCES tenants,
  user_sub       uuid NOT NULL,
  deactivated_at timestamptz NOT NULL DEFAULT now(),
  via            text NOT NULL CHECK (via IN ('account_disabled','account_deleted')),
  reactivated_at timestamptz,
  PRIMARY KEY (tenant_id, user_sub),
  CONSTRAINT fk_baja_del_padron_del_tenant FOREIGN KEY (tenant_id, user_sub)
    REFERENCES user_profiles (tenant_id, user_sub) ON DELETE CASCADE,
  CONSTRAINT ud_la_vuelta_es_posterior
    CHECK (reactivated_at IS NULL OR reactivated_at >= deactivated_at)
);

CREATE INDEX IF NOT EXISTS idx_user_deactivations_reloj
  ON user_deactivations (tenant_id, deactivated_at)
  WHERE reactivated_at IS NULL;

RESET ROLE;
"""

# --- 2: permisos y RLS ---------------------------------------------------------
_PERMISOS = """
GRANT SELECT, INSERT, UPDATE ON user_deactivations TO takab_app;
REVOKE DELETE ON user_deactivations FROM takab_app;
REVOKE ALL ON user_deactivations FROM takab_ingest;

ALTER TABLE user_deactivations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_deactivations FORCE  ROW LEVEL SECURITY;

-- Mismo círculo que `manage_users` en `auth/matrix.py`. La acción de matriz solo
-- hace que el 403 llegue limpio; quien confina por cliente es esto.
DROP POLICY IF EXISTS ud_admin ON user_deactivations;
CREATE POLICY ud_admin ON user_deactivations FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() = 'tenant_admin')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() = 'tenant_admin');

-- Los roles internos, exactamente como en `user_profiles_admin`: el superadmin
-- da de baja en cualquier cliente (`routers/users.py` ya se lo permite) y el job
-- de retención —que corre como `takab_support`— tiene que LEER el reloj de todos
-- los tenants para poder recorrerlos.
DROP POLICY IF EXISTS ud_internal ON user_deactivations;
CREATE POLICY ud_internal ON user_deactivations FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
"""

# La vuelta atrás quita lo añadido; no degrada ningún dato preexistente, porque
# el hecho «esta persona ya no está» no existía antes de esta revisión.
_DOWN = """
DROP TABLE IF EXISTS user_deactivations;
"""


def upgrade() -> None:
    op.execute(_TABLA)
    op.execute(_PERMISOS)


def downgrade() -> None:
    op.execute(_DOWN)
