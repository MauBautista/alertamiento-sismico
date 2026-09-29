// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-9.63 · T-9.65] SISMOS → VER EN EL MAPA: nació con su prueba de cuatro
// estados. La pantalla depende de DOS lecturas (los sismos y el mapa de calor
// del inmueble) y aquí se mide que un fallo de CUALQUIERA de las dos se dice.
import type { MapaDeCalorMovilOut, SismosDelSitioOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import MapaDeSismos from "@/app/mapa-sismos";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = Date.now();

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => mockSitio }));

type Lectura<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  staleSinceMs: number | null;
  refetch: jest.Mock;
};
let mockSismos: Lectura<SismosDelSitioOut> & { refrescando: boolean; refrescar: jest.Mock };
let mockMapa: Lectura<MapaDeCalorMovilOut>;
jest.mock("@/features/sismos/useSismos", () => ({
  ...jest.requireActual("@/features/sismos/useSismos"),
  useSismos: () => mockSismos,
}));
jest.mock("@/features/mapa/useMapaDeCalor", () => ({ useMapaDeCalor: () => mockMapa }));

const CATALOGO: SismosDelSitioOut = {
  actualizado: new Date(AHORA - 60_000).toISOString(),
  atribucion: "Fuente: USGS (dominio público)",
  items: [],
  sync_estado: "ok",
};
const MAPA: MapaDeCalorMovilOut = {
  estado: "sin_evento",
  incidente: null,
  sitio: { lat: 19.04, lon: -98.2 },
};

function lectura<T>(over: Partial<Lectura<T>> = {}): Lectura<T> {
  return { data: null, loading: false, error: null, staleSinceMs: null, refetch: jest.fn(), ...over };
}

beforeEach(() => {
  mockSitio = SITE;
  mockSismos = {
    ...lectura<SismosDelSitioOut>({ data: CATALOGO }),
    refrescando: false,
    refrescar: jest.fn(),
  };
  mockMapa = lectura<MapaDeCalorMovilOut>({ data: MAPA });
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

describe("MAPA DE SISMOS · qué lee la persona cuando algo falta", () => {
  it("con las dos lecturas, el mapa", async () => {
    const v = await render(<MapaDeSismos />);
    await asentar();
    expect(v.getByTestId("mapa-sismos")).toBeTruthy();
  });

  it("si falla el mapa de calor, se DICE aunque los sismos hayan llegado", async () => {
    mockMapa = lectura<MapaDeCalorMovilOut>({ error: "No se pudo consultar el mapa de calor." });
    const v = await render(<MapaDeSismos />);
    await asentar();
    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.queryByTestId("mapa-sismos")).toBeNull();
  });

  it("reintentar RE-CONSULTA las dos", async () => {
    mockSismos = { ...mockSismos, data: null, error: "sin red" };
    const v = await render(<MapaDeSismos />);
    await asentar();
    await act(async () => {
      fireEvent.press(v.getByTestId("state-retry"));
    });
    expect(mockSismos.refetch).toHaveBeenCalledTimes(1);
    expect(mockMapa.refetch).toHaveBeenCalledTimes(1);
  });

  it("el dato retenido se declara con la edad del MÁS viejo de los dos", async () => {
    mockSismos = { ...mockSismos, staleSinceMs: AHORA - 5 * 60_000 };
    mockMapa = lectura<MapaDeCalorMovilOut>({ data: MAPA, staleSinceMs: AHORA - 40 * 60_000 });
    const v = await render(<MapaDeSismos />);
    await asentar();
    expect(v.getByTestId("state-stale")).toBeTruthy();
    expect(v.getByText(/hace 40 min/)).toBeTruthy();
  });
});

describe("MAPA DE SISMOS · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSismos = {
          ...lectura<SismosDelSitioOut>({
            loading: e === "loading",
            error: e === "error" ? "No se pudo consultar el catálogo de sismos." : null,
            data: e === "stale" ? CATALOGO : null,
            staleSinceMs: e === "stale" ? AHORA - 20 * 60_000 : null,
          }),
          refrescando: false,
          refrescar: jest.fn(),
        };
        mockMapa = lectura<MapaDeCalorMovilOut>({ data: e === "stale" ? MAPA : null });
        return <MapaDeSismos />;
      },
      { asentar },
    );
  });
});
