// Insignia SIN CALIBRAR (T-1.33): el PGA/PGV que estás viendo no es una magnitud física.

import { needsCalibrationWarning } from "./calibration";

export interface NotCalibratedBadgeProps {
  calibrated: boolean | undefined;
}

/** Nada si el sitio está calibrado; el aviso en caso contrario (incluido `undefined`). */
export default function NotCalibratedBadge({ calibrated }: NotCalibratedBadgeProps) {
  if (!needsCalibrationWarning(calibrated)) return null;
  return (
    <span
      className="soc-pill soc-pill--warn"
      data-testid="not-calibrated-badge"
      title="Las sensibilidades del sensor son provisionales (falta la respuesta instrumental del RS4D). Los valores son relativos, no g ni cm/s."
    >
      SIN CALIBRAR
    </span>
  );
}
