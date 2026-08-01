// [T-2.28] Vectores de PARIDAD de la ley ATTEN-LAW v1 — los mismos números viven
// en el espejo del panel edge y en la fuente (api/tools/quorum_ssn_validation.py).
// Si esta ley deriva de sus espejos, la web y el gabinete contarían historias
// distintas sobre el mismo sismo.
import { describe, expect, it } from "vitest";

import { attenPoints, hypoKm, pgaLawG, pTravelS, V_P_KM_S } from "./attenuation";

describe("ATTEN-LAW v1 (paridad con _plausible_pga_g)", () => {
  it("vector M 7.1 · prof 57 km · epi 100 km", () => {
    const hypo = hypoKm(100, 57);
    expect(hypo).toBeCloseTo(115.1043, 3);
    expect(pgaLawG(7.1, hypo)).toBeCloseTo(0.04885, 4);
    expect(pgaLawG(7.1, 57)).toBeCloseTo(0.09866, 4); // "en el epicentro": R = profundidad
    expect(pTravelS(hypo)).toBeCloseTo(17.71, 2);
    expect(V_P_KM_S).toBe(6.5); // espejo de quorum_v_p_km_s
  });

  it("sin profundidad, la hipocentral degrada a la epicentral", () => {
    expect(hypoKm(100, null)).toBe(100);
  });

  it("el piso de 1 km evita la singularidad en el origen", () => {
    expect(pgaLawG(7.1, 0)).toBe(pgaLawG(7.1, 1));
  });

  it("la curva decae monótonamente y cubre el dominio pedido", () => {
    const pts = attenPoints(7.1, 57, 200, 120);
    expect(pts).toHaveLength(121);
    expect(pts[0].km).toBe(0);
    expect(pts[120].km).toBeCloseTo(200, 6);
    for (let i = 1; i < pts.length; i += 1) {
      expect(pts[i].g).toBeLessThanOrEqual(pts[i - 1].g);
    }
  });
});
