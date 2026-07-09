// Helpers geográficos puros (T-1.36). Sin React, sin MapLibre: testeables solos.
//
// La ubicación de una estación no es cosmética: la ventana de asociación del quórum
// depende de la distancia entre sitios (`|Δt| ≤ dist/v_P + margen`, blueprint §4.5).
// Un signo invertido en la longitud mueve un edificio de Puebla al Índico.

/** Centro por defecto del selector: Puebla, donde vive la flota dev. */
export const DEFAULT_PICK: LonLat = { lon: -98.2, lat: 19.04 };

export interface LonLat {
  lon: number;
  lat: number;
}

export function isValidLat(lat: number): boolean {
  return Number.isFinite(lat) && lat >= -90 && lat <= 90;
}

export function isValidLon(lon: number): boolean {
  return Number.isFinite(lon) && lon >= -180 && lon <= 180;
}

export function isValidPoint(point: LonLat): boolean {
  return isValidLat(point.lat) && isValidLon(point.lon);
}

/** Redondeo a 6 decimales ≈ 11 cm. Más precisión que eso es ruido del GPS. */
export function roundPoint(point: LonLat): LonLat {
  return { lon: round6(point.lon), lat: round6(point.lat) };
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** Etiqueta N/S · E/W, como en el resto del SOC. */
export function formatPoint({ lat, lon }: LonLat): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${ns} · ${Math.abs(lon).toFixed(4)}°${ew}`;
}

/**
 * Parsea "lat, lon" pegado del portapapeles (el formato que dan Google Maps y el GPS).
 *
 * OJO al orden: los humanos escriben lat,lon; GeoJSON y MapLibre usan lon,lat. Aquí se
 * acepta el orden humano y se devuelve el de la máquina. `null` si no es un par válido.
 */
export function parseLatLonPair(text: string): LonLat | null {
  const parts = text.split(/[,;\s]+/).filter(Boolean);
  if (parts.length !== 2) return null;
  const lat = Number(parts[0]);
  const lon = Number(parts[1]);
  if (!isValidLat(lat) || !isValidLon(lon)) return null;
  return roundPoint({ lat, lon });
}
