// [T-9.63 · T-9.65 · D-46 · D-44] Lo que dibuja el mapa de la app, sin mapa.
import type { SismoCercanoOut, SuperficieMovilOut } from "@takab/sdk";

import { colorDeMmi, radioDeMagnitud } from "@/features/sismos/escala";
import { palette } from "@/ui/theme";

import {
  ATRIBUCION_BASE,
  esquinasDeBbox,
  pieDelMapa,
  rotuloEstimado,
  sismosGeoJSON,
} from "./capas";

function sismo(over: Partial<SismoCercanoOut> & { mmi?: number | null } = {}): SismoCercanoOut {
  const { mmi = 4.2, ...resto } = over;
  return {
    origin_time: "2026-09-20T10:00:00Z",
    magnitude: 5.4,
    place: "12 km al S de Pinotepa",
    lat: 16.2,
    lon: -98.1,
    depth_km: 20,
    review_status: "reviewed",
    usgs_url: null,
    en_tu_inmueble: {
      dist_km: 280,
      metodo: "ATTEN-LAW v1 + Wald 1999",
      mmi_estimada: mmi,
      mmi_romano: mmi === null ? null : "IV",
      pga_estimada_g: 0.01,
    },
    ...resto,
  } as SismoCercanoOut;
}

function superficie(over: Partial<SuperficieMovilOut> = {}): SuperficieMovilOut {
  return {
    bbox: [-100, 18, -97, 20],
    ancho: 96,
    alto: 64,
    n_sensores: 3,
    n_calibrados: 2,
    escala_km: 15,
    ley: "ATTEN-LAW v1",
    metodo: "ley + residuales gaussianos",
    cita_mmi: "Wald et al. (1999)",
    pga_max_g: 0.06,
    mmi_max_estimada: 5.8,
    verde_max_g: 0.04,
    rojo_min_g: 0.1,
    png_base64: "iVBORw0KGgo=",
    ...over,
  };
}

describe("sismosGeoJSON", () => {
  it("cada sismo es un punto con el radio y el color de LA escala compartida", () => {
    const fc = sismosGeoJSON([sismo({ magnitude: 6.3, mmi: 5.6 })]);
    expect(fc.features).toHaveLength(1);
    const f = fc.features[0];
    expect(f.geometry.coordinates).toEqual([-98.1, 16.2]);
    expect(f.properties.radio).toBe(radioDeMagnitud(6.3));
    expect(f.properties.color).toBe(colorDeMmi(5.6));
  });

  it("sin intensidad estimada no se inventa un color: va el neutro", () => {
    const f = sismosGeoJSON([sismo({ mmi: null })]).features[0];
    expect(f.properties.color).toBe(palette.fg3);
  });

  it("los grandes se pintan ENCIMA de los chicos", () => {
    const fc = sismosGeoJSON([
      sismo({ magnitude: 6.8, lat: 1 }),
      sismo({ magnitude: 4.1, lat: 2 }),
      sismo({ magnitude: 5.2, lat: 3 }),
    ]);
    expect(fc.features.map((f) => f.properties.mag)).toEqual([4.1, 5.2, 6.8]);
  });
});

describe("esquinasDeBbox", () => {
  it("arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda", () => {
    expect(esquinasDeBbox([-100, 18, -97, 20])).toEqual([
      [-100, 20],
      [-97, 20],
      [-97, 18],
      [-100, 18],
    ]);
  });

  it.each([
    [[-97, 18, -100, 20]],
    [[-100, 20, -97, 18]],
    [[-100, 18, -97]],
    [[Number.NaN, 18, -97, 20]],
    [[-200, 18, -97, 20]],
  ])("un bbox ilegible (%j) NO se pinta: voltearía el rojo al otro lado", (bbox) => {
    expect(esquinasDeBbox(bbox)).toBeNull();
  });
});

describe("rotuloEstimado", () => {
  it("dice que es una estimación y de cuántos sensores sale, como la consola", () => {
    expect(rotuloEstimado(superficie())).toBe(
      "ESTIMADO a partir de 3 sensores (2 calibrados) · MMI estimada (Wald 1999), no observada",
    );
  });

  it("singular con uno", () => {
    expect(rotuloEstimado(superficie({ n_sensores: 1, n_calibrados: 1 }))).toBe(
      "ESTIMADO a partir de 1 sensor (1 calibrado) · MMI estimada (Wald 1999), no observada",
    );
  });
});

describe("pieDelMapa", () => {
  it("atribuye el mapa base y los sismos, VISIBLE, no detrás de un botón", () => {
    expect(pieDelMapa("Fuente: USGS (dominio público)")).toEqual([
      ATRIBUCION_BASE,
      "Fuente: USGS (dominio público)",
    ]);
    expect(ATRIBUCION_BASE).toMatch(/OpenStreetMap/);
  });

  it("sin atribución de sismos no se inventa una", () => {
    expect(pieDelMapa(undefined)).toEqual([ATRIBUCION_BASE]);
  });
});
