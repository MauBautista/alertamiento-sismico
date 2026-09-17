"""T-7.51 · un incidente cerrado no puede decir en papel que sigue abierto.

## El defecto, medido en la nube dev el 2026-09-17

Tres de los cuatro incidentes vivos tenían ``state = 'closed'`` y ``closed_at``
**nulo**. Y el dictamen imprime el campo CIERRE como ``"EN CURSO"`` cuando ese
campo falta, así que **el dictamen pericial de un incidente cerrado afirmaba que
seguía abierto**. Es la misma clase de defecto que `T-7.38`, `T-7.42` y `T-7.43`
cerraron en otras frases del mismo papel.

## La puerta, encontrada

Ningún camino de la aplicación cierra sin la hora: `incident/lifecycle.py` pone
``closed_at`` **y** escribe `incident_actions` **y** audita;
`routers/classification.py` también. Los tres incidentes no tenían ninguna de las
tres cosas: ni acción ``close``, ni verbo ``close`` en `audit_log` — que la purga
de `T-7.10` **conserva por nombre**, así que su ausencia es evidencia.

Quien cerraba era el **arnés de los E2E móviles**:
``infra/scripts/sql/staging-incident/{reset,crisis}.sql`` hacían
``UPDATE incidents SET state = 'closed' WHERE site_id = … AND state <> 'closed'``
sin ``closed_at``. Y su ``SITE_ID`` por defecto es ``d1000000-…-0000``, que es
`site-dev` — **Puebla, el sitio del gabinete REAL `gw-dev-0001`**. O sea que el
arnés cerraba incidentes de operación de verdad. Se arregla allí; que el arnés
comparta sitio con un gabinete real es una decisión que el software no toma solo
y queda fichada.

## Por qué una COLUMNA y no rellenar la hora

La hora real de aquellos tres cierres **no existe en ninguna parte**: no la
guardó nadie. Rellenarla sería inventar un dato en la tabla de la que cuelga un
dictamen pericial — exactamente lo que `T-7.42` y `T-7.43` acaban de prohibir en
ese mismo documento. Así que se DECLARA la ausencia, como hace
``documentos/identidad.py`` con los cuatro datos que no tiene.

⚠️ Y no vale con un ``CHECK … NOT VALID`` a secas. **Medido:** un `NOT VALID`
bloquea también los UPDATE de las filas que ya lo violan, así que las tres se
convertirían en **minas**: el backfill de picos del dictamen, el UPSERT de la
ingesta o `replay/service.py` fallarían al tocarlas. Con la columna, quedan
declaradas y siguen siendo escribibles.

## ⚠️ La RLS, que ya mató un despliegue

`incidents` tiene ``FORCE ROW LEVEL SECURITY`` (`db/schema.sql`): con FORCE ni el
dueño se salta las políticas, y `takab_migrator` —que es el dueño— no tiene
`BYPASSRLS`. Sin ``app.tenant_id`` puesto, un UPDATE afecta a CERO filas **en
silencio**. Es la trampa que mató el despliegue del 2026-09-14 con la `0063`, y
el bloque de abajo es el mismo remedio suyo. El ``CHECK`` se añade **validado** a
propósito: si el marcado no tocara nada, la validación revienta aquí y no en
producción tres días después. Los cuatro pasos son **indivisibles** — partir esta
migración en dos revisiones dejaría el CHECK puesto sobre filas sin declarar, y
entonces ya no habría forma de declararlas sin superusuario.
"""

from __future__ import annotations

from alembic import op

revision: str = "0066_cierre_con_hora"
down_revision: str | None = "0065_reproduccion_historica"
branch_labels = None
depends_on = None


#: El marcado va con la RLS apartada, y se restaura en el mismo bloque y dentro
#: de la misma transacción de alembic. `NO FORCE` **no abre la tabla a nadie
#: más**: sólo devuelve al DUEÑO el bypass que Postgres le da por defecto. Se lee
#: de `pg_class` en vez de darlo por hecho — restaurar un FORCE que no estaba
#: puesto sería endurecer una tabla como efecto colateral.
_DECLARAR = """
DO $mig$
DECLARE forzada boolean;
BEGIN
  SELECT relforcerowsecurity INTO forzada FROM pg_class WHERE oid = 'incidents'::regclass;
  IF forzada THEN
    EXECUTE 'ALTER TABLE incidents NO FORCE ROW LEVEL SECURITY';
  END IF;
  UPDATE incidents SET cierre_sin_hora = true
   WHERE state = 'closed' AND closed_at IS NULL;
  IF forzada THEN
    EXECUTE 'ALTER TABLE incidents FORCE ROW LEVEL SECURITY';
  END IF;
END $mig$;
"""

#: Un cierre tiene hora, o DECLARA que no la tiene. No hay tercera opción: un
#: `closed` con `closed_at` nulo y sin declarar es lo que hacía que el papel
#: dijera «EN CURSO» de un incidente cerrado.
_CHECK = (
    "ALTER TABLE incidents ADD CONSTRAINT ck_incidents_cierre_con_hora "
    "CHECK (state <> 'closed' OR closed_at IS NOT NULL OR cierre_sin_hora)"
)


#: ⚠️ IDEMPOTENTE, como exige el invariante del proyecto: `db/schema.sql` es el
#: esquema FINAL y se aplica antes de correr las migraciones, así que la 0002 en
#: adelante se encuentran su propio trabajo ya hecho. `ADD COLUMN` a secas
#: reventaba con `DuplicateColumn` y tumbaba la purga de demostración — y el
#: `ADD CONSTRAINT` no tiene `IF NOT EXISTS`, así que se pregunta a
#: `pg_constraint`.
_COLUMNA = (
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cierre_sin_hora boolean NOT NULL DEFAULT false"
)

_COMENTARIO = """
COMMENT ON COLUMN incidents.cierre_sin_hora IS
  '[T-7.51] El incidente se cerró sin que nadie registrara la hora. DECLARA la '
  'ausencia en vez de inventarla: la hora real no existe en ninguna parte. Sólo '
  'lo levantan los cierres anteriores a esta migración; ningún camino vivo puede '
  'ponerlo.'
"""

_CHECK_IDEMPOTENTE = f"""
DO $ck$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'incidents'::regclass
       AND conname = 'ck_incidents_cierre_con_hora'
  ) THEN
    EXECUTE $q${_CHECK}$q$;
  END IF;
END $ck$;
"""


def upgrade() -> None:
    op.execute(_COLUMNA)
    op.execute(_COMENTARIO)
    op.execute(_DECLARAR)
    op.execute(_CHECK_IDEMPOTENTE)


def downgrade() -> None:
    op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_cierre_con_hora")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS cierre_sin_hora")
