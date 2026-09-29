// [T-9.63 · T-9.65] Lo que el mapa le pide a MapLibre y lo que lee la persona.
import type { MapaDeCalorMovilOut, SismosDelSitioOut } from "@takab/sdk";
import { render, within } from "@testing-library/react-native";

import { ATRIBUCION_BASE } from "./capas";
import { MapaSismos, SIN_MAPA_DE_CALOR } from "./MapaSismos";

let mockEscritura: "ok" | "falla" = "ok";
jest.mock("expo-file-system", () => ({
  Paths: { cache: "file:///cache" },
  File: jest.fn().mockImplementation((_dir: string, nombre: string) => ({
    exists: false,
    delete: jest.fn(),
    create: jest.fn(),
    write: jest.fn(() => {
      if (mockEscritura === "falla") throw new Error("disco lleno");
    }),
    uri: `file:///cache/${nombre}`,
  })),
}));

const SISMOS: SismosDelSitioOut = {
  actualizado: "2026-09-28T10:00:00Z",
  atribucion: "Fuente: USGS (dominio público)",
  sync_estado: "ok",
  items: [
    {
      origin_time: "2026-09-20T10:00:00Z",
      magnitude: 5.4,
      place: "Pinotepa",
      lat: 16.2,
      lon: -98.1,
      depth_km: 20,
      review_status: "reviewed",
      usgs_url: null,
      en_tu_inmueble: {
        dist_km: 280,
        metodo: "m",
        mmi_estimada: 4.2,
        mmi_romano: "IV",
        pga_estimada_g: 0.01,
      },
    },
  ],
};

const SITIO = { lat: 19.04, lon: -98.2 };

function conEvento(bbox: number[] = [-99, 18, -97, 20]): MapaDeCalorMovilOut {
  return {
    estado: "disponible",
    sitio: SITIO,
    incidente: {
      incident_id: "inc-1",
      opened_at: "2026-09-19T18:40:00Z",
      superficie: {
        bbox,
        ancho: 96,
        alto: 64,
        n_sensores: 3,
        n_calibrados: 2,
        escala_km: 15,
        ley: "ATTEN-LAW v1",
        metodo: "m",
        cita_mmi: "Wald et al. (1999)",
        pga_max_g: 0.06,
        mmi_max_estimada: 5.8,
        verde_max_g: 0.04,
        rojo_min_g: 0.1,
        png_base64: "iVBORw0KGgo=",
      },
    },
  };
}

const SIN_EVENTO: MapaDeCalorMovilOut = { estado: "sin_evento", incidente: null, sitio: SITIO };

beforeEach(() => {
  mockEscritura = "ok";
});

it("pega la superficie sobre sus cuatro esquinas, desde el fichero del incidente", async () => {
  const v = await render(<MapaSismos mapa={conEvento()} sismos={SISMOS} />);
  const img = v.getByTestId("maplibre-ImageSource-superficie");
  expect(img.props.coordinates).toEqual([
    [-99, 20],
    [-97, 20],
    [-97, 18],
    [-99, 18],
  ]);
  expect(img.props.url).toBe("file:///cache/mapa-de-calor-inc-1.png");
  expect(v.getByTestId("mapa-calor-rotulo").props.children).toBe(
    "ESTIMADO a partir de 3 sensores (2 calibrados) · MMI estimada (Wald 1999), no observada",
  );
  expect(v.queryByTestId("mapa-calor-sin-pintar")).toBeNull();
});

it("centra en el inmueble y lo marca", async () => {
  const v = await render(<MapaSismos mapa={SIN_EVENTO} sismos={SISMOS} />);
  expect(v.getByTestId("maplibre-Camera-").props.initialViewState.center).toEqual([-98.2, 19.04]);
  expect(v.getByTestId("maplibre-GeoJSONSource-inmueble").props.data.coordinates).toEqual([
    -98.2, 19.04,
  ]);
});

it("los sismos van con el radio y el color de la escala compartida", async () => {
  const v = await render(<MapaSismos mapa={SIN_EVENTO} sismos={SISMOS} />);
  const fc = v.getByTestId("maplibre-GeoJSONSource-sismos").props.data;
  expect(fc.features).toHaveLength(1);
  expect(v.getByTestId("maplibre-Layer-sismos").props.paint["circle-radius"]).toEqual([
    "get",
    "radio",
  ]);
});

it("sin evento lo DICE y no pega ninguna imagen", async () => {
  const v = await render(<MapaSismos mapa={SIN_EVENTO} sismos={SISMOS} />);
  expect(v.queryByTestId("maplibre-ImageSource-superficie")).toBeNull();
  expect(v.getByTestId("mapa-calor-sin-evento").props.children).toBe(SIN_MAPA_DE_CALOR);
});

it("un bbox ilegible no se pega volteado: se avisa", async () => {
  const v = await render(<MapaSismos mapa={conEvento([-97, 18, -99, 20])} sismos={SISMOS} />);
  expect(v.queryByTestId("maplibre-ImageSource-superficie")).toBeNull();
  expect(v.getByTestId("mapa-calor-sin-pintar")).toBeTruthy();
});

it("si no se pudo escribir la imagen, se avisa en vez de un mapa sin calor callado", async () => {
  mockEscritura = "falla";
  const v = await render(<MapaSismos mapa={conEvento()} sismos={SISMOS} />);
  expect(v.queryByTestId("maplibre-ImageSource-superficie")).toBeNull();
  expect(v.getByTestId("mapa-calor-sin-pintar")).toBeTruthy();
});

it("el crédito del mapa base y el de los sismos están A LA VISTA", async () => {
  const v = await render(<MapaSismos mapa={SIN_EVENTO} sismos={SISMOS} />);
  const pie = within(v.getByTestId("mapa-atribucion"));
  expect(pie.getByText(ATRIBUCION_BASE)).toBeTruthy();
  expect(pie.getByText(SISMOS.atribucion as string)).toBeTruthy();
  expect(v.getByTestId("mapa-sismos").props.attribution).toBe(false);
});
