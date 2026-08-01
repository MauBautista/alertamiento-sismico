// [T-2.28] Distancia lineal y rumbo de 16 puntos — espejo del haversine/bearing
// del panel del gabinete (edge/takab_edge/local_api/index.html).
import { describe, expect, it } from "vitest";

import { bearing16, haversineKm } from "./geo";

const CDMX = { lat: 19.4326, lon: -99.1332 };
const PUEBLA = { lat: 19.0414, lon: -98.2063 };

describe("haversineKm", () => {
  it("CDMX ↔ Puebla ≈ 106 km", () => {
    const km = haversineKm(CDMX, PUEBLA);
    expect(km).toBeGreaterThan(100);
    expect(km).toBeLessThan(112);
    expect(haversineKm(PUEBLA, CDMX)).toBeCloseTo(km, 9); // simétrica
  });

  it("mismo punto = 0", () => {
    expect(haversineKm(PUEBLA, PUEBLA)).toBe(0);
  });

  it("un grado de latitud ≈ 111 km", () => {
    expect(haversineKm({ lat: 0, lon: 0 }, { lat: 1, lon: 0 })).toBeCloseTo(111.19, 1);
  });
});

describe("bearing16", () => {
  it("los cuatro cardinales en el ecuador", () => {
    const o = { lat: 0, lon: 0 };
    expect(bearing16(o, { lat: 1, lon: 0 })).toBe("N");
    expect(bearing16(o, { lat: 0, lon: 1 })).toBe("E");
    expect(bearing16(o, { lat: -1, lon: 0 })).toBe("S");
    expect(bearing16(o, { lat: 0, lon: -1 })).toBe("O"); // oeste en español, como el panel
  });

  it("intercardinales en español (SO, no SW)", () => {
    const o = { lat: 0, lon: 0 };
    expect(bearing16(o, { lat: -1, lon: -1 })).toBe("SO");
    expect(bearing16(o, { lat: 1, lon: 1 })).toBe("NE");
  });
});
