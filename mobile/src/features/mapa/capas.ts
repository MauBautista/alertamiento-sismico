// [T-9.63 · T-9.65 · D-46 · D-44] LO QUE DIBUJA EL MAPA DE LA APP, en puro.
//
// Los sismos llevan el radio y el color YA calculados con `features/sismos/escala`
// —la misma función que pinta la lista— en vez de reescribir la escala como
// expresión de MapLibre: una segunda copia de los umbrales es la que acaba
// divergiendo de la primera.
//
// La superficie es la de la nube (`shakemap/raster.py`, una celda = un píxel) y
// aquí sólo se decide DÓNDE se pega y CÓMO se rotula. Gemelas de
// `web/src/features/console/superficie.ts` (`esquinasDeBbox`, `rotuloEstimado`):
// la consola y la app tienen que decir lo mismo del mismo sismo.
import type { SismoCercanoOut, SuperficieMovilOut } from "@takab/sdk";
import type { Feature, FeatureCollection, Point } from "geojson";

import { colorDeMmi, radioDeMagnitud } from "@/features/sismos/escala";
import { palette } from "@/ui/theme";

/** El mismo estilo base que la consola (`MapPanel.MAP_STYLE_URL`). */
export const ESTILO_BASE = "https://tiles.openfreemap.org/styles/dark";

/**
 * El crédito del mapa base, VISIBLE. El SDK nativo lo esconde tras un botón (i);
 * OpenStreetMap pide que se vea, y la consola ya lo pinta a la vista.
 */
export const ATRIBUCION_BASE = "Mapa © OpenStreetMap · OpenFreeMap · MapLibre";

/**
 * Lo que cada punto lleva ya resuelto. El punto y la colección son los tipos de
 * GeoJSON (`@types/geojson`), no una forma escrita aquí: `sdkTypeParity` veta
 * redeclarar a mano la forma de un tipo del SDK, y `{type, geometry, properties}`
 * es la de `PuntoFeature`.
 */
type PropiedadesSismo = { mag: number; radio: number; color: string };

export type ColeccionSismos = FeatureCollection<Point, PropiedadesSismo>;

/** Los sismos como puntos, del más chico al más grande (el grande queda ENCIMA). */
export function sismosGeoJSON(items: readonly SismoCercanoOut[]): ColeccionSismos {
  const features = items
    .map(
      (s): Feature<Point, PropiedadesSismo> => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: {
          mag: s.magnitude,
          radio: radioDeMagnitud(s.magnitude),
          // Sin estimación no se inventa un grado: el neutro, no el blanco del I.
          color: colorDeMmi(s.en_tu_inmueble.mmi_estimada) ?? palette.fg3,
        },
      }),
    )
    .sort((a, b) => a.properties.mag - b.properties.mag);
  return { type: "FeatureCollection", features };
}

export type Esquinas = [[number, number], [number, number], [number, number], [number, number]];

/**
 * Las cuatro esquinas de la imagen: arriba-izquierda, arriba-derecha,
 * abajo-derecha, abajo-izquierda (la fila 0 del PNG es el norte). `null` si el
 * bbox no es un rectángulo legible: pegarla sobre esquinas invertidas la
 * voltearía y nada en pantalla lo delataría.
 */
export function esquinasDeBbox(bbox: readonly number[]): Esquinas | null {
  if (bbox.length !== 4 || !bbox.every(Number.isFinite)) return null;
  const [oeste, sur, este, norte] = bbox;
  if (!(oeste < este) || !(sur < norte)) return null;
  if (Math.abs(oeste) > 180 || Math.abs(este) > 180) return null;
  if (Math.abs(sur) > 90 || Math.abs(norte) > 90) return null;
  return [
    [oeste, norte],
    [este, norte],
    [este, sur],
    [oeste, sur],
  ];
}

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

/** El rótulo que la superficie lleva SIEMPRE que se enseña (`D-44`). */
export function rotuloEstimado(sup: SuperficieMovilOut): string {
  return (
    `ESTIMADO a partir de ${plural(sup.n_sensores, "sensor", "sensores")} ` +
    `(${plural(sup.n_calibrados, "calibrado", "calibrados")}) · ` +
    "MMI estimada (Wald 1999), no observada"
  );
}

/** Las líneas del pie: el mapa base siempre, y la fuente de los sismos si llegó. */
export function pieDelMapa(atribucionSismos: string | undefined): string[] {
  return atribucionSismos ? [ATRIBUCION_BASE, atribucionSismos] : [ATRIBUCION_BASE];
}
