"""T-6.17 · el rechazo y el aborto de un simulacro viajan a la nube

Hasta aquí `drills.active` era una **ventana de reloj**: `started_at + duration_s`
sin cierre por acuse. Un gabinete que rechazaba el comando —lo correcto con
`command_enabled` apagada— o que lo abortaba porque entró una alerta real no
cambiaba nada en la nube, y el teléfono anunciaba «SIMULACRO EN CURSO» los
minutos enteros. Medido el 2026-09-06 con un simulacro real: dos gabinetes en
`rejected`, franja ámbar en el móvil tres minutos (`INFORME-UIUX.md`, U-01/U-03).

**Dos columnas en `drill_sites` y un permiso.**

* `drill_sites.aborted_at` / `abort_reason` — el aborto es **por sitio**, no por
  simulacro: un tier instrumental aborta en un gabinete y no en el vecino. La
  fila del simulacro se cierra (`stop_reason='aborted'`) solo cuando no queda
  ningún sitio ejecutándolo. `stop_reason` es texto libre: `'aborted'` es
  aditivo y no toca ningún CHECK.
* `GRANT UPDATE` a `takab_ingest` sobre `drills` y `drill_sites` — el aborto llega
  por el mismo camino que todo acuse (`takab/acks` → `handle_command_ack`), y
  hasta hoy la ingesta solo podía LEER estas dos tablas. Sin este grant el
  handler rompería en la nube y pasaría en local (donde el test migra como
  superusuario): la trampa de `T-1.7`.

**Y la señal live.** La consola sondeaba `/drills/active` cada 10 s; con el aborto
viajando, lo que faltaba era que llegara sin esperar al tic. Dos funciones
dedicadas (mismo patrón que `takab_notify_gateway_equipment`, 0022): `drills` y
`drill_sites` notifican `t='drill'` con `tenant` e `id`; y el acuse de un comando
de simulacro (`commands.status` cambia con `action` `drill_start`/`drill_stop`)
notifica lo mismo resolviendo el `drill_id` por `drill_sites`. El hub lo mapea al
topic `incidents` como invalidación sin lectura (precedente `checkin`, T-2.11).

Idempotente (`IF NOT EXISTS`; `GRANT` repetido es no-op; `CREATE OR REPLACE` +
`DROP TRIGGER IF EXISTS`). DDL sobre tablas PREEXISTENTES ⇒ como usuario de
conexión, sin `SET ROLE`. Las funciones son `SECURITY INVOKER` y solo hacen
`pg_notify`: corren bajo `takab_app` (stop) y bajo `takab_ingest` (acuse).
"""

from __future__ import annotations

from alembic import op

revision: str = "0062_simulacro_aborto_por_sitio"
down_revision: str | None = "0061_plantillas_de_simulacro"
branch_labels = None
depends_on = None

_FN_DRILL = """
CREATE OR REPLACE FUNCTION takab_notify_drill()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  PERFORM pg_notify('takab_live', jsonb_build_object(
    't', 'drill', 'tenant', NEW.tenant_id, 'id', NEW.drill_id)::text);
  RETURN NULL;
END $fn$;
"""

_FN_DRILL_COMMAND = """
CREATE OR REPLACE FUNCTION takab_notify_drill_command()
RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  d uuid;
BEGIN
  SELECT drill_id INTO d FROM drill_sites WHERE command_id = NEW.command_id LIMIT 1;
  IF d IS NOT NULL THEN
    PERFORM pg_notify('takab_live', jsonb_build_object(
      't', 'drill', 'tenant', NEW.tenant_id, 'id', d)::text);
  END IF;
  RETURN NULL;
END $fn$;
"""

_TRIGGERS = (
    "DROP TRIGGER IF EXISTS trg_drills_notify ON drills",
    "CREATE TRIGGER trg_drills_notify AFTER INSERT OR UPDATE ON drills "
    "FOR EACH ROW EXECUTE FUNCTION takab_notify_drill()",
    "DROP TRIGGER IF EXISTS trg_drill_sites_notify ON drill_sites",
    "CREATE TRIGGER trg_drill_sites_notify AFTER INSERT OR UPDATE ON drill_sites "
    "FOR EACH ROW EXECUTE FUNCTION takab_notify_drill()",
    "DROP TRIGGER IF EXISTS trg_commands_drill_notify ON commands",
    "CREATE TRIGGER trg_commands_drill_notify AFTER UPDATE OF status ON commands "
    "FOR EACH ROW WHEN (NEW.action IN ('drill_start', 'drill_stop')) "
    "EXECUTE FUNCTION takab_notify_drill_command()",
)


def upgrade() -> None:
    op.execute("ALTER TABLE drill_sites ADD COLUMN IF NOT EXISTS aborted_at timestamptz")
    op.execute("ALTER TABLE drill_sites ADD COLUMN IF NOT EXISTS abort_reason text")
    op.execute("GRANT UPDATE ON drills, drill_sites TO takab_ingest")
    op.execute(_FN_DRILL)
    op.execute(_FN_DRILL_COMMAND)
    for stmt in _TRIGGERS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_commands_drill_notify ON commands")
    op.execute("DROP TRIGGER IF EXISTS trg_drill_sites_notify ON drill_sites")
    op.execute("DROP TRIGGER IF EXISTS trg_drills_notify ON drills")
    op.execute("DROP FUNCTION IF EXISTS takab_notify_drill_command()")
    op.execute("DROP FUNCTION IF EXISTS takab_notify_drill()")
    op.execute("REVOKE UPDATE ON drills, drill_sites FROM takab_ingest")
    op.execute("ALTER TABLE drill_sites DROP COLUMN IF EXISTS abort_reason")
    op.execute("ALTER TABLE drill_sites DROP COLUMN IF EXISTS aborted_at")
