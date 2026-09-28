// [T-9.54 · D-45] El FONDO del mapa: relieve y suelos, con su atribución.
//
// Lo que se prueba aquí no es MapLibre: es que cada capa diga de dónde sale
// (la atribución la da UN fichero), que la paleta del suelo no hable el idioma
// de la sacudida y que los 5,9 MB de la edafología no viajen en el bundle.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import atribuciones from "../../../../shared/geodatos/atribuciones.json";
import {
  ATRIBUCION,
  COLOR_ZONA_CDMX,
  EDAFOLOGIA_URL,
  NTC_CDMX_URL,
  RELIEVE_TILES,
  ROTULO_EDAFOLOGIA,
  fuenteEdafologia,
  fuenteRelieve,
  fuenteSueloCdmx,
  textoDelSuelo,
} from "./capasDeFondo";

/** El matiz (0–360) de un `#rrggbb`. */
function matiz(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  if (d === 0) return 0;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("[T-9.54] el relieve", () => {
  it("es la fuente raster-dem de AWS Terrain Tiles, en terrarium", () => {
    const f = fuenteRelieve();
    expect(f).toMatchObject({
      type: "raster-dem",
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 15,
    });
    expect(f.tiles).toEqual([
      "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
    ]);
    expect(RELIEVE_TILES).toBe(f.tiles[0]);
  });
});

describe("[T-9.54] las atribuciones salen de UN fichero", () => {
  it("cada fuente cita la `corta` de `shared/geodatos/atribuciones.json`, no una copia", () => {
    // Si alguien cambia el texto del JSON, esto lo sigue: se compara contra el
    // JSON importado, no contra una cadena tecleada aquí.
    expect(fuenteRelieve().attribution).toBe(atribuciones.relieve.corta);
    expect(fuenteSueloCdmx().attribution).toBe(atribuciones.ntc_cdmx.corta);
    expect(fuenteEdafologia().attribution).toBe(atribuciones.edafologia.corta);
    expect(ATRIBUCION).toEqual({
      relieve: atribuciones.relieve.corta,
      sueloCdmx: atribuciones.ntc_cdmx.corta,
      sueloInegi: atribuciones.edafologia.corta,
    });
  });

  it("y el módulo NO escribe ninguna atribución a mano", () => {
    const src = readFileSync(
      resolve(process.cwd(), "src/features/console/capasDeFondo.ts"),
      "utf8",
    );
    for (const clave of ["relieve", "ntc_cdmx", "edafologia"] as const) {
      const corta = (atribuciones as unknown as Record<string, { corta: string }>)[clave].corta;
      expect(src, `la atribución de ${clave} está copiada en el código`).not.toContain(corta);
    }
  });
});

describe("[T-9.54] los suelos", () => {
  it("la zonificación de la CDMX y la edafología se sirven de `public/`, no del bundle", () => {
    expect(NTC_CDMX_URL).toMatch(/\/geodatos\/ntc_cdmx\.geojson$/);
    expect(EDAFOLOGIA_URL).toMatch(/\/geodatos\/edafologia\.geojson$/);
    // La fuente recibe la URL (MapLibre la descarga cuando se cuelga): nunca el
    // objeto importado, que metería 5,9 MB en el JS de la consola.
    expect(fuenteEdafologia().data).toBe(EDAFOLOGIA_URL);
    expect(fuenteSueloCdmx().data).toBe(NTC_CDMX_URL);
    const src = readFileSync(
      resolve(process.cwd(), "src/features/console/capasDeFondo.ts"),
      "utf8",
    );
    expect(src).not.toMatch(/import[^;]*geojson/);
  });

  it("las tres zonas de la CDMX tienen color, y NINGUNO es verde, amarillo o rojo", () => {
    // Verde/amarillo/rojo son las bandas de la SACUDIDA (`D-43`). Un suelo de
    // lago pintado de rojo se leería como «aquí se sacudió fuerte».
    expect(Object.keys(COLOR_ZONA_CDMX).sort()).toEqual(["lago", "lomas", "transicion"]);
    for (const [zona, color] of Object.entries(COLOR_ZONA_CDMX)) {
      const h = matiz(color);
      expect(h, `${zona} (${color}) cae fuera de los azules y violetas`).toBeGreaterThanOrEqual(
        180,
      );
      expect(h, `${zona} (${color}) cae fuera de los azules y violetas`).toBeLessThanOrEqual(300);
    }
  });

  it("el rótulo del INEGI dice que NO es zonificación sísmica", () => {
    expect(ROTULO_EDAFOLOGIA).toBe("TIPO DE SUELO (INEGI) · no es zonificación sísmica");
  });

  it("el popup del suelo dice su nombre, y que no es zonificación sísmica", () => {
    expect(textoDelSuelo({ GRUPO1: "VR", N_G1: "VERTISOL" })).toBe(
      "VERTISOL (VR) · TIPO DE SUELO INEGI · NO ES ZONIFICACIÓN SÍSMICA",
    );
    // `ZU` no es un suelo: es una localidad que el INEGI no clasifica. Decir
    // «LOCALIDAD» a secas invitaría a leerlo como un tipo.
    expect(textoDelSuelo({ GRUPO1: "ZU", N_G1: "LOCALIDAD" })).toMatch(/SIN CLASIFICAR/);
    expect(textoDelSuelo({})).toMatch(/SIN DATO/);
  });
});
