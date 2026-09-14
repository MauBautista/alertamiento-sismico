"""T-7.36 · `incidents.opened_trigger`: qué ABRIÓ el incidente, no qué lo escaló

`incidents.trigger` **no es el disparo de apertura**. El UPSERT de la ingesta
(`handlers._EVENT_SQL`) lo sobrescribe con el de la última escalada
(`ON CONFLICT (event_uuid) DO UPDATE SET … trigger = EXCLUDED.trigger`), y
`summary` se fusiona perdiendo el valor viejo. **Ningún sitio del esquema guarda
hoy con qué se abrió.**

Y el dictamen —documento con peso legal— presenta ese campo como el origen
(«…en <inmueble> por <disparo>») y **el mismo campo decide el tiempo de aviso
ganado**. Las dos direcciones del error son reales y opuestas:

* umbral local abre, SASMEX escala ⇒ `trigger = 'sasmex'` con el `opened_at` del
  umbral: el papel **infla** el aviso ganado atribuyéndole a SASMEX segundos que
  transcurrieron antes de que SASMEX dijera nada.
* SASMEX abre, el cuórum escala ⇒ `trigger = 'quorum'` y `_lead_time` **niega**
  un aviso que sí existió.

Es latente, no vivo: el incidente del acto 3 del 2026-09-12 abrió `sasmex` y
nunca escaló. Muerde en cuanto un sismo fuerte escale un incidente abierto por el
SASMEX — o sea, en el primer sismo de verdad.

**La estampa la pone la BASE, no cada escritor.** Hay ~39 `INSERT INTO incidents`
repartidos entre migraciones, sembradores, arneses y tests, en cuatro lenguajes
de invocación distintos: confiar en que todos pongan la columna es exactamente
cómo se llega a un campo de auditoría con huecos. El disparador la copia de
`trigger` en el INSERT **ignorando lo que traiga el escritor** (nadie puede
mentir sobre el origen) y la **restaura desde `OLD` en cada UPDATE** (nadie puede
reescribirla, ni queriendo ni por descuido en un `UPDATE … SET` amplio).

Lo que esta migración NO hace, a propósito: **no toca la derivación del móvil**.
`queries/mobile.OPEN_INCIDENT` seguirá leyendo `trigger`, porque allí la pregunta
es otra —«¿quién autoriza evacuar AHORA?»— y la respuesta correcta es la escalada
vigente: si el cuórum corrobora, el cuórum autoriza (`autoriza_evacuacion`).
Cambiarlo ahí **reduciría** autorizaciones legítimas, que es la dirección cara.

Idempotente: `ADD COLUMN IF NOT EXISTS`, `UPDATE` acotado a los nulos,
`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS` antes del `CREATE`, y
`SET NOT NULL` que es no-op si ya lo está. DDL sobre una tabla PREEXISTENTE ⇒
como usuario de conexión, sin `SET ROLE` (invariante de `T-1.7`). No hace falta
`GRANT`: la columna hereda los permisos de la tabla y el disparador es
`SECURITY INVOKER`, así que corre bajo `takab_ingest` y bajo `takab_app` sin
privilegio extra.
"""

from __future__ import annotations

from alembic import op

revision: str = "0063_disparo_de_apertura"
down_revision: str | None = "0062_simulacro_aborto_por_sitio"
branch_labels = None
depends_on = None

_COLUMNA = """
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS opened_trigger text;
"""

# Relleno de lo ya existente: `trigger` es lo mejor que se sabe de un incidente
# viejo. Para los que nunca escalaron —la inmensa mayoría— es exacto; para los que
# escalaron es lo único que queda, y no hay forma de reconstruir el original.
# Acotado a `IS NULL` para que una segunda pasada no pise lo que ya estampó el
# disparador.
_RELLENO = """
UPDATE incidents SET opened_trigger = trigger WHERE opened_trigger IS NULL;
"""

_FN = """
CREATE OR REPLACE FUNCTION takab_stamp_opened_trigger()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF TG_OP = 'INSERT' THEN
    -- Se COPIA de `trigger`, nunca se lee de lo que mandó el escritor: un campo
    -- de auditoría que el emisor puede rellenar no audita al emisor.
    NEW.opened_trigger := NEW.trigger;
  ELSE
    -- Inmutable. Se restaura en silencio en vez de lanzar: el UPSERT de la
    -- ingesta no la menciona, y hacer fallar ahí mandaría a la DLQ la escalada
    -- de un sismo real por una columna que el escritor ni sabía que existía.
    NEW.opened_trigger := OLD.opened_trigger;
  END IF;
  RETURN NEW;
END $fn$;
"""

_TRIGGER = """
DROP TRIGGER IF EXISTS trg_incidents_opened_trigger ON incidents;
CREATE TRIGGER trg_incidents_opened_trigger
  BEFORE INSERT OR UPDATE ON incidents
  FOR EACH ROW EXECUTE FUNCTION takab_stamp_opened_trigger();
"""

# Va DESPUÉS del disparador: los BEFORE corren antes de comprobar restricciones,
# así que a partir de aquí ninguna fila nueva puede nacer sin estampa.
_NOT_NULL = """
ALTER TABLE incidents ALTER COLUMN opened_trigger SET NOT NULL;
"""


def upgrade() -> None:
    op.execute(_COLUMNA)
    op.execute(_RELLENO)
    op.execute(_FN)
    op.execute(_TRIGGER)
    op.execute(_NOT_NULL)
    op.execute(
        "COMMENT ON COLUMN incidents.opened_trigger IS "
        "'[T-7.36] Disparo con el que se ABRIÓ el incidente. Lo estampa "
        "trg_incidents_opened_trigger y es inmutable: `trigger` se sobrescribe con "
        "la última escalada y no sirve para reconstruir el origen ni el aviso ganado.'"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_incidents_opened_trigger ON incidents")
    op.execute("DROP FUNCTION IF EXISTS takab_stamp_opened_trigger()")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS opened_trigger")
