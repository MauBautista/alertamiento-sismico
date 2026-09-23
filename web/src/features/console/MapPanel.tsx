// Mapa GIS real del live wall (T-1.27): MapLibre GL sobre OpenFreeMap dark.
// Desviación RATIFICADA: mapa vectorial real, no el SVG esquemático del mock.
//
// Qué pinta este mapa, y qué NO (todo viene derivado de /telemetry/map/state):
//
//  · Cada punto es un EDIFICIO, coloreado por la SACUDIDA QUE ÉL MIDIÓ (`felt`),
//    clasificada con los umbrales de su propio rule_set — los mismos que arman
//    sus actuadores. NO es la severidad de la alerta: una alerta SASMEX abre el
//    incidente en `critical` sin medir nada de lo que pasa aquí (el WR-1 es un
//    booleano), y pintar el inmueble de rojo por eso diría algo falso sobre él.
//  · [T-2.46] El ENLACE con el gabinete va en OTRO canal: opacidad + núcleo hueco
//    + glifo, jamás color (el color ya lo ocupa `felt`). Un punto con el enlace
//    caído tiene que verse como lo que es: un color que ya no es una lectura viva.
//    Y `SIN GABINETE` no se colapsa con `SIN ENLACE`.
//  · El EPICENTRO va en su propia capa, con otra forma y otro color: es dónde se
//    ORIGINÓ el sismo y no es ningún edificio. Sin evento localizado no se dibuja
//    y la leyenda lo declara — no se planta un punto inventado.
//  · [T-2.47] Con un epicentro LOCALIZADO y FRESCO se animan las líneas
//    epicentro→estación y los frentes P/S. Los radios son FÍSICOS (km) y se
//    convierten a píxeles con la escala del zoom: el dibujo NO cambia de
//    significado con la rueda del ratón. Ver `wavefront.ts`.
//  · [T-7.24] El MAPA DE LA SACUDIDA del incidente (`shakemap`) pinta lo MEDIDO
//    por cada inmueble y lo MODELADO por la ley de atenuación, y nunca con la
//    misma codificación: disco relleno con su valor vs anillo geográfico de
//    trazo discontinuo, con la procedencia dentro de cada rasgo.
//  · Sigue sin haber intensidad sísmica INTERPOLADA: ni isosistas, ni bandas
//    MMI, ni una superficie continua entre estaciones. Lo que hay son puntos
//    medidos, un modelo rotulado como modelo y el residuo entre los dos. Ver el
//    comentario en la carga de capas.
//  · NO hay cuenta regresiva T-MINUS ni magnitud preliminar (`CLAUDE.md §8`).

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CatalogEarthquakeOut, MapEpicenter, MapSiteState } from "@takab/sdk";

import { observeMapResize } from "../../lib/maplibre";
import { utcStamp } from "../../lib/time";
import { useReducedMotion } from "../../lib/useReducedMotion";
import {
  LINK_GLYPH,
  LINK_DEGRADADO,
  LINK_OPERATIVO,
  LINK_SIN_ENLACE,
  LINK_SIN_GABINETE,
  coreOpacity,
  haloOpacity,
  isLinkDown,
  siteLink,
} from "./link";
import { esDeDemostracion, ROTULO_DEMO } from "../fleet/datosDeDemostracion";
import { sitesInBounds, type ViewBounds } from "./stats";
import {
  ARRIVAL_BURST_S,
  DASH_FRAMES,
  animatableEpicenters,
  arrivalSeconds,
  dashFrameIndex,
  epicenterLinks,
  kmToPixels,
  staticRings,
  waveRadiiKm,
  WAVE_MAX_AGE_S,
} from "./wavefront";
import { haversineKm } from "../fleet/geo";
import {
  PGA_SIN_COBERTURA,
  coberturaFeatureCollection,
  colorDeBanda,
  modeladoFeatureCollection,
  nivelesDe,
  observadoFeatureCollection,
  sinProcedencia,
  vistaSacudida,
  type ShakemapOut,
} from "./shakemap";

/** Lo que `GeoJSONSource.setData` acepta. El namespace global `GeoJSON` no está
 * en el `types` del tsconfig: se deriva del propio tipo de MapLibre. */
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

export const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/dark";

/**
 * [T-6.15] LA PILA DE FUENTES DE LOS GLIFOS DEL MAPA, dicha en voz alta.
 *
 * Ninguna capa la declaraba, así que MapLibre usaba su defecto de
 * especificación —`["Open Sans Regular", "Arial Unicode MS Regular"]`— y
 * `openfreemap` NO SIRVE ese par: medido el 2026-09-10, tres rangos en 404 por
 * sesión (`0-255`, `8704-8959` y `9472-9727`, que son justo el latín y los dos
 * bloques donde viven `◐`, `◇` y `✳`). El estilo de openfreemap sirve
 * `Noto Sans Regular`, que responde 200.
 *
 * No es cosmético: los tres rangos que fallaban son los del rótulo del sitio,
 * el glifo de enlace y el glifo de sacudida que T-6.09 y T-6.10 pusieron en el
 * mapa precisamente para que el daltónico no dependiera del matiz.
 */
export const TEXT_FONT = ["Noto Sans Regular"];

/** Estilo de EMERGENCIA 100% local (T-1.50): si los tiles remotos no llegan
 * (sin internet, CDN caído), el mapa base degrada a fondo navy PERO las capas
 * GeoJSON de sitios siguen pintando — las estaciones jamás desaparecen. El
 * badge "SIN MAPA BASE" declara la degradación (regla de oro 7). */
export const FALLBACK_STYLE = {
  version: 8 as const,
  name: "takab-fallback",
  sources: {},
  layers: [{ id: "bg", type: "background" as const, paint: { "background-color": "#0d2034" } }],
};

/** Centro por defecto: Puebla (flota dev); el mapa hace fit a los sitios. */
const DEFAULT_CENTER: [number, number] = [-98.2, 19.04];
const DEFAULT_ZOOM = 8.5;
const PULSE_PERIOD_MS = 1_600;

/** [T-2.47] Compuerta del rAF: 20 fps. Por encima no se percibe y sí se paga. */
export const FRAME_MS = 50;

/**
 * Fotograma del pulso a partir del tiempo transcurrido (ms). El timestamp de
 * requestAnimationFrame puede ser MARGINALMENTE anterior al `start` capturado
 * (vsync del frame previo), lo que daría un delta negativo y una opacidad > 1
 * que MapLibre RECHAZA (validación estricta 0..1). Se clampa el delta a >= 0 y
 * la opacidad queda garantizada en (0,1]. Motion lineal (sin bounce).
 */
export function pulseAt(deltaMs: number): { radius: number; strokeOpacity: number } {
  const elapsed = deltaMs > 0 ? deltaMs : 0;
  const phase = (elapsed % PULSE_PERIOD_MS) / PULSE_PERIOD_MS; // [0, 1)
  return { radius: 15 + phase * 45, strokeOpacity: 1 - phase };
}

/**
 * [A-060 · T-8.09] El faro con `prefers-reduced-motion`: QUIETO y PUESTO.
 *
 * El interruptor apaga el MOVIMIENTO, no la información — la misma regla que el
 * anillo de arribo (T-7.18): el edificio sigue diciendo «disparé», con un anillo
 * fijo a medio camino del recorrido del pulso y visible de sobra. Hasta esta
 * ficha el loop ignoraba la preferencia y la leyenda decía «ANILLOS ESTÁTICOS»
 * mientras el faro seguía expandiéndose cada 1.6 s.
 */
export const PULSE_STILL: { radius: number; strokeOpacity: number } = {
  radius: 22,
  strokeOpacity: 0.6,
};

/** El fotograma del faro, con la preferencia de movimiento DENTRO de la decisión. */
export function pulseFrame(
  deltaMs: number,
  reducedMotion: boolean,
): { radius: number; strokeOpacity: number } {
  return reducedMotion ? PULSE_STILL : pulseAt(deltaMs);
}

/** Color por SACUDIDA MEDIDA en el inmueble (`felt`), no por severidad de la
 * alerta. Un aviso SASMEX abre el incidente en `critical` sin haber medido nada
 * de lo que pasa AQUÍ (el WR-1 es un booleano): pintar el edificio de rojo por
 * eso afirmaría algo falso sobre él. `unknown` (sin dato) es GRIS y jamás verde:
 * "no reportó" no es "no se movió" (regla de oro 7). */
export const FELT_COLOR: Record<string, string> = {
  trip: "#FF5252", // superó el umbral de DISPARO de su rule_set
  watch: "#FFC107", // superó el de cautela
  normal: "#00E676", // midió, y por debajo de cautela
  unknown: "#7A8DA6", // no hay medida: ausencia de dato
};

/**
 * [T-6.09] La banda, en FORMA. El color solo no bastaba: `watch` (#FFC107) y
 * `normal` (#00E676) llevaban el mismo radio y bajo deuteranopía —el 6 % de
 * los hombres— los dos tiran a un amarillo parecido. Son la diferencia entre
 * «superó cautela» y «bajo umbral».
 *
 * El alfabeto es propio y no reusa el del ENLACE (`⊘ ▲ ○`): un ▲ que según la
 * capa signifique una cosa u otra no es un glifo, es una adivinanza. Y sigue
 * la misma doctrina que aquél — el que no tiene nada que decir no dice nada,
 * así que `normal` va vacío y el mapa tranquilo se queda sin ruido. `unknown`
 * SÍ marca: «no reportó» no es «no se movió» (regla de oro 7), y hasta hoy eso
 * lo decía únicamente un gris.
 */
export const FELT_GLYPH: Record<string, string> = {
  trip: "!!",
  watch: "!",
  normal: "",
  unknown: "?",
};

export const EPICENTER_COLOR = "#E040FB";

/** [T-2.28] Catálogo HISTÓRICO de referencia (1985–2022): color y símbolo (◇)
 * propios — jamás se confunde ni con un edificio ni con el ✳ de un incidente. */
export const CATALOG_COLOR = "#7CE7FF";

/** [T-2.47] Frentes de onda: la P (aviso) en cian, la S (la que daña) en ámbar. */
export const WAVE_P_COLOR = "#7CE7FF";
export const WAVE_S_COLOR = "#FFC107";

/** Banda de sacudida medida del sitio (la deriva el server; el default es honesto). */
export function siteFelt(site: MapSiteState): string {
  return site.felt ?? "unknown";
}

type FeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: Record<string, unknown>;
  }>;
};

/** GeoJSON de los EDIFICIOS, coloreados por lo que cada uno sintió. */
export function sitesToFeatureCollection(sites: MapSiteState[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: sites.map((site) => {
      const felt = siteFelt(site);
      const link = siteLink(site);
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [site.lon, site.lat] },
        properties: {
          site_id: site.site_id,
          name: site.name,
          felt,
          color: FELT_COLOR[felt] ?? FELT_COLOR.unknown,
          // [T-6.09] La MISMA banda, en el canal de la forma. Un `felt` que el
          // server estrene cae en `unknown` por los dos canales a la vez: color
          // y glifo no pueden decir cosas distintas del mismo edificio.
          felt_glyph: FELT_GLYPH[felt] ?? FELT_GLYPH.unknown,
          // El halo y el pulso marcan al que SINTIÓ el disparo.
          tripped: felt === "trip",
          // Sin calibrar el PGA es RELATIVO: el borde punteado lo declara y la
          // UI no puede llamarlo una intensidad física.
          calibrated: site.calibrated === true,
          // [T-2.46] Enlace: canal PROPIO. `link_down` vacía el núcleo (queda un
          // aro), la opacidad apaga el punto y el glifo nombra el estado. Nada de
          // esto toca `color`, que sigue diciendo exclusivamente qué se midió.
          link,
          link_down: isLinkDown(link),
          link_glyph: LINK_GLYPH[link],
          link_opacity: coreOpacity(link),
          link_halo_opacity: haloOpacity(link),
          // [T-5.05] Sitio de DEMOSTRACIÓN. Se deriva del código —un hecho del
          // dato— y no de una columna nueva: la convención del seed ya existe y
          // duplicarla sería una segunda verdad. Un prospecto veía 21 sitios
          // idénticos en este mapa, de los cuales 20 no existen.
          demo: esDeDemostracion(site.code),
          demo_glyph: esDeDemostracion(site.code) ? ROTULO_DEMO : "",
        },
      };
    }),
  };
}

/** Los edificios que superaron su umbral de disparo (fuente del pulso). */
export function trippedFeatures(sites: MapSiteState[]): FeatureCollection {
  return sitesToFeatureCollection(sites.filter((s) => siteFelt(s) === "trip"));
}

/** GeoJSON del EPICENTRO: dónde se originó el sismo. NUNCA es un edificio. */
export function epicentersToFeatureCollection(epicenters: MapEpicenter[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: epicenters.map((e) => {
      // La magnitud es opcional a propósito: el WR-1 no la entrega y muchos eventos
      // no la tienen. Sin ella se rotula el evento, no un número falso.
      const base = e.magnitude !== null ? `M ${e.magnitude.toFixed(1)}` : "EPICENTRO";
      // Corroboración (T-1.71): N estaciones que formaron el evento por quórum. Solo
      // `local_quorum` la trae (`meta.node_count`); sin ella se rotula solo el evento.
      const conNodos = e.node_count != null ? `${base} · ${e.node_count} est.` : base;
      // [T-7.18] Un epicentro de 2017 pintado sin decir que es una reproducción
      // es la mentira más cara que puede contar esta pantalla. El rótulo lo dice
      // SIEMPRE y en primer lugar: quien mire el ◇ no puede leer la magnitud sin
      // leer que es una reproducción.
      const label = e.reproduccion === true ? `REPRODUCCIÓN · ${conNodos}` : conNodos;
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [e.lon, e.lat] },
        properties: {
          event_id: e.event_id,
          node_count: e.node_count ?? null,
          reproduccion: e.reproduccion === true,
          label,
        },
      };
    }),
  };
}

/**
 * [T-6.14] El rótulo de un sismo del catálogo, en UN solo sitio.
 *
 * El ◇ del mapa y el aviso de «comparativa armada» tienen que nombrar el mismo
 * sismo con las mismas palabras: con trece diamantes iguales en pantalla, dos
 * rótulos distintos para el mismo evento se leen como dos eventos.
 */
export function catalogLabel(q: CatalogEarthquakeOut): string {
  return `M ${q.magnitude.toFixed(1)} · ${q.origin_time.slice(0, 4)} · ${q.source}`;
}

/** [T-2.28] GeoJSON del catálogo histórico. Los "gemelos" SSN/USGS del mismo sismo
 * se pintan AMBOS: sus ~28 km de separación son dato honesto del catálogo. */
export function catalogToFeatureCollection(
  items: CatalogEarthquakeOut[],
  selectedId: string | null,
): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items.map((q) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [q.lon, q.lat] },
      properties: {
        ref_id: q.ref_id,
        label: catalogLabel(q),
        selected: q.ref_id === selectedId,
      },
    })),
  };
}

/**
 * [T-7.18] EL ARRIBO POR ESTACIÓN: un punto sobre cada edificio, con el segundo
 * en que la onda S le llega.
 *
 * El instante NO viene del servidor: sale del mismo frente que el mapa está
 * dibujando. Si el anillo se encendiera con un campo del snapshot y el frente se
 * calculara aquí, una estación podría iluminarse mientras el frente se ve pasando
 * por otro sitio — dos relojes para el mismo suceso y ninguna forma de saber cuál
 * miente. El arribo MEDIDO, que es con lo que se contrasta, está en la tabla de
 * `T-7.17`, que es donde se compara.
 */
export function arrivalsFeatureCollection(
  epicenters: MapEpicenter[],
  sites: MapSiteState[],
): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: epicenters.flatMap((e) =>
      sites.map((s) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [s.lon, s.lat] as [number, number] },
        properties: {
          event_id: e.event_id,
          site_id: s.site_id,
          arrival_s: arrivalSeconds(
            haversineKm({ lon: e.lon, lat: e.lat }, { lon: s.lon, lat: s.lat }),
          ),
        },
      })),
    ),
  };
}

/**
 * [T-2.47] Anillos QUIETOS de `prefers-reduced-motion`, ya en píxeles.
 *
 * Se recalcula en `zoomend` porque el radio es FÍSICO: sin recalcular, el mismo
 * anillo afirmaría 37 km a un zoom y 300 km a otro — el defecto exacto que se
 * documentó al borrar las bandas MMI de este archivo.
 */
export function staticRingsFeatureCollection(
  epicenters: MapEpicenter[],
  zoom: number,
): FeatureCollection {
  const rings = staticRings();
  return {
    type: "FeatureCollection",
    features: epicenters.flatMap((e) =>
      rings.map((ring) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [e.lon, e.lat] as [number, number] },
        properties: {
          event_id: e.event_id,
          phase: ring.phase,
          label: ring.label,
          radius_px: kmToPixels(ring.km, e.lat, zoom),
        },
      })),
    ),
  };
}

/** [T-2.50] Capas conmutables del wall. Todas ON salvo el catálogo histórico
 * (el wall es operativo; la referencia histórica se pide, no se impone). */
export interface LayerToggles {
  stations: boolean;
  epicenters: boolean;
  catalog: boolean;
  link: boolean;
  waves: boolean;
  /** [T-7.24] El mini-ShakeMap del incidente: lo medido y lo modelado. */
  shakemap: boolean;
}

export const DEFAULT_LAYERS: LayerToggles = {
  stations: true,
  epicenters: true,
  catalog: false,
  link: true,
  waves: true,
  // ON, pero sólo se ve cuando una superficie ALIMENTA el mapa de sacudida: sin
  // la prop no hay ni botón ni leyenda (igual que el catálogo histórico sin su
  // prop). Un interruptor que no conmuta nada es ruido en un wall operativo.
  shakemap: true,
};

const LAYERS_OF: Record<keyof LayerToggles, string[]> = {
  stations: ["site-halo", "site-core", "pulse"],
  epicenters: ["epicenter-halo", "epicenter-mark", "epicenter-label"],
  catalog: ["catalog-mark", "catalog-label"],
  link: ["site-link"],
  waves: ["wave-link", "wave-p", "wave-s", "wave-static-ring", "wave-static-label"],
  shakemap: [
    "shakemap-cobertura",
    "shakemap-anillo",
    "shakemap-anillo-nivel",
    "shakemap-punto",
    "shakemap-punto-valor",
  ],
};

const LAYER_LABEL: Record<keyof LayerToggles, string> = {
  stations: "ESTACIONES",
  epicenters: "EPICENTROS",
  catalog: "CATÁLOGO",
  link: "ENLACE",
  waves: "ONDAS",
  shakemap: "SACUDIDA",
};

export interface MapPanelProps {
  sites: MapSiteState[];
  epicenters: MapEpicenter[];
  onSelectSite: (siteId: string) => void;
  /** Catálogo histórico (T-2.28); sin la prop, la capa no existe. */
  catalog?: CatalogEarthquakeOut[];
  catalogError?: boolean;
  selectedCatalogId?: string | null;
  /** [T-6.14] `null` DESARMA: apagar el histórico y el «CANCELAR» del aviso
   * pasan por aquí, y quien manda en la selección sigue siendo el padre. */
  onSelectCatalog?: (refId: string | null) => void;
  /** [T-2.50] Estaciones dentro del viewport actual (moveend + getBounds). */
  onViewportChange?: (visibleSiteIds: string[]) => void;
  /**
   * [T-7.24] El mini-ShakeMap YA CALCULADO del incidente
   * (`GET /incidents/{id}/shakemap`). **Sin la prop, la capa no existe** —mismo
   * trato que el catálogo histórico—: este panel es el wall EN VIVO y el mapa de
   * la sacudida es por evento, así que quien lo tenga lo pasa y quien no, ni
   * estrena un interruptor ni una leyenda que no puede llenar.
   *
   * El panel NO lo pide ni lo calcula: lo pinta. Si lo calculara, dos operadores
   * verían mapas distintos del mismo sismo según cuándo apretaran F5.
   */
  shakemap?: ShakemapOut;
  /** `true` = la consulta del mapa de sacudida falló. Se declara, no se calla. */
  shakemapError?: boolean;
  /**
   * `true` = la consulta está EN VUELO y todavía no hay snapshot.
   *
   * Es un estado propio y no un vacío (regla de oro 7): sin él, el hueco entre
   * la petición y la respuesta se ve idéntico a un incidente que no tiene mapa.
   */
  shakemapLoading?: boolean;
}

export default function MapPanel({
  sites,
  epicenters,
  onSelectSite,
  catalog = [],
  catalogError = false,
  selectedCatalogId = null,
  onSelectCatalog,
  onViewportChange,
  shakemap,
  shakemapError = false,
  shakemapLoading = false,
}: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const degradedRef = useRef(false);
  const [degraded, setDegraded] = useState(false);
  // `loadedRef` no es reactivo: los efectos que TOCAN el mapa necesitan volver a
  // correr cuando el estilo termina de cargar, o se quedan con el early-return
  // del primer render y las capas nacen sin visibilidad ni datos.
  const [styleReady, setStyleReady] = useState(false);
  const sitesRef = useRef(sites);
  sitesRef.current = sites;
  const epicentersRef = useRef(epicenters);
  epicentersRef.current = epicenters;
  const onSelectRef = useRef(onSelectSite);
  onSelectRef.current = onSelectSite;
  // [T-7.24] Lo que la capa de cobertura tiene DERECHO a pintar ahora mismo.
  // Vive en un ref porque el `zoomend` —que rehace los radios FÍSICOS— se
  // registra una sola vez dentro del `style.load` y no vería el snapshot de un
  // render posterior.
  const coberturaRef = useRef<ShakemapOut | undefined>(undefined);
  // [T-2.28] capa de catálogo histórico: OFF por default (el wall es operativo).
  const [layers, setLayers] = useState<LayerToggles>(DEFAULT_LAYERS);
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const onSelectCatalogRef = useRef(onSelectCatalog);
  onSelectCatalogRef.current = onSelectCatalog;
  const onViewportRef = useRef(onViewportChange);
  onViewportRef.current = onViewportChange;

  const reducedMotion = useReducedMotion();
  const reducedMotionRef = useRef(reducedMotion);
  reducedMotionRef.current = reducedMotion;

  // Frente vivo: origen fijo (epoch ms) + latitud del epicentro más reciente que
  // está LOCALIZADO y DENTRO de la ventana. `null` = no hay nada que animar; el
  // rAF lo lee cada tick y se apaga solo cuando el evento envejece.
  const waveRef = useRef<{ originMs: number; lat: number } | null>(null);
  const [waveActive, setWaveActive] = useState(false);

  const bounds = useCallback((map: maplibregl.Map): ViewBounds | null => {
    const b = map.getBounds?.();
    if (b === undefined || b === null) return null;
    return { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() };
  }, []);

  const emitViewport = useCallback(
    (map: maplibregl.Map) => {
      const cb = onViewportRef.current;
      if (cb === undefined) return;
      cb(sitesInBounds(sitesRef.current, bounds(map)).map((s) => s.site_id));
    },
    [bounds],
  );

  // Init una sola vez; datos y handlers via refs (sin re-crear el mapa).
  useEffect(() => {
    if (containerRef.current === null) return undefined;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      // [T-2.59] Sin el control nativo: este panel YA pinta su atribución en
      // `.soc-map__attribution` (abajo-izquierda) con los créditos que exigen
      // OpenFreeMap y OpenStreetMap. El nativo los repetía abajo-DERECHA, y
      // esa esquina es la del panel de leyendas: medidos 2853 px² (357×8) de
      // solape en los tres viewports. Se quita el duplicado, no el crédito.
      attributionControl: false,
    });
    mapRef.current = map;
    let raf = 0;
    // El contenedor puede asentarse DESPUÉS del constructor (grid del wall):
    // sin resize el canvas queda medido en 0×0 aunque el CSS ya esté bien.
    const stopResize = observeMapResize(map, containerRef.current);

    // Estilo remoto irrecuperable ⇒ degradar a estilo local. Solo aplica si el
    // estilo inicial NUNCA cargó (un tile suelto fallando mid-sesión no borra
    // el mapa base ya renderizado).
    map.on("error", () => {
      if (loadedRef.current || degradedRef.current) return;
      degradedRef.current = true;
      setDegraded(true);
      map.setStyle(FALLBACK_STYLE as unknown as maplibregl.StyleSpecification);
    });

    // `style.load` dispara para el estilo inicial Y tras setStyle(FALLBACK):
    // en ambos casos hay que (re)colgar sources/capas del wall.
    map.on("style.load", () => {
      loadedRef.current = true;
      setStyleReady(true);
      if (map.getSource("sites") !== undefined) return;
      map.addSource("sites", { type: "geojson", data: sitesToFeatureCollection(sitesRef.current) });
      map.addSource("tripped", { type: "geojson", data: trippedFeatures(sitesRef.current) });
      map.addSource("epicenters", {
        type: "geojson",
        data: epicentersToFeatureCollection(epicentersRef.current),
      });

      // NO hay bandas MMI, y lo que sigue explica qué se puede dibujar en su
      // lugar. Aquí vivían dos anillos ("mmi-severa" 55px y "mmi-alta" 100px)
      // rotulados INTENSIDAD MMI que no estaban conectados a ningún dato: eran
      // constantes. Y como `circle-radius` de MapLibre es en PÍXELES DE
      // PANTALLA, el mismo anillo afirmaba ~22 km de radio en zoom 8.5 y ~1 km
      // en zoom 13 — la banda cambiaba de significado físico con cada rueda del
      // ratón.
      //
      // [T-7.24] El mini-ShakeMap ya existe (más abajo) y NO deroga nada de
      // esto: no interpola una superficie, no dibuja isosistas y no reporta
      // intensidad macrosísmica —`dictamen/model.py::NO_MMI` lo tiene impreso en
      // documentos FIRMADOS—. Son puntos MEDIDOS, anillos de un MODELO rotulados
      // como tales y el residuo entre ambos, y sus anillos son polígonos en
      // grados. Lo que sigue prohibido es lo que mató a aquellas dos capas:
      // inventar un radio y presentarlo como el área donde se sintió el sismo
      // (regla de oro 7).
      //
      // [T-2.47] Los frentes P/S de abajo son otra cosa y por eso SÍ se dibujan:
      // no afirman intensidad ninguna, son la posición geométrica de un frente a
      // velocidad conocida desde un origen conocido (modelo de UNA CAPA, así
      // rotulado), y su radio es FÍSICO — se reconvierte a píxeles con el zoom.

      // --- [T-2.47] Ondas: líneas y frentes ---------------------------------
      // Van ABAJO del resto (se añaden primero) para no tapar ni estaciones ni
      // epicentros: son contexto, no el dato.
      map.addSource("wave-links", {
        type: "geojson",
        data: epicenterLinks([], []) as unknown as SourceData,
      });
      map.addSource("wave-front", {
        type: "geojson",
        data: epicentersToFeatureCollection([]),
      });
      map.addSource("wave-static", {
        type: "geojson",
        data: staticRingsFeatureCollection([], DEFAULT_ZOOM),
      });
      // [T-7.18] La ráfaga de arribo por estación. Fuente propia y no una
      // propiedad de `sites`: el instante depende del EPICENTRO, y meterlo en el
      // edificio haría que el mismo sitio tuviera un arribo distinto por cada
      // evento en pantalla.
      map.addSource("arrivals", {
        type: "geojson",
        data: arrivalsFeatureCollection([], []),
      });
      map.addLayer({
        id: "wave-link",
        type: "line",
        source: "wave-links",
        layout: { visibility: "none" },
        paint: {
          "line-color": EPICENTER_COLOR,
          "line-width": 1.1,
          "line-opacity": 0.55,
          "line-dasharray": [...DASH_FRAMES[0]],
        },
      });
      map.addLayer({
        id: "wave-p",
        type: "circle",
        source: "wave-front",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 0,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": WAVE_P_COLOR,
          "circle-stroke-width": 1.4,
          "circle-stroke-opacity": 0.75,
        },
      });
      map.addLayer({
        id: "wave-s",
        type: "circle",
        source: "wave-front",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 0,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": WAVE_S_COLOR,
          "circle-stroke-width": 1.8,
          "circle-stroke-opacity": 0.8,
        },
      });
      // Los anillos QUIETOS del modo accesible: el radio viaja EN EL DATO, así
      // que no hay nada que animar y basta un setData en `zoomend`.
      map.addLayer({
        id: "wave-static-ring",
        type: "circle",
        source: "wave-static",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["get", "radius_px"],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": [
            "case",
            ["==", ["get", "phase"], "P"],
            WAVE_P_COLOR,
            WAVE_S_COLOR,
          ],
          "circle-stroke-width": 1.2,
          "circle-stroke-opacity": 0.7,
        },
      });
      map.addLayer({
        id: "wave-static-label",
        type: "symbol",
        source: "wave-static",
        layout: {
          visibility: "none",
          "text-field": ["get", "label"],
          "text-font": TEXT_FONT,
          "text-size": 9,
          "text-offset": [0, -0.8],
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#B8C2CE",
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.5,
        },
      });

      // Pulso animado (rAF, easing lineal). Es un BEACON del marcador del
      // edificio que DISPARÓ (atrae la vista), no una afirmación geográfica: por
      // eso sí es correcto que viva en píxeles y no escale con el zoom.
      map.addLayer({
        id: "pulse",
        type: "circle",
        source: "tripped",
        paint: {
          "circle-radius": 15,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": FELT_COLOR.trip,
          "circle-stroke-width": 1.2,
        },
      });
      // [T-7.18] El anillo del arribo va DEBAJO del edificio: anuncia que la onda
      // acaba de llegar ahí, no tapa lo que el edificio midió.
      map.addLayer({
        id: "arrival-ring",
        type: "circle",
        source: "arrivals",
        paint: {
          "circle-radius": 0,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": EPICENTER_COLOR,
          "circle-stroke-width": 1.4,
          "circle-stroke-opacity": 0,
        },
      });
      // Halo + núcleo de cada EDIFICIO, coloreados por lo que ESE inmueble midió.
      map.addLayer({
        id: "site-halo",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "tripped"], 16, 12],
          "circle-color": ["get", "color"],
          "circle-opacity": ["get", "link_halo_opacity"],
        },
      });
      map.addLayer({
        id: "site-core",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "tripped"], 7, 5],
          // [T-2.46] NÚCLEO HUECO con el enlace caído: el relleno desaparece y
          // queda un aro del color de la sacudida. Se lee de un vistazo como lo
          // que es — un color que ya no está respaldado por un dato vivo.
          "circle-color": ["case", ["get", "link_down"], "rgba(0,0,0,0)", ["get", "color"]],
          "circle-opacity": ["get", "link_opacity"],
          // Borde punteado no se puede en `circle`: el sitio SIN CALIBRAR se
          // declara con un anillo tenue en vez del contorno sólido del navy —
          // su PGA es relativo y no puede leerse como una intensidad física.
          "circle-stroke-color": [
            "case",
            ["get", "link_down"],
            ["get", "color"],
            ["case", ["get", "calibrated"], "#0d2034", "#FFFFFF"],
          ],
          "circle-stroke-width": [
            "case",
            ["get", "link_down"],
            2,
            ["case", ["get", "calibrated"], 1.5, 1],
          ],
          "circle-stroke-opacity": [
            "case",
            ["get", "link_down"],
            ["get", "link_opacity"],
            ["case", ["get", "calibrated"], 1, 0.55],
          ],
        },
      });
      // [T-2.46] Capa de GLIFO del enlace: ⊘ sin enlace, ▲ degradado, ○ sin
      // gabinete. Vacío en OPERATIVO — el ruido visual se reserva al problema.
      map.addLayer({
        id: "site-link",
        type: "symbol",
        source: "sites",
        layout: {
          "text-field": ["get", "link_glyph"],
          "text-font": TEXT_FONT,
          "text-size": 11,
          "text-offset": [0.9, -0.9],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#F0F2F5",
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.6,
        },
      });

      // [T-6.09] Glifo de la BANDA DE SACUDIDA. Se ancla abajo-izquierda para
      // no chocar con el del enlace (arriba-derecha): son dos alfabetos y el
      // sitio puede llevar los dos a la vez.
      map.addLayer({
        id: "site-felt",
        type: "symbol",
        source: "sites",
        layout: {
          "text-field": ["get", "felt_glyph"],
          "text-font": TEXT_FONT,
          "text-size": 12,
          "text-offset": [-0.85, 0.85],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#F0F2F5",
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.6,
        },
      });

      // [T-5.05] Rótulo DEMO. Va en gris neutro y NO en ámbar: el ámbar de esta
      // consola ya significa simulacro en curso y dato retenido, y un tercer
      // significado en el mismo color deja de significar nada. Vacío en los
      // sitios reales, que es el caso de producción: cero ruido añadido.
      map.addLayer({
        id: "site-demo",
        type: "symbol",
        source: "sites",
        layout: {
          "text-field": ["get", "demo_glyph"],
          "text-font": TEXT_FONT,
          "text-size": 9,
          "text-letter-spacing": 0.14,
          "text-offset": [0, 1.7],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#8A9CB1",
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.6,
        },
      });

      // --- [T-7.24] EL MAPA DE LA SACUDIDA ----------------------------------
      //
      // Dos fuentes y no una, y ésa es la mitad del contrato: un rasgo MEDIDO no
      // puede acabar dibujado por la capa del MODELO ni al revés. La otra mitad
      // es que la procedencia viaja dentro de cada rasgo (`shakemap.ts`).
      //
      // ⚠️ Los anillos son POLÍGONOS EN GRADOS —los materializa el lector de la
      // nube (`shakemap/lectura.py::circulo`)— y se dibujan con una capa `line`,
      // JAMÁS con `circle-radius`. Aquí vivían dos capas de bandas MMI con radio
      // en píxeles de pantalla: el mismo anillo afirmaba ~22 km a zoom 8.5 y ~1
      // km a zoom 13. Un anillo que dice «aquí el modelo predice 0.02 g» tiene
      // que seguir diciéndolo a cualquier zoom.
      map.addSource("shakemap-modelado", {
        type: "geojson",
        data: modeladoFeatureCollection(undefined) as unknown as SourceData,
      });
      map.addSource("shakemap-observado", {
        type: "geojson",
        data: observadoFeatureCollection(undefined) as unknown as SourceData,
      });
      map.addSource("shakemap-cobertura", {
        type: "geojson",
        data: coberturaFeatureCollection(undefined, DEFAULT_ZOOM) as unknown as SourceData,
      });
      // HASTA DÓNDE HABLA LO MEDIDO. Va la primera, o sea DEBAJO de todo lo
      // demás: es el suelo de la lectura, no un dato encima de los datos.
      //
      // Esta capa existe porque la leyenda declaraba una tinta de `SIN
      // COBERTURA` que ninguna capa usaba — una clave de color prometiendo una
      // distinción que el mapa no hacía en ninguna parte, que es el mismo
      // defecto de la leyenda MMI que esta tarea vino a cerrar.
      //
      // ⚠️ Radio FÍSICO: `radius_px` lo calcula `coberturaFeatureCollection`
      // con el zoom y se rehace en `zoomend`. Un número constante aquí sería
      // otra vez `DIF-shakemap.a`.
      map.addLayer({
        id: "shakemap-cobertura",
        type: "circle",
        source: "shakemap-cobertura",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["get", "radius_px"],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": PGA_SIN_COBERTURA,
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.6,
        },
      });
      map.addLayer({
        id: "shakemap-anillo",
        type: "line",
        source: "shakemap-modelado",
        layout: { visibility: "none" },
        paint: {
          // El color es la BANDA DE PGA; lo que separa modelo de medida es la
          // FORMA (trazo discontinuo vs disco relleno), nunca el color: con dos
          // escalas distintas no se podrían comparar, que es para lo que está.
          "line-color": ["get", "color"],
          "line-width": 1.4,
          "line-dasharray": [3, 3],
          "line-opacity": 0.85,
        },
      });
      map.addLayer({
        id: "shakemap-anillo-nivel",
        type: "symbol",
        source: "shakemap-modelado",
        layout: {
          visibility: "none",
          // Rotulado SOBRE la línea: un `symbol` normal pondría los tres
          // rótulos en el centroide —el epicentro— apilados uno encima de otro.
          "symbol-placement": "line",
          "symbol-spacing": 400,
          "text-field": ["get", "label"],
          "text-font": TEXT_FONT,
          "text-size": 10,
        },
        paint: {
          "text-color": ["get", "color"],
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.6,
        },
      });
      map.addLayer({
        id: "shakemap-punto",
        type: "circle",
        source: "shakemap-observado",
        layout: { visibility: "none" },
        paint: {
          // CONSTANTE, y es deliberado: un marcador no afirma extensión, afirma
          // un valor EN ESE PUNTO. Atar este radio al PGA lo convertiría en una
          // burbuja que se lee como área de influencia — el pecado de las MMI.
          "circle-radius": 9,
          // Sin medida el disco va HUECO: un relleno diría que hay un valor.
          "circle-color": ["case", ["get", "medido"], ["get", "color"], "rgba(0,0,0,0)"],
          "circle-opacity": 0.85,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1.6,
        },
      });
      map.addLayer({
        id: "shakemap-punto-valor",
        type: "symbol",
        source: "shakemap-observado",
        layout: {
          visibility: "none",
          "text-field": ["get", "label"],
          "text-font": TEXT_FONT,
          "text-size": 10,
          "text-offset": [0, -1.7],
          "text-anchor": "bottom",
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#F0F2F5",
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.6,
        },
      });

      // EPICENTRO: dónde se ORIGINÓ el sismo. Va por encima de los edificios y
      // con otra forma (cruz + rótulo) para que jamás se confunda con uno.
      map.addLayer({
        id: "epicenter-halo",
        type: "circle",
        source: "epicenters",
        paint: {
          "circle-radius": 14,
          "circle-color": EPICENTER_COLOR,
          "circle-opacity": 0.15,
          "circle-stroke-color": EPICENTER_COLOR,
          "circle-stroke-width": 1,
        },
      });
      map.addLayer({
        id: "epicenter-mark",
        type: "symbol",
        source: "epicenters",
        layout: {
          "text-field": "✳",
          "text-font": TEXT_FONT,
          "text-size": 20,
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: { "text-color": EPICENTER_COLOR },
      });
      map.addLayer({
        id: "epicenter-label",
        type: "symbol",
        source: "epicenters",
        layout: {
          "text-field": ["get", "label"],
          "text-font": TEXT_FONT,
          "text-size": 11,
          "text-offset": [0, 1.5],
          "text-anchor": "top",
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": EPICENTER_COLOR,
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.5,
        },
      });

      // [T-2.28] Catálogo histórico: ◇ + rótulo. La capa nace VACÍA (toggle off);
      // el efecto de datos la alimenta. NO es intensidad interpolada: cada ◇ es
      // un epicentro puntual del catálogo oficial, sin radios ni isosistas.
      map.addSource("catalog", {
        type: "geojson",
        data: catalogToFeatureCollection([], null),
      });
      map.addLayer({
        id: "catalog-mark",
        type: "symbol",
        source: "catalog",
        layout: {
          "text-field": "◇",
          "text-font": TEXT_FONT,
          "text-size": ["case", ["get", "selected"], 26, 18],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": CATALOG_COLOR,
          "text-halo-color": "#0d2034",
          "text-halo-width": ["case", ["get", "selected"], 2.5, 1],
        },
      });
      map.addLayer({
        id: "catalog-label",
        type: "symbol",
        source: "catalog",
        layout: {
          "text-field": ["get", "label"],
          "text-font": TEXT_FONT,
          "text-size": 10,
          "text-offset": [0, 1.4],
          "text-anchor": "top",
        },
        paint: {
          "text-color": CATALOG_COLOR,
          "text-halo-color": "#0d2034",
          "text-halo-width": 1.5,
        },
      });

      map.on("click", "site-core", (event) => {
        const feature = event.features?.[0];
        const siteId = feature?.properties?.["site_id"];
        if (typeof siteId === "string") onSelectRef.current(siteId);
      });
      map.on("click", "catalog-mark", (event) => {
        const refId = event.features?.[0]?.properties?.["ref_id"];
        if (typeof refId === "string") onSelectCatalogRef.current?.(refId);
      });
      // [T-2.50] El contador del wall va atado a lo que se está VIENDO.
      map.on("moveend", () => emitViewport(map));
      // [T-2.47] Radio FÍSICO ⇒ hay que rehacer los píxeles al cambiar el zoom.
      // Los anillos animados se recalculan solos en cada tick; los QUIETOS del
      // modo accesible no tienen tick, así que se rehacen aquí.
      map.on("zoomend", () => {
        const zoom = map.getZoom?.() ?? DEFAULT_ZOOM;
        const source = map.getSource("wave-static") as maplibregl.GeoJSONSource | undefined;
        source?.setData(
          staticRingsFeatureCollection(
            animatableEpicenters(epicentersRef.current, Date.now()),
            zoom,
          ) as unknown as SourceData,
        );
        // [T-7.24] El halo de cobertura mide 25 km DE TERRENO: sin rehacer los
        // píxeles, a zoom 13 afirmaría un par de manzanas.
        (map.getSource("shakemap-cobertura") as maplibregl.GeoJSONSource | undefined)?.setData(
          coberturaFeatureCollection(coberturaRef.current, zoom) as unknown as SourceData,
        );
      });
      emitViewport(map);

      if (raf !== 0) return; // el loop del pulso ya corre (re-add tras fallback)
      const start = performance.now();
      let lastTick = -Infinity;
      const loop = (t: number) => {
        // Compuerta de 20 fps: un solo rAF para TODO lo que se mueve en el wall.
        if (t - lastTick >= FRAME_MS) {
          lastTick = t;
          // Entre setStyle(FALLBACK) y su style.load la capa no existe: guard.
          if (map.getLayer("pulse") !== undefined) {
            // [A-060] `reducedMotionRef` existía y NUNCA se leía. Se lee aquí, en
            // cada tick, para que el cambio del ajuste en caliente y la recarga
            // del estilo (fallback) queden cubiertos sin otra vía. Repetir el
            // mismo valor es gratis: MapLibre descarta un paint idéntico.
            const { radius, strokeOpacity } = pulseFrame(t - start, reducedMotionRef.current);
            map.setPaintProperty("pulse", "circle-radius", radius);
            map.setPaintProperty("pulse", "circle-stroke-opacity", strokeOpacity);
            // [A-060] Lo que el loop PINTA, legible desde un e2e. Comparar dos
            // capturas del canvas entero no aísla al faro: el frente de onda y el
            // anillo de arribo se mueven en la misma imagen, y bastaba con que una
            // tesela llegara tarde. El radio es el hecho que A-060 afirma; no
            // depende de que haya un edificio disparado, así que se mide siempre.
            containerRef.current?.setAttribute("data-faro-radio", radius.toFixed(2));
          }
          const wave = waveRef.current;
          if (wave !== null && map.getLayer("wave-p") !== undefined) {
            const elapsedS = (Date.now() - wave.originMs) / 1000;
            if (elapsedS >= WAVE_MAX_AGE_S) {
              // Condición de apagado nº2: el frente envejeció. Se apaga SOLO,
              // sin esperar a que llegue un snapshot nuevo del servidor.
              waveRef.current = null;
              setWaveActive(false);
            } else {
              const zoom = map.getZoom?.() ?? DEFAULT_ZOOM;
              const { pKm, sKm } = waveRadiiKm(elapsedS);
              map.setPaintProperty("wave-p", "circle-radius", kmToPixels(pKm, wave.lat, zoom));
              map.setPaintProperty("wave-s", "circle-radius", kmToPixels(sKm, wave.lat, zoom));
              // Dash CONMUTADO: una propiedad de pintura de la capa, O(1) por
              // frame haya 3 líneas o 300. La geometría no se toca jamás.
              if (map.getLayer("wave-link") !== undefined) {
                const frame = DASH_FRAMES[dashFrameIndex(t - start)];
                map.setPaintProperty("wave-link", "line-dasharray", [...frame]);
              }
              // [T-7.18] La ráfaga de cada estación, en UNA expresión por frame:
              // el motor la evalúa por rasgo, así que da igual que haya tres
              // estaciones o trescientas. `d` es lo que lleva la onda desde que
              // llegó a ESE edificio.
              if (map.getLayer("arrival-ring") !== undefined) {
                const d = ["-", elapsedS, ["get", "arrival_s"]];
                const dentro = ["all", [">=", d, 0], ["<", d, ARRIVAL_BURST_S]];
                map.setPaintProperty("arrival-ring", "circle-radius", [
                  "case",
                  dentro,
                  ["+", 9, ["*", 18, ["/", d, ARRIVAL_BURST_S]]],
                  0,
                ]);
                map.setPaintProperty("arrival-ring", "circle-stroke-opacity", [
                  "case",
                  dentro,
                  ["-", 1, ["/", d, ARRIVAL_BURST_S]],
                  0,
                ]);
              }
            }
          }
        }
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    });

    return () => {
      cancelAnimationFrame(raf);
      stopResize();
      loadedRef.current = false;
      mapRef.current = null;
      map.remove();
    };
    // `emitViewport` es estable (useCallback sin deps vivas) y el resto entra por
    // refs: el mapa se construye UNA vez. Meter aquí una prop viva (un handler
    // recreado por render) reconstruiría el mapa entero en cada render.
  }, [emitViewport]);

  // Datos nuevos → setData (sin recrear capas).
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || !loadedRef.current) return;
    (map.getSource("sites") as maplibregl.GeoJSONSource | undefined)?.setData(
      sitesToFeatureCollection(sites),
    );
    (map.getSource("tripped") as maplibregl.GeoJSONSource | undefined)?.setData(
      trippedFeatures(sites),
    );
    (map.getSource("epicenters") as maplibregl.GeoJSONSource | undefined)?.setData(
      epicentersToFeatureCollection(epicenters),
    );
    (map.getSource("catalog") as maplibregl.GeoJSONSource | undefined)?.setData(
      catalogToFeatureCollection(layers.catalog ? catalog : [], selectedCatalogId),
    );
    emitViewport(map);
  }, [sites, epicenters, catalog, selectedCatalogId, layers.catalog, emitViewport, styleReady]);

  // [T-2.47] Compuerta de la animación, SIN depender del mapa: la leyenda tiene
  // que declarar el estado aunque los tiles no hayan cargado (regla de oro 7).
  // Se re-evalúa con los datos —el snapshot llega cada 30 s— y el rAF se apaga
  // solo cuando el frente envejece, sin esperar al siguiente snapshot.
  // `Date.now()` va DENTRO del memo a propósito: la compuerta se re-evalúa cuando
  // llega un snapshot nuevo (cada 30 s), no en cada render. El apagado por edad
  // dentro de esa ventana lo hace el rAF, que sí mira el reloj cada tick.
  const live = useMemo(() => animatableEpicenters(epicenters, Date.now()), [epicenters]);
  // Con más de un epicentro vivo se anima el MÁS RECIENTE: un solo par de
  // anillos no puede describir honestamente dos orígenes distintos.
  const newest = useMemo(
    () =>
      live.reduce<MapEpicenter | null>(
        (best, e) =>
          best === null || Date.parse(e.detected_at) > Date.parse(best.detected_at) ? e : best,
        null,
      ),
    [live],
  );
  useEffect(() => {
    setWaveActive(newest !== null);
    if (newest === null || reducedMotion) {
      // Condiciones de apagado nº1 (sin epicentro localizado / evento viejo) y
      // nº3 (el operador pidió menos movimiento).
      waveRef.current = null;
      return;
    }
    waveRef.current = { originMs: Date.parse(newest.detected_at), lat: newest.lat };
  }, [newest, reducedMotion]);

  // Datos de las capas de onda → sources (esto sí toca el mapa).
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || !loadedRef.current) return;
    const zoom = map.getZoom?.() ?? DEFAULT_ZOOM;
    (map.getSource("wave-links") as maplibregl.GeoJSONSource | undefined)?.setData(
      epicenterLinks(live, sites) as unknown as SourceData,
    );
    (map.getSource("wave-front") as maplibregl.GeoJSONSource | undefined)?.setData(
      epicentersToFeatureCollection(newest === null ? [] : [newest]) as unknown as SourceData,
    );
    (map.getSource("wave-static") as maplibregl.GeoJSONSource | undefined)?.setData(
      staticRingsFeatureCollection(live, zoom) as unknown as SourceData,
    );
    // [T-7.18] Los arribos del frente VIVO. Con `newest === null` la colección
    // queda vacía y el anillo desaparece solo, sin esperar a un snapshot nuevo.
    (map.getSource("arrivals") as maplibregl.GeoJSONSource | undefined)?.setData(
      arrivalsFeatureCollection(newest === null ? [] : [newest], sites) as unknown as SourceData,
    );
    if (reducedMotion && map.getLayer("wave-link") !== undefined) {
      // Dash CONGELADO en su primer fotograma: el interruptor apaga TODO
      // movimiento, incluido el de la línea.
      map.setPaintProperty("wave-link", "line-dasharray", [...DASH_FRAMES[0]]);
    }
    if (reducedMotion && map.getLayer("arrival-ring") !== undefined) {
      // [T-7.18] El interruptor apaga el MOVIMIENTO, no la información: en vez
      // de la ráfaga, un anillo QUIETO sobre cada estación a la que la onda ya
      // llegó. Sin tick no hay decaimiento, así que el anillo no miente sobre
      // «acaba de llegar»: dice «ya llegó», que es lo que se sabe.
      const elapsedS = newest === null ? 0 : (Date.now() - Date.parse(newest.detected_at)) / 1000;
      const yaLlego = [">=", elapsedS, ["get", "arrival_s"]];
      map.setPaintProperty("arrival-ring", "circle-radius", ["case", yaLlego, 14, 0]);
      map.setPaintProperty("arrival-ring", "circle-stroke-opacity", ["case", yaLlego, 0.55, 0]);
    }
  }, [sites, live, newest, reducedMotion, styleReady]);

  // [T-7.24] Datos del mapa de la sacudida. Lo que se pinta lo decide
  // `vistaSacudida` a partir del DATO —no del rótulo del estado—, así que un
  // snapshot que se declare `completo` sin anillos no dibuja un modelo fantasma.
  const sacudida = useMemo(
    () => vistaSacudida(shakemap, shakemapError, shakemapLoading),
    [shakemap, shakemapError, shakemapLoading],
  );
  coberturaRef.current = sacudida.pintaObservado ? shakemap : undefined;
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || !loadedRef.current) return;
    (map.getSource("shakemap-observado") as maplibregl.GeoJSONSource | undefined)?.setData(
      observadoFeatureCollection(sacudida.pintaObservado ? shakemap : undefined) as SourceData,
    );
    (map.getSource("shakemap-modelado") as maplibregl.GeoJSONSource | undefined)?.setData(
      modeladoFeatureCollection(sacudida.pintaModelado ? shakemap : undefined) as SourceData,
    );
    (map.getSource("shakemap-cobertura") as maplibregl.GeoJSONSource | undefined)?.setData(
      coberturaFeatureCollection(
        coberturaRef.current,
        map.getZoom?.() ?? DEFAULT_ZOOM,
      ) as SourceData,
    );
  }, [shakemap, sacudida, styleReady]);

  // Visibilidad de capas (T-2.50) + estado de las ondas (T-2.47), en un solo sitio.
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || !loadedRef.current) return;
    const show = (id: string, on: boolean): void => {
      if (map.getLayer(id) !== undefined) {
        map.setLayoutProperty?.(id, "visibility", on ? "visible" : "none");
      }
    };
    for (const [key, ids] of Object.entries(LAYERS_OF) as [keyof LayerToggles, string[]][]) {
      if (key === "waves") continue;
      for (const id of ids) show(id, layers[key]);
    }
    const waves = layers.waves && waveActive;
    show("wave-link", waves);
    show("wave-p", waves && !reducedMotion);
    show("wave-s", waves && !reducedMotion);
    show("wave-static-ring", waves && reducedMotion);
    show("wave-static-label", waves && reducedMotion);
  }, [layers, waveActive, reducedMotion, styleReady]);

  const anyUncalibrated = sites.some((s) => s.calibrated !== true);
  const linkCounts = sites.reduce<Record<string, number>>((acc, s) => {
    const state = siteLink(s);
    acc[state] = (acc[state] ?? 0) + 1;
    return acc;
  }, {});
  // [T-6.14] Apagar el HISTÓRICO desarma la comparativa. El aviso del paso 2
  // colgaba de `layers.catalog`, así que apagar la capa lo borraba y dejaba el
  // mapa armado en silencio: el siguiente clic en una estación abría la
  // comparativa en vez del detalle. Se desarma desde AQUÍ y no desde un efecto
  // del padre porque el interruptor vive aquí; el padre sigue siendo el dueño
  // de la selección y por eso se le avisa en vez de tocarla.
  //
  // Vale para los DOS mandos del mismo interruptor (la fila de CAPAS y el
  // rótulo de la leyenda): que uno desarmara y el otro no sería peor que no
  // desarmar ninguno.
  // El sismo con el que está armada la comparativa, si lo tenemos en el
  // catálogo cargado: `null` = no armado.
  const armado = catalog.find((q) => q.ref_id === selectedCatalogId) ?? null;
  // [T-7.24] La superficie que ALIMENTA el mapa de sacudida es la que lo enseña.
  // Sin `shakemap` no hay ni botón de capa ni leyenda: un wall en vivo no estrena
  // un interruptor que no conmuta nada ni una caja que sólo puede decir «vacío».
  const muestraSacudida = shakemap !== undefined || shakemapError || shakemapLoading;
  const niveles = nivelesDe(sacudida.pintaModelado ? shakemap : undefined);
  // [T-7.24] La fila de `SIN COBERTURA` cuelga de que HAYA halo, no de que haya
  // puntos: el halo sólo lo dibujan los inmuebles que MIDIERON, así que un
  // snapshot con puntos mudos prometía un límite que ninguna capa dibuja — la
  // clave de color huérfana que esta ficha vino a cerrar. Se cuenta con la MISMA
  // función que alimenta la capa para que no puedan divergir; el zoom no cambia
  // CUÁNTOS halos hay, sólo su radio en píxeles.
  const hayCobertura =
    coberturaFeatureCollection(coberturaRef.current, DEFAULT_ZOOM).features.length > 0;
  const descartados = sinProcedencia(shakemap);
  const calculadoEn =
    shakemap?.calculado_en != null && !Number.isNaN(Date.parse(shakemap.calculado_en))
      ? utcStamp(Date.parse(shakemap.calculado_en))
      : null;
  const toggle = (key: keyof LayerToggles) => () => {
    const apagando = layersRef.current[key];
    // El ref se ADELANTA al render: dos pulsaciones en el mismo lote (un doble
    // clic, o el mando de la fila y el de la leyenda seguidos) leerían las dos
    // el estado viejo y la segunda no se enteraría de que está apagando.
    layersRef.current = { ...layersRef.current, [key]: !apagando };
    setLayers(layersRef.current);
    if (key === "catalog" && apagando) onSelectCatalogRef.current?.(null);
  };

  return (
    <div
      className="soc-map"
      data-testid="map-panel"
      data-comparativa={armado !== null ? "armada" : undefined}
    >
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />

      {/* [T-2.55] Pila de ESTADO DEL MAPA, arriba-izquierda. El badge estaba
          anclado al centro superior y ahí chocaba con la alerta sísmica y con
          el "DATOS RETENIDOS" del wall. Cada esquina tiene un solo dueño. */}
      <div className="soc-map__status">
        {degraded && (
          <div className="soc-map__degraded" data-testid="map-degraded" role="status">
            ◐ SIN MAPA BASE · TILES NO DISPONIBLES · SITIOS EN VIVO
          </div>
        )}
        {/* [T-6.14] El mapa ARMADO lo dice donde se está mirando, no en la
            tercera leyenda de abajo. Dice también QUÉ sismo, porque el mapa
            tiene trece ◇ iguales, y trae su propio modo de salir: quien armó
            sin querer no tiene que adivinar que se desarma apagando una capa. */}
        {armado !== null && (
          <div className="soc-map__armado" data-testid="map-armado" role="status">
            <span>
              ◇ COMPARATIVA ARMADA · {catalogLabel(armado)} · ELIJA LA ESTACIÓN A COMPARAR
            </span>
            <button
              type="button"
              className="soc-map__armado-btn"
              data-testid="map-desarmar"
              onClick={() => onSelectCatalogRef.current?.(null)}
            >
              CANCELAR
            </button>
          </div>
        )}
      </div>

      <div className="soc-map__legends">
        {/* [T-2.50] Capas conmutables: el operador decide qué mira. */}
        <div className="soc-map__legend soc-map__legend--layers" data-testid="map-layers">
          <div className="soc-map__legend-title">CAPAS</div>
          <div className="soc-map__layer-row">
            {(Object.keys(LAYER_LABEL) as (keyof LayerToggles)[])
              // La clave existe SIEMPRE en las cuatro tablas —una capa a medias
              // es peor que ninguna—; lo que es condicional es el MANDO.
              .filter((key) => key !== "shakemap" || muestraSacudida)
              .map((key) => (
                <button
                  key={key}
                  type="button"
                  className={`soc-map__layer-btn${layers[key] ? " soc-map__layer-btn--on" : ""}`}
                  data-testid={`layer-${key}`}
                  aria-pressed={layers[key]}
                  onClick={toggle(key)}
                >
                  {LAYER_LABEL[key]}
                </button>
              ))}
          </div>
          {layers.waves && !waveActive && (
            <div className="soc-map__legend-note" data-testid="waves-idle">
              SIN FRENTE ACTIVO · SE DIBUJA CON EPICENTRO LOCALIZADO Y EVENTO &lt; {WAVE_MAX_AGE_S}{" "}
              s
            </div>
          )}
          {layers.waves && waveActive && (
            <div className="soc-map__legend-note" data-testid="waves-model">
              ◍ FRENTES P/S · MODELO DE UNA CAPA · ESTIMACIÓN
              {/* [T-7.18] Bajo reducción el anillo de arribo no destella: se
                  queda puesto sobre las estaciones a las que la onda YA llegó, y
                  la leyenda lo dice. El interruptor apaga el movimiento, no la
                  información — y decir «ya llegó» es lo que se sabe sin tick. */}
              {reducedMotion
                ? " · ANILLOS ESTÁTICOS (MOVIMIENTO REDUCIDO) · ARRIBO YA ALCANZADO, SIN RÁFAGA"
                : ""}
            </div>
          )}
        </div>

        {/* [T-2.46] SEGUNDA leyenda, separada de la de movimiento del suelo: son
            dos hechos ortogonales y mezclarlos en una sola caja invitaba a leer
            el color como si dijera algo del enlace (patrón StationView). */}
        {layers.link && (
          <div className="soc-map__legend soc-map__legend--link" data-testid="map-legend-link">
            <div className="soc-map__legend-title">Enlace con la estación</div>
            <div className="soc-map__legend-row">
              <span className="soc-map__glyph">●</span> {LINK_OPERATIVO} ·{" "}
              {linkCounts[LINK_OPERATIVO] ?? 0}
            </div>
            <div className="soc-map__legend-row">
              <span className="soc-map__glyph">{LINK_GLYPH[LINK_DEGRADADO]}</span> {LINK_DEGRADADO}{" "}
              · {linkCounts[LINK_DEGRADADO] ?? 0}
            </div>
            <div className="soc-map__legend-row">
              <span className="soc-map__glyph">{LINK_GLYPH[LINK_SIN_ENLACE]}</span>{" "}
              {LINK_SIN_ENLACE} · {linkCounts[LINK_SIN_ENLACE] ?? 0}
            </div>
            <div className="soc-map__legend-row">
              <span className="soc-map__glyph">{LINK_GLYPH[LINK_SIN_GABINETE]}</span>{" "}
              {LINK_SIN_GABINETE} · {linkCounts[LINK_SIN_GABINETE] ?? 0}
            </div>
            <div className="soc-map__legend-note">
              NÚCLEO HUECO Y APAGADO = EL COLOR NO ES UNA LECTURA VIVA
            </div>
          </div>
        )}

        {/* El color de cada punto es la SACUDIDA QUE MIDIÓ ESE EDIFICIO, no la
            severidad de la alerta ni la magnitud del sismo: son cosas distintas y
            el mapa dice cuál está mostrando. Las bandas son las del rule_set que
            arma los actuadores, así que el color y el disparo hablan el mismo
            idioma. El epicentro va aparte porque NO es un edificio. */}
        <div className="soc-map__legend">
          <div className="soc-map__legend-title">SACUDIDA MEDIDA EN EL EDIFICIO</div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.trip }} />
            <span className="soc-map__glyph">{FELT_GLYPH.trip}</span> Superó disparo
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.watch }} />
            <span className="soc-map__glyph">{FELT_GLYPH.watch}</span> Superó cautela
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.normal }} />
            {/* [T-6.09] El tranquilo no lleva marca, y la leyenda lo dice con un
                hueco del MISMO ancho: si el renglón se encogiera, la columna de
                glifos dejaría de leerse como una columna. */}
            <span className="soc-map__glyph" aria-hidden="true" />
            Bajo umbral
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.unknown }} />
            <span className="soc-map__glyph">{FELT_GLYPH.unknown}</span> Sin dato
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: EPICENTER_COLOR }} />
            <span className="soc-map__glyph" aria-hidden="true" />
            Epicentro
          </div>
          {epicenters.length === 0 && (
            <div className="soc-map__legend-note" data-testid="map-no-epicenter">
              SIN EPICENTRO LOCALIZADO
            </div>
          )}
          {anyUncalibrated && (
            <div className="soc-map__legend-note" data-testid="map-uncalibrated">
              ○ SIN CALIBRAR · PGA RELATIVO
            </div>
          )}
          <button
            type="button"
            className={`soc-map__legend-toggle${layers.catalog ? " soc-map__legend-toggle--on" : ""}`}
            data-testid="catalog-toggle"
            aria-pressed={layers.catalog}
            onClick={toggle("catalog")}
          >
            <span className="soc-map__sw" style={{ background: CATALOG_COLOR }} /> CATÁLOGO
            HISTÓRICO 1985–2022 · {layers.catalog ? "ON" : "OFF"}
          </button>
          {layers.catalog && catalogError && (
            <div className="soc-map__legend-note" data-testid="catalog-error">
              CATÁLOGO NO DISPONIBLE
            </div>
          )}
          {layers.catalog && !catalogError && catalog.length === 0 && (
            <div className="soc-map__legend-note" data-testid="catalog-empty">
              CATÁLOGO VACÍO
            </div>
          )}
          {layers.catalog && selectedCatalogId !== null && (
            <div className="soc-map__legend-note" data-testid="catalog-step2">
              PASO 2 · SELECCIONE UNA ESTACIÓN EN EL MAPA
            </div>
          )}
        </div>

        {/* [T-7.24] LA TERCERA COSA QUE PINTA ESTE MAPA: la sacudida del evento.
            Va la última de la columna a propósito —CAPAS tiene que seguir siendo
            la primera (T-7.05 · C-1)— y sólo existe si alguien alimenta la prop.

            La leyenda declara las DOS codificaciones antes que ninguna cifra,
            porque es lo que hace legible el resto: disco relleno = MEDIDO en ese
            edificio; anillo discontinuo = MODELO. Y `SIN COBERTURA` es una fila
            propia, con su radio: fuera de él no se extrapola color, y una
            ausencia sin nombre se lee como «ahí no pasó nada». */}
        {muestraSacudida && layers.shakemap && (
          <div className="soc-map__legend soc-map__legend--pga" data-testid="map-legend-pga">
            <div className="soc-map__legend-title">MAPA DE LA SACUDIDA</div>
            {/* Cada fila de codificación cuelga de la capa QUE SE ESTÁ
                PINTANDO: una leyenda que explica un anillo que no está en
                pantalla promete un modelo que no se hizo. La ausencia la nombra
                la nota de abajo, que para eso está. */}
            {sacudida.pintaObservado && (
              <div className="soc-map__legend-row">
                <span className="soc-map__sw soc-map__sw--medido" />
                MEDIDO EN EL EDIFICIO · DISCO CON SU VALOR
              </div>
            )}
            {sacudida.pintaModelado && (
              <div className="soc-map__legend-row">
                <span className="soc-map__sw soc-map__sw--modelo" />
                MODELO{shakemap?.ley != null ? ` ${shakemap.ley}` : ""} · ANILLO DISCONTINUO ·
                ESTIMACIÓN
              </div>
            )}
            {/* Las bandas son las del `rule_set` que regía el incidente y llegan
                EN los propios anillos: aquí no hay ninguna escala escrita a
                mano, y por eso el rótulo cita el umbral por su nombre. */}
            {niveles.map((nivel) => (
              <div className="soc-map__legend-row" key={nivel.umbral}>
                <span className="soc-map__sw" style={{ background: colorDeBanda(nivel.umbral) }} />
                {nivel.pga_g.toFixed(3)} g · {nivel.umbral}
              </div>
            ))}
            {/* `SIN COBERTURA` cuelga de que HAYA HALOS DIBUJADOS, porque es
                justo lo que explica. Colgaba de `shakemap !== undefined`, así
                que un incidente sin snapshot calculado imprimía «SIN COBERTURA
                · A MÁS DE 25 km…» junto a «ESTE INCIDENTE AÚN NO TIENE
                SNAPSHOT»: una clave de color de un mapa que no existía. Luego
                colgó de `pintaObservado` —«hay puntos»—, y un snapshot con
                puntos MUDOS volvía a prometer un límite sin un solo halo: el
                halo lo dibujan sólo los que MIDIERON. */}
            {hayCobertura && shakemap !== undefined && (
              <div className="soc-map__legend-row">
                {/* La muestra es un ARO y no un cuadro relleno, porque la capa
                    pinta un borde: una muestra rellena prometería que el mapa
                    tiñe el área de fuera, y el área de fuera es el resto del
                    mundo. El color lo pone la hoja con `var()` —aquí sí
                    resuelve— para no tener la misma tinta escrita dos veces. */}
                <span className="soc-map__sw soc-map__sw--cobertura" />
                SIN COBERTURA · A MÁS DE {shakemap.cobertura_km} km DE UN INMUEBLE INSTRUMENTADO
              </div>
            )}
            {sacudida.nota !== null && (
              <div className="soc-map__legend-note" data-testid={sacudida.notaTestId ?? undefined}>
                {sacudida.nota}
              </div>
            )}
            {/* Descartar en silencio sería cambiar un dato sospechoso por una
                pantalla tranquila: si algo llega sin procedencia, se dice. */}
            {descartados > 0 && (
              <div className="soc-map__legend-note" data-testid="shakemap-sin-procedencia">
                {descartados} RASGO(S) SIN PROCEDENCIA · NO SE PINTAN
              </div>
            )}
            {/* El mapa NO es en vivo: se calcula por evento. La hora del cálculo
                es lo que dice con qué información se hizo (regla de oro 7).
                Cuelga de que el snapshot sea LEGIBLE: fechar un mapa que la
                nota de arriba acaba de declarar ilegible lo vuelve a presentar
                como un mapa válido y reciente. */}
            {sacudida.legible && calculadoEn !== null && (
              <div className="soc-map__legend-note" data-testid="shakemap-calculado">
                CALCULADO {calculadoEn} UTC
              </div>
            )}
          </div>
        )}
      </div>

      <div className="soc-map__attribution">
        <span>◐ MapLibre GL · OpenFreeMap</span>
        <span>Map data © OpenStreetMap · Sensórica Raspberry Shake® RS4D</span>
      </div>
    </div>
  );
}
