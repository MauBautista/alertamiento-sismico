"""T-7.14 · la reproducción histórica: ventana armada y `reproduccion` en el catálogo.

Dos cosas que van juntas porque sin la segunda la primera deja incidentes que
nadie puede clasificar por lo que fueron.

## `demo_replay` — armar es DECLARAR

Una fila dice: «en este cliente, hasta esta hora, lo que abra un pulso del WR-1 es
una reproducción del sismo `catalog_key`». No hay forma técnica de distinguir el
pulso de una demostración del de una alerta real —es el mismo contacto seco, que
es justo lo que hace confiable al camino SASMEX—, así que lo que el sistema puede
exigir es que alguien lo declare, con nombre, con vencimiento y en un cliente que
tenga sitios de demostración. Por eso:

* **`armed_until` obligatorio y acotado en la BASE**, igual que `demo_mode`. Ocho
  horas: más que eso no es una demostración. Un tope en la aplicación se salta
  con un INSERT a mano.
* **PK = el cliente.** Armar dos veces es la misma ventana, no dos verdades sobre
  qué sismo se está reproduciendo.
* **FK a `reference_earthquakes(catalog_key)`.** No se puede armar un sismo que no
  esté en el catálogo con su procedencia: la cifra que se enseñe tiene que venir
  de una fila citable (`T-7.12`).
* **Riesgo residual, escrito donde se lee:** dentro de la ventana, un sismo REAL
  en ese cliente se rotularía como reproducción. Es el precio de anclar la
  demostración al gabinete real, y por eso la ventana vence sola, la abre solo un
  superadmin y el rótulo viaja en `meta.reproduccion` del evento — que no se borra
  y permite saber después qué incidentes se vistieron de demostración.

## `reproduccion` en el catálogo de clasificación

`D-33`: una corrida de demostración **no es** una prueba del gabinete ni un falso
positivo, y meterla en cualquiera de las dos ensucia la única métrica que decide
si un cliente renueva. Entra como quinta clasificación, cierra el incidente y
**no cuenta en el denominador de la tasa**, por lo mismo que `prueba`.

Revision ID: 0065_reproduccion_historica
Revises: 0064_worker_lee_clasificacion
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0065_reproduccion_historica"
down_revision: str | None = "0064_worker_lee_clasificacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `SET ROLE takab_migrator` SOLO para el objeto NUEVO (la tabla); el ALTER sobre
# `incident_classifications`, que es preexistente, va como usuario de conexión.
_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS demo_replay (
  tenant_id   uuid PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  catalog_key text NOT NULL REFERENCES reference_earthquakes(catalog_key),
  armed_by    uuid NOT NULL,
  armed_at    timestamptz NOT NULL DEFAULT now(),
  armed_until timestamptz NOT NULL,
  note        text NOT NULL DEFAULT '',
  CONSTRAINT demo_replay_ventana_acotada
    CHECK (armed_until > armed_at AND armed_until <= armed_at + interval '8 hours')
);

RESET ROLE;

ALTER TABLE demo_replay ENABLE ROW LEVEL SECURITY;
ALTER TABLE demo_replay FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS demo_replay_tenant ON demo_replay;
CREATE POLICY demo_replay_tenant ON demo_replay
  USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

GRANT SELECT, INSERT, DELETE ON demo_replay TO takab_app;
-- El worker LEE la ventana para vestir el incidente. No arma ni desarma: armar es
-- un acto de persona y desarmar también (o lo hace el vencimiento).
GRANT SELECT ON demo_replay TO takab_ingest;
-- Y el catálogo, que es de donde salen la magnitud y el epicentro que se visten.
-- La `0055`-equivalente de esta tabla la creó solo para `takab_app` porque hasta
-- ahora solo la consola la leía: sin esto el worker muere con `permission denied`
-- en cada pasada, verde en local e imposible en la nube.
GRANT SELECT ON reference_earthquakes TO takab_ingest;

-- [D-33] La quinta clasificación. Se reescribe el CHECK entero porque un CHECK no
-- se "amplía": se sustituye.
ALTER TABLE incident_classifications
  DROP CONSTRAINT IF EXISTS incident_classifications_classification_check;
ALTER TABLE incident_classifications
  ADD  CONSTRAINT incident_classifications_classification_check
  CHECK (classification IN
         ('real','falso_positivo','prueba','indeterminado','reproduccion'));
"""

# La bajada NO borra clasificaciones para poder estrechar el CHECK: la tabla es
# append-only por privilegio Y por trigger (regla de oro 11), y una migración que
# se salte eso deja escrito que se puede. Si ya hay filas `reproduccion`, la
# bajada se NIEGA y lo dice: estrechar el CHECK con filas que lo violan tampoco
# funcionaría, y fallar con el motivo escrito es mejor que fallar con el de
# Postgres.
_DOWN = """
DROP TABLE IF EXISTS demo_replay;

DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM incident_classifications WHERE classification = 'reproduccion';
  IF n > 0 THEN
    RAISE EXCEPTION 'hay % clasificaciones `reproduccion`: son append-only y no se borran '
                    'para estrechar el CHECK (regla de oro 11)', n;
  END IF;
END $$;

ALTER TABLE incident_classifications
  DROP CONSTRAINT IF EXISTS incident_classifications_classification_check;
ALTER TABLE incident_classifications
  ADD  CONSTRAINT incident_classifications_classification_check
  CHECK (classification IN ('real','falso_positivo','prueba','indeterminado'));
"""


def _exec(sql: str) -> None:
    """Por el cursor crudo: el cuerpo lleva `::uuid` que el binding de SQLAlchemy
    leería como placeholder (mismo patrón que la 0004)."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
