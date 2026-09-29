// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-9.62 · D-46] La pestaña SISMOS: nació con su prueba de cuatro estados. Aquí
// se mide además la distinción que la hace honesta: «no hubo sismos» (vacío)
// sólo se afirma con el catálogo AL DÍA; con el catálogo sin actualizar, la
// pantalla enseña la franja y NO el vacío.
import type { HistorialSismicoOut, SismoCercanoOut, SismosDelSitioOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Sismos from "@/app/(occupant)/sismos";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = Date.now();
const hace = (ms: number) => new Date(AHORA - ms).toISOString();

// ------------------------------------------------------------------ mocks

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }) }));

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

type Lectura<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  staleSinceMs: number | null;
  refetch: jest.Mock;
};
let mockSismos: Lectura<SismosDelSitioOut> & { refrescando: boolean; refrescar: jest.Mock };
let mockHistorial: Lectura<HistorialSismicoOut>;
jest.mock("@/features/sismos/useSismos", () => ({
  ...jest.requireActual("@/features/sismos/useSismos"),
  useSismos: () => mockSismos,
  useHistorialSismico: () => mockHistorial,
}));

// ------------------------------------------------------------------ datos

const SISMO: SismoCercanoOut = {
  depth_km: 15,
  lat: 17,
  lon: -99.5,
  magnitude: 6.1,
  origin_time: hace(2 * 86_400_000),
  place: "Acapulco, Gro.",
  review_status: "reviewed",
  usgs_url: null,
  en_tu_inmueble: {
    dist_km: 300,
    metodo: "estimada",
    mmi_estimada: 5.1,
    mmi_romano: "V",
    pga_estimada_g: 0.03,
  },
};

function catalogo(over: Partial<SismosDelSitioOut> = {}): SismosDelSitioOut {
  return {
    actualizado: hace(60_000),
    atribucion: "Datos: USGS",
    items: [SISMO],
    sync_estado: "ok",
    ...over,
  };
}

function lectura<T>(over: Partial<Lectura<T>> = {}): Lectura<T> {
  return { data: null, loading: false, error: null, staleSinceMs: null, refetch: jest.fn(), ...over };
}

beforeEach(() => {
  mockSitio = SITE;
  mockSismos = { ...lectura<SismosDelSitioOut>({ data: catalogo() }), refrescando: false, refrescar: jest.fn() };
  mockHistorial = lectura<HistorialSismicoOut>({ data: { eventos: [] } });
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("SISMOS · qué lee la persona cuando algo falta", () => {
  it("sin sitio vigilado dice cómo vincularse", async () => {
    mockSitio = null;
    const v = await render(<Sismos />);
    await asentar();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Vincúlese/);
  });

  it("catálogo al día y sin filas: el vacío honesto", async () => {
    mockSismos.data = catalogo({ items: [] });
    const v = await render(<Sismos />);
    await asentar();
    expect(v.getByTestId("state-empty")).toHaveTextContent("Sin sismos de M 4.0 o más en 90 días");
  });

  it("catálogo SIN actualizar y sin filas: NO afirma el vacío, enseña la franja", async () => {
    mockSismos.data = catalogo({ items: [], sync_estado: "fallido", actualizado: hace(3 * 3_600_000) });
    const v = await render(<Sismos />);
    await asentar();
    expect(v.queryByTestId("state-empty")).toBeNull();
    expect(v.getByTestId("catalogo-sin-actualizar")).toHaveTextContent(/CATÁLOGO SIN ACTUALIZAR DESDE/);
  });

  it("con datos: la lista y, encima, el historial del inmueble", async () => {
    const v = await render(<Sismos />);
    await asentar();
    expect(v.getByText("Acapulco, Gro.")).toBeTruthy();
    expect(v.getByTestId("historial-sismico")).toBeTruthy();
  });

  it("el error ofrece REINTENTAR y reintentar RE-CONSULTA", async () => {
    mockSismos = { ...mockSismos, data: null, error: "No se pudo consultar el catálogo de sismos." };
    const v = await render(<Sismos />);
    await asentar();
    await act(async () => {
      fireEvent.press(v.getByTestId("state-retry"));
    });
    expect(mockSismos.refetch).toHaveBeenCalledTimes(1);
  });
});

describe("SISMOS · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSismos = {
          ...lectura<SismosDelSitioOut>({
            loading: e === "loading",
            error: e === "error" ? "No se pudo consultar el catálogo de sismos." : null,
            data: e === "stale" ? catalogo() : null,
            staleSinceMs: e === "stale" ? AHORA - 20 * 60_000 : null,
          }),
          refrescando: false,
          refrescar: jest.fn(),
        };
        return <Sismos />;
      },
      { asentar },
    );
  });
});

describe("SISMOS · VER EN EL MAPA (T-9.63)", () => {
  it("abre la pantalla del mapa", async () => {
    mockPush.mockReset();
    const v = await render(<Sismos />);
    await asentar();
    await act(async () => {
      fireEvent.press(v.getByTestId("sismos-ver-mapa"));
    });
    expect(mockPush).toHaveBeenCalledWith("/mapa-sismos");
  });
});
