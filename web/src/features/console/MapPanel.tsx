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
//  · NO hay intensidad sísmica interpolada: ni isosistas, ni bandas MMI, ni radio
//    de "hasta dónde se sintió". Eso es el mini-ShakeMap del BLUEPRINT §14 (fase
//    futura). Ver el comentario en la carga de capas.
//  · NO hay cuenta regresiva T-MINUS ni magnitud preliminar (`CLAUDE.md §8`).

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CatalogEarthquakeOut, MapEpicenter, MapSiteState } from "@takab/sdk";

import { observeMapResize } from "../../lib/maplibre";
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
import { sitesInBounds, type ViewBounds } from "./stats";
import {
  DASH_FRAMES,
  animatableEpicenters,
  dashFrameIndex,
  epicenterLinks,
  kmToPixels,
  staticRings,
  waveRadiiKm,
  WAVE_MAX_AGE_S,
} from "./wavefront";

/** Lo que `GeoJSONSource.setData` acepta. El namespace global `GeoJSON` no está
 * en el `types` del tsconfig: se deriva del propio tipo de MapLibre. */
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

export const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/dark";

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
      const label = e.node_count != null ? `${base} · ${e.node_count} est.` : base;
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [e.lon, e.lat] },
        properties: { event_id: e.event_id, node_count: e.node_count ?? null, label },
      };
    }),
  };
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
        label: `M ${q.magnitude.toFixed(1)} · ${q.origin_time.slice(0, 4)} · ${q.source}`,
        selected: q.ref_id === selectedId,
      },
    })),
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
}

export const DEFAULT_LAYERS: LayerToggles = {
  stations: true,
  epicenters: true,
  catalog: false,
  link: true,
  waves: true,
};

const LAYERS_OF: Record<keyof LayerToggles, string[]> = {
  stations: ["site-halo", "site-core", "pulse"],
  epicenters: ["epicenter-halo", "epicenter-mark", "epicenter-label"],
  catalog: ["catalog-mark", "catalog-label"],
  link: ["site-link"],
  waves: ["wave-link", "wave-p", "wave-s", "wave-static-ring", "wave-static-label"],
};

const LAYER_LABEL: Record<keyof LayerToggles, string> = {
  stations: "ESTACIONES",
  epicenters: "EPICENTROS",
  catalog: "CATÁLOGO",
  link: "ENLACE",
  waves: "ONDAS",
};

export interface MapPanelProps {
  sites: MapSiteState[];
  epicenters: MapEpicenter[];
  onSelectSite: (siteId: string) => void;
  /** Catálogo histórico (T-2.28); sin la prop, la capa no existe. */
  catalog?: CatalogEarthquakeOut[];
  catalogError?: boolean;
  selectedCatalogId?: string | null;
  onSelectCatalog?: (refId: string) => void;
  /** [T-2.50] Estaciones dentro del viewport actual (moveend + getBounds). */
  onViewportChange?: (visibleSiteIds: string[]) => void;
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
      attributionControl: { compact: true },
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

      // NO hay bandas MMI. Aquí vivían dos anillos ("mmi-severa" 55px y
      // "mmi-alta" 100px) rotulados INTENSIDAD MMI que no estaban conectados a
      // ningún dato: eran constantes. Y como `circle-radius` de MapLibre es en
      // PÍXELES DE PANTALLA, el mismo anillo afirmaba ~22 km de radio en zoom
      // 8.5 y ~1 km en zoom 13 — la banda cambiaba de significado físico con
      // cada rueda del ratón. Dibujar una isosista honesta exige una intensidad
      // real, y hoy no existe: `seismic_events.magnitude` es NULL (el WR-1 solo
      // entrega un booleano) y el PGA de un sensor sin calibrar es RELATIVO, no
      // físico (db/schema.sql §sensors). Mostrar un radio inventado como si
      // fuera el área donde se sintió el sismo es exactamente lo que prohíbe la
      // regla de oro 7. El mapa de intensidades es el mini-ShakeMap del
      // BLUEPRINT §14 — fase futura.
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
        const source = map.getSource("wave-static") as maplibregl.GeoJSONSource | undefined;
        source?.setData(
          staticRingsFeatureCollection(
            animatableEpicenters(epicentersRef.current, Date.now()),
            map.getZoom?.() ?? DEFAULT_ZOOM,
          ) as unknown as SourceData,
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
            const { radius, strokeOpacity } = pulseAt(t - start);
            map.setPaintProperty("pulse", "circle-radius", radius);
            map.setPaintProperty("pulse", "circle-stroke-opacity", strokeOpacity);
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
    if (reducedMotion && map.getLayer("wave-link") !== undefined) {
      // Dash CONGELADO en su primer fotograma: el interruptor apaga TODO
      // movimiento, incluido el de la línea.
      map.setPaintProperty("wave-link", "line-dasharray", [...DASH_FRAMES[0]]);
    }
  }, [sites, live, newest, reducedMotion, styleReady]);

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
  const toggle = (key: keyof LayerToggles) => () =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="soc-map" data-testid="map-panel">
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
      </div>

      <div className="soc-map__legends">
        {/* [T-2.50] Capas conmutables: el operador decide qué mira. */}
        <div className="soc-map__legend soc-map__legend--layers" data-testid="map-layers">
          <div className="soc-map__legend-title">CAPAS</div>
          <div className="soc-map__layer-row">
            {(Object.keys(LAYER_LABEL) as (keyof LayerToggles)[]).map((key) => (
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
              {reducedMotion ? " · ANILLOS ESTÁTICOS (MOVIMIENTO REDUCIDO)" : ""}
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
            <span className="soc-map__sw" style={{ background: FELT_COLOR.trip }} /> Superó disparo
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.watch }} /> Superó cautela
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.normal }} /> Bajo umbral
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: FELT_COLOR.unknown }} /> Sin dato
          </div>
          <div className="soc-map__legend-row">
            <span className="soc-map__sw" style={{ background: EPICENTER_COLOR }} /> Epicentro
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
      </div>

      <div className="soc-map__attribution">
        <span>◐ MapLibre GL · OpenFreeMap</span>
        <span>Map data © OpenStreetMap · Sensórica Raspberry Shake® RS4D</span>
      </div>
    </div>
  );
}
