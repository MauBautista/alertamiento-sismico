"""T-7.24 · el mini-ShakeMap de un incidente se CALCULA una vez y se lee muchas

## Por qué es una tabla y no un cálculo en la petición

El mapa de la sacudida no es en vivo (`design/BLOQUE-IV-ARQUITECTURA.md §A.4`):
se calcula por evento, cuando hay con qué calcularlo. Recalcularlo en cada
petición tendría tres consecuencias, y ninguna buena:

* **Dos operadores verían mapas distintos del mismo sismo** si entre sus dos
  peticiones llega el epicentro del catálogo, y ninguno sabría cuál es el que se
  citó en la reunión.
* El PDF del dictamen y la consola dibujarían cada uno *su* mapa. Este
  repositorio ya midió lo que pasa con dos caminos a los mismos números.
* Una petición de lectura acabaría corriendo la tabla por estación entera —una
  consulta de features por inmueble— con el operador esperando.

Se persiste el SNAPSHOT: lo que se calculó, cuándo, con qué ley y con qué
epicentro. `calculado_en` **sí** se refresca al recalcular, a diferencia de
`fw_releases.released_at`: aquí la fecha del cálculo ES el dato, porque dice con
qué información se hizo el mapa.

## Las columnas, y la que parece redundante y no lo es

* ``estado`` — vocabulario cerrado de TRES: ``completo`` / ``solo_observado`` /
  ``sin_datos``. **No hay ``pendiente``**: ése es la AUSENCIA de fila, y lo pone
  el lector. Meterlo en el CHECK dejaría dos formas de decir lo mismo y un día
  habría filas `pendiente` que nadie recalcula.
* ``ley`` — `'ATTEN-LAW v1'` o NULL. NULL significa que **no se modeló**, no que
  se modeló con otra cosa. Sin esto, un mapa viejo se leería con la ley de hoy.
* ``epicentro`` — jsonb `{lat,lon,depth_km,magnitud,fuente,procedencia,
  catalog_key}` o NULL. ``fuente`` (quién lo localizó) y ``procedencia`` (el
  estado del glosario) son cosas distintas y las dos hacen falta: el centroide
  de nuestro propio cuórum es un epicentro NUESTRO y presentarlo sin decirlo lo
  confundiría con la solución de una agencia.
* ``cobertura_km`` — el radio de representatividad vigente CUANDO se calculó.
  Va en la fila y no se lee de los ajustes al pintar: un mapa impreso en un
  dictamen firmado no puede cambiar de significado porque alguien suba el
  número seis meses después.
* ``puntos`` — capa 1 (observado) + su modelado + su residuo, por inmueble, y
  el voto de cuórum de ese inmueble (`voto_contado`), que es lo que distingue al
  que participó del que sólo estaba ahí.
* ``anillos`` — el CENSO de los niveles de la capa 2 como NÚMEROS:
  `[{umbral, pga_g, radio_km, motivo, radio_max_km}]`. Una sola lista para los
  dibujados (`radio_km` no nulo) y los suprimidos (`motivo` no nulo), para que
  nadie pueda leer los anillos sin enterarse de qué umbral falta y por qué: un
  anillo ausente sin explicación se lee como «ese umbral no existía». La
  geometría del círculo la materializa quien pinta. Guardar 64 vértices sería
  guardar un dibujo, no un modelo — y un dibujo hecho a una latitud no vale a
  otra.

⚠️ **El radio va en kilómetros, y ésa es media ficha.** La guarda que T-7.24
sustituye nació de dos capas de MapLibre con `circle-radius` en PÍXELES DE
PANTALLA rotuladas «INTENSIDAD MMI»: el mismo anillo afirmaba ~22 km a zoom 8.5 y
~1 km a zoom 13. Una unidad de pantalla no puede sostener una afirmación física.

## Idempotencia (regla de oro 3)

La clave natural es el incidente, y es la PRIMARY KEY: recalcular hace
`ON CONFLICT (incident_id) DO UPDATE` y no puede duplicar ni dejar dos verdades
sobre el mismo sismo.

## Escritura: el worker y nadie más

`takab_app` recibe **solo SELECT**, y encima el REVOKE — que no es redundante,
está MEDIDO: la `0001` aplica `db/schema.sql` y DESPUÉS concede `ALL TABLES` a
`takab_app`, así que en una base construida desde cero la API salía con INSERT,
UPDATE y DELETE sobre tablas que el esquema sólo le dejaba leer. Es el modo de
fallo que destapó la 0068 y el que ya había destapado a `takab_app` con SELECT
sobre hashes de credencial: **verde en local no es verde en la nube**.

Sin política de escritura, ni con GRANT podría: escribe `takab_ingest`
(BYPASSRLS), que es el rol del worker de incidentes.

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+: `db/schema.sql` es el
esquema final y la `0001` lo aplica ANTES, así que esta migración se encuentra su
propio trabajo hecho.

Revision ID: 0069_mapa_de_sacudida
Revises: 0068_consulta_al_catalogo
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0069_mapa_de_sacudida"
down_revision: str | None = "0068_consulta_al_catalogo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
-- Objeto NUEVO ⇒ `SET ROLE takab_migrator` (invariante de dueños): las tablas de
-- negocio son de un rol NO-superusuario, sin lo cual `FORCE ROW LEVEL SECURITY`
-- seria inverificable. Los GRANT y los ALTER sobre tablas PREEXISTENTES van
-- fuera, como usuario de conexion.
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS incident_shakemap (
  incident_id  uuid PRIMARY KEY REFERENCES incidents(incident_id) ON DELETE CASCADE,
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  calculado_en timestamptz NOT NULL DEFAULT now(),
  estado       text NOT NULL CHECK (estado IN ('completo','solo_observado','sin_datos')),
  ley          text,
  epicentro    jsonb,
  cobertura_km numeric NOT NULL CHECK (cobertura_km > 0),
  puntos       jsonb NOT NULL DEFAULT '[]'::jsonb,
  anillos      jsonb NOT NULL DEFAULT '[]'::jsonb
);

RESET ROLE;

COMMENT ON TABLE incident_shakemap IS
  '[T-7.24] El mini-ShakeMap de UN incidente, calculado por el worker y leido '
  'por la consola y por el PDF. Tres capas que no se mezclan: observado '
  '(puntos medidos), modelado (ATTEN-LAW v1, anillos) y residuo por punto.';
COMMENT ON COLUMN incident_shakemap.estado IS
  'completo / solo_observado / sin_datos. `pendiente` NO cabe aqui: es la '
  'AUSENCIA de fila y lo declara el lector.';
COMMENT ON COLUMN incident_shakemap.ley IS
  'La ley con que se modelo, o NULL si NO se modelo. NULL no significa "otra '
  'ley": significa que no hubo capa 2 porque faltaba epicentro o magnitud.';
COMMENT ON COLUMN incident_shakemap.cobertura_km IS
  'Radio de representatividad de un inmueble instrumentado VIGENTE al calcular. '
  'Va en la fila para que un mapa ya impreso no cambie de significado si manana '
  'alguien sube el ajuste.';
COMMENT ON COLUMN incident_shakemap.anillos IS
  'CENSO de los niveles de la capa 2: [{umbral, pga_g, radio_km, motivo, '
  'radio_max_km}], radio EPICENTRAL en KM. radio_km NULL <=> motivo NO NULL: ese '
  'nivel NO se dibuja (bajo_la_superficie / no_invertible / fuera_del_alcance) y '
  'se DECLARA, porque un anillo ausente sin explicacion se lee como "ese umbral '
  'no existia". Los umbrales son los de la banda del inmueble, derivados de '
  'felt.Thresholds. La geometria del circulo la materializa quien pinta; guardar '
  'vertices seria guardar un dibujo. Y el radio va en km, jamas en pixeles de '
  'pantalla: un anillo que afirma "aqui el modelo predice 0.02 g" tiene que '
  'seguir afirmandolo a cualquier zoom.';
COMMENT ON COLUMN incident_shakemap.puntos IS
  'Capa 1 + capa 3: un punto por inmueble instrumentado con su PGA y su PGV '
  'medidas, la PGA que el modelo predice a su distancia, el residuo '
  'log10(medida/modelada) y si su voto conto en el cuorum (voto_contado). '
  'pga_g NULL = no publico nada en la ventana; NO es 0 g (regla de oro 7).';

ALTER TABLE incident_shakemap ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_shakemap FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ism_read ON incident_shakemap;
CREATE POLICY ism_read ON incident_shakemap FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());

-- Solo SELECT para la API: «el worker es el unico escritor» convertido en
-- privilegio en vez de en costumbre. Y no hay politica de escritura, asi que ni
-- con GRANT podria: escribe `takab_ingest` (BYPASSRLS).
GRANT SELECT ON incident_shakemap TO takab_app;
GRANT SELECT, INSERT, UPDATE ON incident_shakemap TO takab_ingest;
-- ⚠️ El REVOKE no es redundante, y esta MEDIDO (0068, 2026-09-20): la `0001`
-- termina con `GRANT ... ON ALL TABLES IN SCHEMA public TO takab_app` y para
-- entonces esta tabla YA existe (la trae `db/schema.sql`), asi que en una base
-- NUEVA `takab_app` saldria con INSERT, UPDATE y DELETE. En una base EXISTENTE
-- —donde la crea esta migracion, despues de aquel GRANT— no pasa. O sea: el
-- privilegio de mas aparece solo en la nube, que es el modo de fallo que este
-- repositorio lleva tres fichas cazando.
REVOKE INSERT, UPDATE, DELETE ON incident_shakemap FROM takab_app;
"""

_DOWN = """
DROP TABLE IF EXISTS incident_shakemap;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
