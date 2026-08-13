"""T-2.73.b · Devolver a `takab_migrator` las tablas que quedaron del superusuario.

El verificador de `T-2.73` señaló 7 tablas de `public` que pertenecen a `takab`
(superusuario) en vez de a `takab_migrator`. **Riesgo latente, no explotable
hoy:** una migración futura con `SET ROLE takab_migrator; ALTER TABLE
notification_jobs …` moriría con `must be owner of table`.

**Antes de escribir esto se midió de dónde sale el defecto, y no es del código.**
Las migraciones que las crean (0005, 0006, 0007, 0011, 0015) no llevan `SET ROLE`
—correctamente: el `SET ROLE` se reserva a objetos nuevos que quieran dueño
distinto del conector—, así que la tabla queda a nombre del **usuario de la
conexión**. Y ahí es donde los dos mundos divergen:

* **local** migra como `takab` (superusuario)  ⇒ dueño `takab`  ⇒ el defecto.
* **la nube** migra como `takab_migrator`      ⇒ dueño `takab_migrator` ⇒ sano.

Medido (2026-08-13, Postgres local): una tabla creada bajo `SET ROLE
takab_migrator` sin más queda a nombre de `takab_migrator`; y `takab_migrator`
**NO puede** cambiar el dueño de una que no es suya — `ERROR: must be owner of
table`. Ese error es exactamente lo que mataría un `apply` en la nube si esta
migración hiciera el `ALTER` a ciegas. Por eso **no lo hace a ciegas**:

* Si la tabla ya es de `takab_migrator` (el caso de la nube), no hay nada que
  hacer y no se toca — que es también lo que la hace idempotente.
* Si no lo es y el usuario de la conexión **puede** (es el dueño o superusuario:
  el caso local), se transfiere.
* Si no lo es y **no puede**, se deja un `RAISE NOTICE` y se sigue. Un aviso en
  el log de alembic es infinitamente mejor que un despliegue muerto por una
  higiene que no era urgente.

Alcance derivado del catálogo, no de la lista de la ficha —que se había quedado
corta: en la base de desarrollo aparecía además `reference_earthquakes`—. Se
excluyen las tablas que pertenecen a una extensión (`pg_depend.deptype = 'e'`,
p.ej. `spatial_ref_sys` de PostGIS): su dueño lo pone quien instaló la extensión
y no es asunto nuestro. Y se excluye `alembic_version` a propósito: es la
contabilidad de la propia herramienta, no una tabla de negocio, y el riesgo que
esta ficha persigue —`SET ROLE takab_migrator` + DDL— no la alcanza.

**NO se toca `tenant_retire_codes`.** Su `ENABLE` sin `FORCE` es la otra mitad de
la ficha y resultó ser una decisión, no un olvido: `db/schema.sql:1052` lo
declara explícitamente y ponerle FORCE **rompe** `app_verify_retire_code` —
medido: devuelve `false` para un código correcto, o sea deja sin poder retirar un
gabinete a quien tiene derecho. Ese lado se arregló en el verificador
(`ops/restore_check.py`), no aquí. Ver `tests/ops/test_rls_no_force_declarada.py`.

Tablas PREEXISTENTES ⇒ **sin `SET ROLE`**: el DDL corre como el usuario de la
conexión (invariante de dueños del proyecto).
Idempotente (invariante T-1.45): la segunda pasada no encuentra nada que mover.

Revision ID: 0039_table_owners_migrator
Revises: 0038_privacy_erasure_on_behalf
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039_table_owners_migrator"
down_revision: str | None = "0038_privacy_erasure_on_behalf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# `pg_has_role(current_user, X, 'USAGE')` es la pregunta correcta en los dos
# sitios donde aparece: PostgreSQL exige, para transferir, ser miembro del rol
# DUEÑO (o superusuario) **y** miembro del rol DESTINO. Preguntarlo al catálogo
# en vez de asumirlo es lo que convierte un `apply` muerto en un NOTICE.
_UP = """
DO $mig$
DECLARE
  t record;
  movidas int := 0;
  saltadas int := 0;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'takab_migrator') THEN
    RAISE NOTICE '0039: no existe el rol takab_migrator; nada que hacer';
    RETURN;
  END IF;
  IF NOT pg_has_role(current_user, 'takab_migrator', 'USAGE') THEN
    RAISE NOTICE '0039: % no es miembro de takab_migrator; no se transfiere nada', current_user;
    RETURN;
  END IF;

  FOR t IN
    SELECT c.oid, c.relname, c.relowner
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND c.relowner <> 'takab_migrator'::regrole
       AND c.relname <> 'alembic_version'
       AND NOT EXISTS (
             SELECT 1 FROM pg_depend d
              WHERE d.classid = 'pg_class'::regclass
                AND d.objid = c.oid
                AND d.deptype = 'e')
     ORDER BY c.relname
  LOOP
    IF pg_has_role(current_user, t.relowner, 'USAGE') THEN
      EXECUTE format('ALTER TABLE public.%I OWNER TO takab_migrator', t.relname);
      movidas := movidas + 1;
    ELSE
      saltadas := saltadas + 1;
      RAISE NOTICE '0039: % sigue siendo de %; % no puede transferirla',
        t.relname, t.relowner::regrole, current_user;
    END IF;
  END LOOP;

  RAISE NOTICE '0039: % tablas devueltas a takab_migrator, % saltadas', movidas, saltadas;
END
$mig$;
"""

# Sin vuelta atrás, y no por pereza: el dueño ANTERIOR era un accidente del
# usuario con el que se migró, distinto en cada entorno. Un `downgrade` tendría
# que inventarse a quién devolvérsela, y en la nube devolvérsela a `takab` es
# imposible (ese rol ni existe allí). Deshacer esto es no haberlo hecho.
_DOWN = "SELECT 1"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
