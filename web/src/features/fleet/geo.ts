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

/** Radio terrestre medio (km) — el mismo del haversine del panel del gabinete. */
const EARTH_R_KM = 6371;

/** [T-2.28] Distancia lineal de gran círculo en km — espejo de `haversine()` del
 * panel edge (index.html). Es la "distancia lineal" que ve el operador. */
export function haversineKm(a: LonLat, b: LonLat): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R_KM * Math.asin(Math.sqrt(s));
}

/** Rosa de 16 puntos EN ESPAÑOL (O = oeste), como la habla el panel del gabinete. */
const ROSE_16 = [
  "N",
  "NNE",
  "NE",
  "ENE",
  "E",
  "ESE",
  "SE",
  "SSE",
  "S",
  "SSO",
  "SO",
  "OSO",
  "O",
  "ONO",
  "NO",
  "NNO",
] as const;

/** [T-2.28] Rumbo de 16 puntos desde `a` hacia `b` — espejo de `bearing()` del panel. */
export function bearing16(a: LonLat, b: LonLat): string {
  const rad = Math.PI / 180;
  const y = Math.sin((b.lon - a.lon) * rad) * Math.cos(b.lat * rad);
  const x =
    Math.cos(a.lat * rad) * Math.sin(b.lat * rad) -
    Math.sin(a.lat * rad) * Math.cos(b.lat * rad) * Math.cos((b.lon - a.lon) * rad);
  const deg = (Math.atan2(y, x) / rad + 360) % 360;
  return ROSE_16[Math.round(deg / 22.5) % 16];
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
