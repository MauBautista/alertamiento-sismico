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
//  · El EPICENTRO va en su propia capa, con otra forma y otro color: es dónde se
//    ORIGINÓ el sismo y no es ningún edificio. Sin evento localizado no se dibuja
//    y la leyenda lo declara — no se planta un punto inventado.
//  · NO hay intensidad sísmica interpolada: ni isosistas, ni bandas MMI, ni radio
//    de "hasta dónde se sintió". Eso es el mini-ShakeMap del BLUEPRINT §14 (fase
//    futura). Ver el comentario en la carga de capas.

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { observeMapResize } from "../../lib/maplibre";

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
    features: epicenters.map((e) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [e.lon, e.lat] },
      properties: {
        event_id: e.event_id,
        // La magnitud es opcional a propósito: el WR-1 no la entrega y muchos
        // eventos no la tienen. Sin ella se rotula el evento, no un número falso.
        label: e.magnitude !== null ? `M ${e.magnitude.toFixed(1)}` : "EPICENTRO",
      },
    })),
  };
}

export interface MapPanelProps {
  sites: MapSiteState[];
  epicenters: MapEpicenter[];
  onSelectSite: (siteId: string) => void;
}

export default function MapPanel({ sites, epicenters, onSelectSite }: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const degradedRef = useRef(false);
  const [degraded, setDegraded] = useState(false);
  const sitesRef = useRef(sites);
  sitesRef.current = sites;
  const epicentersRef = useRef(epicenters);
  epicentersRef.current = epicenters;
  const onSelectRef = useRef(onSelectSite);
  onSelectRef.current = onSelectSite;

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
      // BLUEPRINT §14 — fase futura, no este ciclo.

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
          "circle-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "site-core",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "tripped"], 7, 5],
          "circle-color": ["get", "color"],
          // Borde punteado no se puede en `circle`: el sitio SIN CALIBRAR se
          // declara con un anillo tenue en vez del contorno sólido del navy —
          // su PGA es relativo y no puede leerse como una intensidad física.
          "circle-stroke-color": ["case", ["get", "calibrated"], "#0d2034", "#FFFFFF"],
          "circle-stroke-width": ["case", ["get", "calibrated"], 1.5, 1],
          "circle-stroke-opacity": ["case", ["get", "calibrated"], 1, 0.55],
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

      map.on("click", "site-core", (event) => {
        const feature = event.features?.[0];
        const siteId = feature?.properties?.["site_id"];
        if (typeof siteId === "string") onSelectRef.current(siteId);
      });

      if (raf !== 0) return; // el loop del pulso ya corre (re-add tras fallback)
      const start = performance.now();
      const loop = (t: number) => {
        // Entre setStyle(FALLBACK) y su style.load la capa no existe: guard.
        if (map.getLayer("pulse") !== undefined) {
          const { radius, strokeOpacity } = pulseAt(t - start);
          map.setPaintProperty("pulse", "circle-radius", radius);
          map.setPaintProperty("pulse", "circle-stroke-opacity", strokeOpacity);
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
  }, []);

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
  }, [sites, epicenters]);

  const anyUncalibrated = sites.some((s) => s.calibrated !== true);

  return (
    <div className="soc-map" data-testid="map-panel">
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />

      {degraded && (
        <div className="soc-map__degraded" data-testid="map-degraded" role="status">
          ◐ SIN MAPA BASE · TILES NO DISPONIBLES · SITIOS EN VIVO
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
      </div>

      <div className="soc-map__attribution">
        <span>◐ MapLibre GL · OpenFreeMap</span>
        <span>Map data © OpenStreetMap · Sensórica Raspberry Shake® RS4D</span>
      </div>
    </div>
  );
}
