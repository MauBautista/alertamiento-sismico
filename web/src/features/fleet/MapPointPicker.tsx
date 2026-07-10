// Selector de punto en el mapa (T-1.36): marcador arrastrable sobre MapLibre.
//
// Componente NUEVO a propósito. `MapPanel` es el wall de la consola: sus capas, su
// pulso rAF y sus anillos MMI no tienen nada que ver con "elegir dónde está un
// edificio", y sobrecargarlo habría acoplado el camino de vigilancia al de alta.
//
// Fuente de verdad = la prop `value`. Arrastrar el marcador NOTIFICA; no muta estado
// interno. Así el formulario y el mapa nunca discrepan sobre dónde está la estación.

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

import { observeMapResize } from "../../lib/maplibre";
import { MAP_STYLE_URL } from "../console/MapPanel";
import { formatPoint, roundPoint } from "./geo";
import type { LonLat } from "./geo";

const PICK_ZOOM = 13;

export interface MapPointPickerProps {
  value: LonLat;
  onChange: (point: LonLat) => void;
  /** Solo lectura: se ve dónde está, no se puede mover. */
  disabled?: boolean;
}

export default function MapPointPicker({ value, onChange, disabled = false }: MapPointPickerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // Encuadre inicial. Vive en una ref y NO en las dependencias del efecto: si el mapa
  // se recreara en cada arrastre, el operador perdería su zoom y su paneo a media alta.
  const initialRef = useRef(value);

  useEffect(() => {
    if (containerRef.current === null) return undefined;
    const start = initialRef.current;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: [start.lon, start.lat],
      zoom: PICK_ZOOM,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    // [T-1.54] El form aparece por swap tabla↔form: el layout se asienta
    // DESPUÉS del constructor y el canvas quedaba mal medido (marcador
    // desalineado / mapa cortado). El observer lo corrige en cuanto el
    // contenedor toma su tamaño real.
    const stopResize = observeMapResize(map, containerRef.current);

    const marker = new maplibregl.Marker({ draggable: !disabled, color: "#00BFFF" })
      .setLngLat([start.lon, start.lat])
      .addTo(map);
    markerRef.current = marker;

    marker.on("dragend", () => {
      const { lng, lat } = marker.getLngLat();
      onChangeRef.current(roundPoint({ lon: lng, lat }));
    });

    // Un clic en el mapa también coloca la estación: arrastrar un marcador de 20 px
    // sobre una azotea es más incómodo que apuntar.
    if (!disabled) {
      map.on("click", (event) => {
        onChangeRef.current(roundPoint({ lon: event.lngLat.lng, lat: event.lngLat.lat }));
      });
    }

    return () => {
      stopResize();
      markerRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, [disabled]);

  // La prop manda: si el formulario cambia lat/lon a mano, el marcador sigue.
  useEffect(() => {
    markerRef.current?.setLngLat([value.lon, value.lat]);
  }, [value.lon, value.lat]);

  return (
    <div className="fleet__picker" data-testid="map-point-picker">
      <div ref={containerRef} className="fleet__pickermap" />
      <p className="soc-mono fleet__pickercoords" data-testid="picker-coords">
        {formatPoint(value)}
      </p>
    </div>
  );
}
