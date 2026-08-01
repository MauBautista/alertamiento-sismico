// [T-2.28] Ley de atenuación para la comparativa histórica. Puro: ni React ni DOM.
//
// ATTEN-LAW v1: log10(PGA_g) = 0.5*M - 2.8 - log10(max(R_hipo_km, 1)) — espejo de
// api/tools/quorum_ssn_validation.py::_plausible_pga_g (la fuente, con ancla en su
// docstring) y del panel del gabinete (T-2.27). Ley ILUSTRATIVA y determinista:
// alimenta SOLO una comparativa informativa, jamás decisiones ni actuadores, y NO
// es el mini-ShakeMap del blueprint §14 (cero interpolación espacial, cero IA).

/** Velocidad de la onda P (km/s) — espejo de `quorum_v_p_km_s` de la nube. */
export const V_P_KM_S = 6.5;

/** Distancia hipocentral: hipotenusa de la epicentral y la profundidad.
 * Sin profundidad reportada degrada a la epicentral (y la UI lo declara). */
export function hypoKm(epiKm: number, depthKm: number | null): number {
  return depthKm === null ? epiKm : Math.hypot(epiKm, depthKm);
}

/** PGA estimado (g) a distancia hipocentral `rKm`. Piso de 1 km: sin singularidad. */
export function pgaLawG(magnitude: number, rKm: number): number {
  return 10 ** (0.5 * magnitude - 2.8) / Math.max(rKm, 1);
}

/** Arribo teórico de la onda P (s) — modelo de una capa, como `_p_travel_s`. */
export function pTravelS(rKm: number): number {
  return rKm / V_P_KM_S;
}

export interface AttenPoint {
  km: number;
  g: number;
}

/** Muestreo uniforme de la curva en distancia EPICENTRAL [0, maxKm]. */
export function attenPoints(
  magnitude: number,
  depthKm: number | null,
  maxKm: number,
  n = 120,
): AttenPoint[] {
  const points: AttenPoint[] = [];
  for (let i = 0; i <= n; i += 1) {
    const km = (maxKm * i) / n;
    points.push({ km, g: pgaLawG(magnitude, hypoKm(km, depthKm)) });
  }
  return points;
}
