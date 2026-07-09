import { describe, expect, it } from "vitest";

import {
  CALIBRATED_UNITS,
  UNCALIBRATED_UNITS,
  needsCalibrationWarning,
  unitsFor,
} from "./calibration";

describe("calibration", () => {
  it("solo un true explícito habilita las unidades físicas", () => {
    expect(unitsFor(true)).toEqual(CALIBRATED_UNITS);
    expect(unitsFor(true).pga).toBe("g");
    expect(unitsFor(true).pgv).toBe("cm/s");
  });

  it("sin calibrar, las unidades son relativas", () => {
    expect(unitsFor(false)).toEqual(UNCALIBRATED_UNITS);
    expect(unitsFor(false).pga).toBe("rel.");
  });

  it("undefined cae del lado seguro (default-deny)", () => {
    // Cargando, o un backend viejo que no manda el flag: nunca inventar 'g'.
    expect(unitsFor(undefined)).toEqual(UNCALIBRATED_UNITS);
    expect(needsCalibrationWarning(undefined)).toBe(true);
  });

  it("el aviso aparece salvo que esté calibrado", () => {
    expect(needsCalibrationWarning(false)).toBe(true);
    expect(needsCalibrationWarning(true)).toBe(false);
  });
});
