// [T-9.54 · D-45] EL FONDO DEL MAPA: relieve y suelos, con su atribución.
//
// Son CONTEXTO y no dato del incidente: van debajo de todo lo que el incidente
// pinta (superficie, ondas, edificios, puntos medidos), en tonos tenues, y cada
// una con su interruptor. Nada de aquí entra en una decisión: la edafología del
// INEGI es tipo de suelo agrícola, no respuesta sísmica, y se rotula así
// (`D-45 · El precio, declarado`).
//
// TRES REGLAS
// ───────────
// 1. **La atribución sale de UN fichero** (`shared/geodatos/atribuciones.json`),
//    el mismo que leen el PDF y la app. Aquí no se teclea ninguna: una copia se
//    queda atrás el día que cambie la licencia.
// 2. **Los geojson se sirven de `public/` y se pasan por URL**, nunca
//    importados: `import` metería los 5,9 MB de la edafología en el JS de la
//    consola. MapLibre los descarga cuando la fuente se cuelga, y la edafología
//    sólo se cuelga cuando alguien enciende su interruptor.
// 3. **Ningún suelo habla el idioma de la sacudida.** Verde, amarillo y rojo son
//    las bandas del dictamen (`D-43`): un suelo de lago en rojo se leería como
//    «aquí se sacudió fuerte». Los suelos van en azules, violetas y neutros.

import atribuciones from "../../../../shared/geodatos/atribuciones.json";

/** Teselas de elevación de AWS Terrain Tiles (Tilezen), codificación terrarium. */
export const RELIEVE_TILES =
  "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";

/** `BASE_URL` y no `/` a secas: la consola podría servirse bajo un prefijo. */
const BASE = import.meta.env.BASE_URL.endsWith("/")
  ? import.meta.env.BASE_URL
  : `${import.meta.env.BASE_URL}/`;
export const NTC_CDMX_URL = `${BASE}geodatos/ntc_cdmx.geojson`;
export const EDAFOLOGIA_URL = `${BASE}geodatos/edafologia.geojson`;

/** La atribución corta de cada capa, por su clave de interruptor. */
export const ATRIBUCION = {
  relieve: atribuciones.relieve.corta,
  sueloCdmx: atribuciones.ntc_cdmx.corta,
  sueloInegi: atribuciones.edafologia.corta,
} as const;

/** El rótulo del interruptor del INEGI. La negación va EN el mando, no en una nota. */
export const ROTULO_EDAFOLOGIA = "TIPO DE SUELO (INEGI) · no es zonificación sísmica";

/* =====================================================================
   RELIEVE
   ===================================================================== */

export function fuenteRelieve() {
  return {
    type: "raster-dem" as const,
    tiles: [RELIEVE_TILES],
    encoding: "terrarium" as const,
    tileSize: 256,
    maxzoom: 15,
    attribution: ATRIBUCION.relieve,
  };
}

/**
 * El sombreado, TENUE: el mapa base es oscuro y encima van los datos. Con una
 * exageración baja y sin resaltado blanco, el relieve se lee como textura —la
 * cuenca del valle de México, la sierra— sin competir con un solo punto.
 */
export const PAINT_RELIEVE = {
  "hillshade-exaggeration": 0.25,
  "hillshade-shadow-color": "#000000",
  "hillshade-highlight-color": "rgba(255,255,255,0.06)",
  "hillshade-accent-color": "#000000",
};

/* =====================================================================
   ZONIFICACIÓN GEOTÉCNICA DE LA CDMX (NTC)
   ===================================================================== */

/**
 * Las tres zonas, en azules y violetas: nada de verde, amarillo o rojo. La
 * intensidad va del lago (el más oscuro y saturado: es donde el suelo amplifica)
 * a las lomas (el más pálido), que es la lectura que un operador ya trae.
 */
export const COLOR_ZONA_CDMX: Record<"lomas" | "transicion" | "lago", string> = {
  lomas: "#9A7FC0",
  transicion: "#6C8CA8",
  lago: "#3553C9",
};

/** El nombre que se rotula de cada zona (la clave del geojson no lleva tilde). */
const NOMBRE_ZONA_CDMX: Record<keyof typeof COLOR_ZONA_CDMX, string> = {
  lomas: "LOMAS",
  transicion: "TRANSICIÓN",
  lago: "LAGO",
};

export function fuenteSueloCdmx() {
  return { type: "geojson" as const, data: NTC_CDMX_URL, attribution: ATRIBUCION.sueloCdmx };
}

/** `["match", ["get", "zona"], "lomas", …, defecto]` para un mapa clave → valor. */
function porZona(valores: Record<string, string>, defecto: string): unknown[] {
  return ["match", ["get", "zona"], ...Object.entries(valores).flat(), defecto];
}

export const PAINT_SUELO_CDMX = {
  "fill-color": porZona(COLOR_ZONA_CDMX, "rgba(0,0,0,0)"),
  "fill-opacity": 0.18,
  "fill-outline-color": porZona(COLOR_ZONA_CDMX, "rgba(0,0,0,0)"),
};

export const LAYOUT_ROTULO_CDMX = {
  "text-field": porZona(
    Object.fromEntries(Object.entries(NOMBRE_ZONA_CDMX).map(([k, v]) => [k, `ZONA ${v}`])),
    "",
  ),
  "text-size": 10,
};

export const PAINT_ROTULO_CDMX = {
  "text-color": porZona(COLOR_ZONA_CDMX, "#F0F2F5"),
  "text-halo-color": "#0d2034",
  "text-halo-width": 1.4,
};

/* =====================================================================
   EDAFOLOGÍA DEL INEGI
   ===================================================================== */

/**
 * Los grupos WRB que trae el continuo nacional, en orden alfabético. El color se
 * asigna por su posición en esta lista, así que es ESTABLE entre sesiones: el
 * mismo suelo, el mismo tono, siempre.
 */
const GRUPOS_WRB = [
  "AC",
  "AL",
  "AN",
  "AR",
  "ARR",
  "CH",
  "CL",
  "CM",
  "DU",
  "FL",
  "GL",
  "GY",
  "HS",
  "KS",
  "LP",
  "LV",
  "LX",
  "NT",
  "PH",
  "PL",
  "PT",
  "RG",
  "SC",
  "SN",
  "UM",
  "VR",
];

/** Paleta NEUTRA: grises, pizarras y sepias apagados. Ningún verde, amarillo o rojo. */
const PALETA_NEUTRA = ["#7F8A94", "#8C8478", "#6F7C8C", "#8A8290", "#77858A", "#938C82"];

/** Localidad urbana que el INEGI no clasifica, y cuerpo de agua: no son suelos. */
const ZONA_URBANA = "ZU";
const CUERPO_DE_AGUA = "H2O";

export function fuenteEdafologia() {
  return { type: "geojson" as const, data: EDAFOLOGIA_URL, attribution: ATRIBUCION.sueloInegi };
}

export const PAINT_EDAFOLOGIA = {
  "fill-color": [
    "match",
    ["get", "GRUPO1"],
    ...GRUPOS_WRB.flatMap((g, i) => [g, PALETA_NEUTRA[i % PALETA_NEUTRA.length]]),
    ZONA_URBANA,
    "#5A5F66",
    CUERPO_DE_AGUA,
    "#2F4A66",
    "#6E6E6E",
  ],
  "fill-opacity": 0.22,
  "fill-outline-color": "rgba(240,242,245,0.18)",
};

/** Lo que dice el popup de un polígono de la edafología. */
export function textoDelSuelo(p: Record<string, unknown>): string {
  const grupo = typeof p["GRUPO1"] === "string" ? p["GRUPO1"] : null;
  const nombre = typeof p["N_G1"] === "string" ? p["N_G1"] : null;
  if (grupo === ZONA_URBANA) return "LOCALIDAD · ZONA URBANA SIN CLASIFICAR (INEGI)";
  if (grupo === CUERPO_DE_AGUA) return "CUERPO DE AGUA (INEGI)";
  if (grupo === null || nombre === null) return "TIPO DE SUELO SIN DATO";
  return `${nombre} (${grupo}) · TIPO DE SUELO INEGI · NO ES ZONIFICACIÓN SÍSMICA`;
}
