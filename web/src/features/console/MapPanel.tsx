// Mapa GIS real del live wall (T-1.27): MapLibre GL sobre OpenFreeMap dark.
// Desviación RATIFICADA: mapa vectorial real, no el SVG esquemático del mock.
//
// Los sitios vienen de /telemetry/map/state (verdad server-side): color por
// severidad del incidente abierto (o criticidad OK). Los sitios con incidente
// crítico llevan un pulso animado por rAF (motion lineal, sin bounce — design
// system) como beacon del marcador.
//
// Este mapa NO dibuja intensidad sísmica: no hay isosistas, ni bandas MMI, ni
// radio de "dónde se sintió". Ese es el mini-ShakeMap del BLUEPRINT §14 (fase
// futura). Ver el comentario en la carga de capas.

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import type { MapSiteState } from "@takab/sdk";

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

export const SEVERITY_COLOR: Record<string, string> = {
  critical: "#FF5252",
  warning: "#FFC107",
  watch: "#FFC107",
  info: "#00E676",
  ok: "#00E676",
};

/** Severidad efectiva del sitio en el mapa (incidente abierto manda). */
export function siteSeverity(site: MapSiteState): string {
  return site.open_incident?.severity ?? "ok";
}

type FeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: Record<string, unknown>;
  }>;
};

/** GeoJSON de sitios para la capa de círculos (color y radio por severidad). */
export function sitesToFeatureCollection(sites: MapSiteState[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: sites.map((site) => {
      const severity = siteSeverity(site);
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [site.lon, site.lat] },
        properties: {
          site_id: site.site_id,
          name: site.name,
          severity,
          color: SEVERITY_COLOR[severity] ?? SEVERITY_COLOR.warning,
          critical: severity === "critical",
        },
      };
    }),
  };
}

/** Solo los sitios con incidente crítico (fuente de anillos MMI + pulso). */
export function criticalFeatures(sites: MapSiteState[]): FeatureCollection {
  return sitesToFeatureCollection(sites.filter((s) => siteSeverity(s) === "critical"));
}

export interface MapPanelProps {
  sites: MapSiteState[];
  onSelectSite: (siteId: string) => void;
}

export default function MapPanel({ sites, onSelectSite }: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const degradedRef = useRef(false);
  const [degraded, setDegraded] = useState(false);
  const sitesRef = useRef(sites);
  sitesRef.current = sites;
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
      map.addSource("critical", { type: "geojson", data: criticalFeatures(sitesRef.current) });

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

      // Pulso animado (rAF, easing lineal). Es un BEACON del marcador (atrae la
      // vista al sitio crítico), no una afirmación geográfica: por eso sí es
      // correcto que viva en píxeles y no escale con el zoom.
      map.addLayer({
        id: "pulse",
        type: "circle",
        source: "critical",
        paint: {
          "circle-radius": 15,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": "#FF5252",
          "circle-stroke-width": 1.2,
        },
      });
      // Halo + núcleo de cada sitio.
      map.addLayer({
        id: "site-halo",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "critical"], 16, 12],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "site-core",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "critical"], 7, 5],
          "circle-color": ["get", "color"],
          "circle-stroke-color": "#0d2034",
          "circle-stroke-width": 1.5,
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
    (map.getSource("critical") as maplibregl.GeoJSONSource | undefined)?.setData(
      criticalFeatures(sites),
    );
  }, [sites]);

  return (
    <div className="soc-map" data-testid="map-panel">
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />

      {degraded && (
        <div className="soc-map__degraded" data-testid="map-degraded" role="status">
          ◐ SIN MAPA BASE · TILES NO DISPONIBLES · SITIOS EN VIVO
        </div>
      )}

      {/* La leyenda declara lo que el color SIGNIFICA de verdad: la severidad
          del incidente abierto en cada sitio (`/telemetry/map/state`). Antes
          decía "INTENSIDAD MMI", que prometía una escala de intensidad sísmica
          que el sistema no calcula en ningún lado. */}
      <div className="soc-map__legend">
        <div className="soc-map__legend-title">SEVERIDAD DEL SITIO</div>
        <div className="soc-map__legend-row">
          <span className="soc-map__sw" style={{ background: "#FF5252" }} /> Crítico
        </div>
        <div className="soc-map__legend-row">
          <span className="soc-map__sw" style={{ background: "#FFC107" }} /> Advertencia
        </div>
        <div className="soc-map__legend-row">
          <span className="soc-map__sw" style={{ background: "#00E676" }} /> Sin incidente
        </div>
      </div>

      <div className="soc-map__attribution">
        <span>◐ MapLibre GL · OpenFreeMap</span>
        <span>Map data © OpenStreetMap · Sensórica Raspberry Shake® RS4D</span>
      </div>
    </div>
  );
}
