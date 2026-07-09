// Unidades honestas de PGA/PGV (T-1.33).
//
// El edge escala counts→físico con las sensibilidades PLACEHOLDER de `SignalConfig`,
// a la espera del StationXML del RS4D. Hasta que un sensor declare su
// `calibration_source`, sus números NO son `g` ni `cm/s`: son cuentas escaladas.
// Pintarlos con unidades físicas sería inventarse una magnitud — la misma clase de
// mentira que prohíbe la regla de oro 7 para el dato `stale`.
//
// Default-deny: `undefined` (aún cargando, o un backend viejo que no manda el flag)
// se trata como SIN CALIBRAR. Preferimos avisar de más que engañar una vez.

export interface Units {
  /** Unidad del pico de aceleración. */
  pga: string;
  /** Unidad del pico de velocidad. */
  pgv: string;
}

export const CALIBRATED_UNITS: Units = { pga: "g", pgv: "cm/s" };

/** `rel.` = relativo a la escala placeholder del edge; comparable consigo mismo,
 *  no con la física ni con otro sitio calibrado distinto. */
export const UNCALIBRATED_UNITS: Units = { pga: "rel.", pgv: "rel." };

export function unitsFor(calibrated: boolean | undefined): Units {
  return calibrated === true ? CALIBRATED_UNITS : UNCALIBRATED_UNITS;
}

/** ¿Debe la UI advertir que estos números no tienen anclaje físico? */
export function needsCalibrationWarning(calibrated: boolean | undefined): boolean {
  return calibrated !== true;
}
