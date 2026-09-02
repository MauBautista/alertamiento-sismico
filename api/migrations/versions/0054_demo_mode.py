"""T-5.02 · Modo demostración por cliente, acotado en el tiempo.

El interruptor que faltaba: hasta hoy no existía ningún estado en el que el
sistema no molestara a nadie. Lo único que se llamaba «demo» era el reproductor
de escenas del panel del gabinete y el ``simulated`` de las notificaciones — que
**no es un modo**: es un estado derivado de la ausencia de credenciales, y por
tanto desaparece justo en el entorno donde se haría la demostración.

**Por cliente y no por despliegue** (`D-27`): cegar a todos los clientes para
demostrarle a uno es la peor de las opciones. **Y con vencimiento obligatorio**,
que es lo que hace de esto un interruptor de seguridad y no una nota mental: el
fallo realista no es la malicia, es el olvido.

**La ventana es el CHECK y no una comprobación de la aplicación.** Un tope que
vive en el código se salta con un `INSERT` a mano en una madrugada mala; uno que
vive en la base no. Ocho horas es el techo — más que eso ya no es una
demostración, es un cliente sin avisos.

**Apagar = borrar la fila**, y por eso esta tabla **no** es append-only ni lleva
guarda: el hecho que hay que conservar (quién lo encendió, quién lo apagó y
cuándo) vive en ``audit_log``, que sí lo es. Una tabla de estado que no se puede
vaciar sería un modo que no se puede apagar.

Revision ID: 0054_demo_mode
Revises: 0053_cctv
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_demo_mode"
down_revision: str | None = "0053_cctv"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `SET ROLE takab_migrator` porque la tabla es un objeto NUEVO: sin él quedaría a
# nombre del usuario de conexión, que en local es superusuario y en la nube no.
# Es la invariante de T-1.45, y su rojo aparece SOLO en la nube.
_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS demo_mode (
  -- Uno por cliente como MUCHO: la PK es el alcance, no un id suelto. Encender
  -- dos veces el mismo cliente es la misma ventana, no dos.
  tenant_id  uuid PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  enabled_by uuid NOT NULL,
  enabled_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  note       text NOT NULL DEFAULT '',
  -- El techo vive AQUÍ. Ver la cabecera: un tope de aplicación se salta con un
  -- INSERT a mano, y este modo suprime los avisos de un edificio entero.
  CONSTRAINT demo_mode_ventana_acotada
    CHECK (expires_at > enabled_at AND expires_at <= enabled_at + interval '8 hours')
);

RESET ROLE;

ALTER TABLE demo_mode ENABLE ROW LEVEL SECURITY;
ALTER TABLE demo_mode FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS demo_mode_tenant ON demo_mode;
CREATE POLICY demo_mode_tenant ON demo_mode
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- La API lo enciende y lo apaga; leerlo lo hacen los DOS lados. El worker de
-- notificación va con `takab_ingest` (BYPASSRLS) porque despacha para todos los
-- clientes a la vez y no tiene un tenant en la mano.
GRANT SELECT, INSERT, DELETE ON demo_mode TO takab_app;
-- El worker de notificación NECESITA borrar: «lo real gana» lo ejecuta él, antes
-- de planificar el primer aviso de un incidente. Sin el DELETE, un sismo no
-- podría apagar el modo y la promesa de D-27 sería falsa — que es exactamente el
-- fallo que este modo no puede permitirse. No se le da INSERT: encender es acto
-- de la consola, con su sesión y su rol; el worker solo puede apagar.
GRANT SELECT, DELETE ON demo_mode TO takab_ingest;

-- Estado NUEVO para un job suprimido por el modo. Va SIN `SET ROLE`: la tabla es
-- PREEXISTENTE y el DDL sobre ella lo hace el usuario de conexión (invariante de
-- T-1.45; el `SET ROLE takab_migrator` es solo para objetos nuevos).
--
-- Y es un estado PROPIO y no `simulated` ni `skipped`, aunque los tres acaben en
-- «nadie recibió nada». `simulated` significa «no hay proveedor real
-- configurado» y `skipped` «la cascada ya estaba satisfecha»: colapsarlos haría
-- imposible responder a la única pregunta que importa al día siguiente — ¿por
-- qué no llegó este aviso? Es la misma lección de `drill_sites.commandable`.
-- `sent_at` se queda en NULL, como en `simulated`: no llegó a nadie.
ALTER TABLE notification_jobs DROP CONSTRAINT IF EXISTS notification_jobs_status_check;
ALTER TABLE notification_jobs ADD CONSTRAINT notification_jobs_status_check
  CHECK (status IN ('pending','sent','failed','skipped','simulated','blocked_demo'));
"""

_DOWN = "DROP TABLE IF EXISTS demo_mode;"


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
