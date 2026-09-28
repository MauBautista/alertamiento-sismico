// [T-9.62 · T-9.66] Los dos hooks de la pestaña SISMOS: qué le preguntan a la
// nube, qué hacen sin sitio y qué devuelven cuando la red falla.
import {
  historialSismicoSitesSiteIdHistorialSismicoGet,
  sismosDelSitioSitesSiteIdSismosGet,
} from "@takab/sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { HISTORIAL_DIAS, SISMOS_DIAS, SISMOS_MIN_MAG, useHistorialSismico, useSismos } from "./useSismos";

jest.mock("@takab/sdk", () => ({
  sismosDelSitioSitesSiteIdSismosGet: jest.fn(),
  historialSismicoSitesSiteIdHistorialSismicoGet: jest.fn(),
}));

const sismos = sismosDelSitioSitesSiteIdSismosGet as jest.Mock;
const historial = historialSismicoSitesSiteIdHistorialSismicoGet as jest.Mock;

const SITE = "11111111-1111-1111-1111-111111111111";
const RESPUESTA = { actualizado: null, atribucion: "USGS", items: [], sync_estado: "nunca" };

const clientes: QueryClient[] = [];
afterEach(() => {
  for (const c of clientes.splice(0)) {
    c.clear();
  }
});

function envoltorio() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clientes.push(qc);
  function Envoltorio({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Envoltorio;
}

beforeEach(() => {
  sismos.mockReset();
  historial.mockReset();
  sismos.mockResolvedValue({ data: RESPUESTA, response: { status: 200 } });
  historial.mockResolvedValue({ data: { eventos: [] }, response: { status: 200 } });
});

describe("useSismos", () => {
  it("pide los de M 4.0 o más de los últimos 90 días DEL SITIO", async () => {
    const r = await renderHook(() => useSismos(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    expect(sismos).toHaveBeenCalledWith({
      path: { site_id: SITE },
      query: { dias: SISMOS_DIAS, min_mag: SISMOS_MIN_MAG },
    });
    expect([SISMOS_DIAS, SISMOS_MIN_MAG]).toEqual([90, 4]);
    expect(r.result.current.loading).toBe(false);
    expect(r.result.current.error).toBeNull();
    expect(r.result.current.staleSinceMs).toBeNull();
  });

  it("sin sitio no pregunta ni se queda «cargando» para siempre", async () => {
    const r = await renderHook(() => useSismos(null), { wrapper: envoltorio() });
    await act(async () => {});
    expect(sismos).not.toHaveBeenCalled();
    expect(r.result.current.loading).toBe(false);
    expect(r.result.current.data).toBeNull();
  });

  it("si la nube no contesta, error con texto y SIN dato inventado", async () => {
    sismos.mockResolvedValue({ data: undefined, error: { detail: "x" }, response: { status: 503 } });
    const r = await renderHook(() => useSismos(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.error).not.toBeNull());
    expect(r.result.current.data).toBeNull();
    expect(r.result.current.loading).toBe(false);
  });

  it("si `fetch` muere (el SDK lanza), también es error y no un giro eterno", async () => {
    sismos.mockRejectedValue(new TypeError("Network request failed"));
    const r = await renderHook(() => useSismos(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.error).not.toBeNull());
  });

  it("refrescar (tirar hacia abajo) vuelve a preguntar y se apaga al terminar", async () => {
    const r = await renderHook(() => useSismos(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    await act(async () => {
      await r.result.current.refrescar();
    });
    expect(sismos).toHaveBeenCalledTimes(2);
    expect(r.result.current.refrescando).toBe(false);
  });
});

describe("useHistorialSismico", () => {
  it("pide el historial del sitio del último año", async () => {
    const r = await renderHook(() => useHistorialSismico(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    expect(historial).toHaveBeenCalledWith({
      path: { site_id: SITE },
      query: { dias: HISTORIAL_DIAS },
    });
    expect(HISTORIAL_DIAS).toBe(365);
  });

  it("sin sitio no pregunta", async () => {
    await renderHook(() => useHistorialSismico(null), { wrapper: envoltorio() });
    await act(async () => {});
    expect(historial).not.toHaveBeenCalled();
  });

  it("la nube caída es error, no un historial vacío", async () => {
    historial.mockRejectedValue(new TypeError("Network request failed"));
    const r = await renderHook(() => useHistorialSismico(SITE), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.error).not.toBeNull());
    expect(r.result.current.data).toBeNull();
  });
});
