import { describe, expect, it } from "vitest";

import { formatPoint, isValidPoint, parseLatLonPair, roundPoint } from "./geo";

describe("isValidPoint", () => {
  it("acepta el rango geográfico real", () => {
    expect(isValidPoint({ lat: 19.06, lon: -98.3 })).toBe(true);
    expect(isValidPoint({ lat: -90, lon: 180 })).toBe(true);
  });

  it("rechaza lo que no es una coordenada", () => {
    expect(isValidPoint({ lat: 91, lon: 0 })).toBe(false);
    expect(isValidPoint({ lat: 0, lon: 181 })).toBe(false);
    expect(isValidPoint({ lat: Number.NaN, lon: 0 })).toBe(false);
  });
});

describe("roundPoint", () => {
  it("recorta a 6 decimales (~11 cm): más que eso es ruido del GPS", () => {
    expect(roundPoint({ lat: 19.0633331234, lon: -98.30140009 })).toEqual({
      lat: 19.063333,
      lon: -98.3014,
    });
  });
});

describe("formatPoint", () => {
  it("rotula hemisferio, como el resto del SOC", () => {
    expect(formatPoint({ lat: 19.0633, lon: -98.3014 })).toBe("19.0633°N · 98.3014°W");
    expect(formatPoint({ lat: -33.4, lon: 151.2 })).toBe("33.4000°S · 151.2000°E");
  });
});

describe("parseLatLonPair", () => {
  it("acepta el orden HUMANO (lat, lon) y devuelve el de la máquina", () => {
    // Google Maps y los GPS dan "19.0633, -98.3014"; GeoJSON quiere [lon, lat].
    expect(parseLatLonPair("19.0633, -98.3014")).toEqual({ lat: 19.0633, lon: -98.3014 });
  });

  it("tolera espacios y punto y coma", () => {
    expect(parseLatLonPair("19.0633 -98.3014")).toEqual({ lat: 19.0633, lon: -98.3014 });
    expect(parseLatLonPair("19.0633;-98.3014")).toEqual({ lat: 19.0633, lon: -98.3014 });
  });

  it("rechaza pares imposibles en vez de colocar la estación en el mar", () => {
    // 98.3 no es una latitud válida: quien pegó lon,lat invertido debe verlo fallar.
    expect(parseLatLonPair("-98.3014, 19.0633")).toBeNull();
    expect(parseLatLonPair("19.0633")).toBeNull();
    expect(parseLatLonPair("hola, mundo")).toBeNull();
    expect(parseLatLonPair("1, 2, 3")).toBeNull();
  });
});
