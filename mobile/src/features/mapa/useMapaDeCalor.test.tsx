// [T-9.65] El hook del mapa de calor: qué le pregunta a la nube, qué hace sin
// sitio y qué devuelve cuando la red falla.
import { mapaDeCalorSitesSiteIdMapaDeCalorGet } from "@takab/sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useMapaDeCalor } from "./useMapaDeCalor";

jest.mock("@takab/sdk", () => ({ mapaDeCalorSitesSiteIdMapaDeCalorGet: jest.fn() }));

const pide = mapaDeCalorSitesSiteIdMapaDeCalorGet as jest.Mock;
const SITE = "11111111-1111-1111-1111-111111111111";
const SIN_EVENTO = { estado: "sin_evento", incidente: null, sitio: { lat: 19.04, lon: -98.2 } };

const clientes: QueryClient[] = [];
afterEach(() => {
  for (const c of clientes.splice(0)) c.clear();
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
  pide.mockReset();
  pide.mockResolvedValue({ data: SIN_EVENTO, response: { status: 200 } });
});

it("pide el mapa DEL SITIO y entrega la respuesta tal cual", async () => {
  const r = await renderHook(() => useMapaDeCalor(SITE), { wrapper: envoltorio() });
  await waitFor(() => expect(r.result.current.data).not.toBeNull());
  expect(pide).toHaveBeenCalledWith({ path: { site_id: SITE } });
  expect(r.result.current.data).toEqual(SIN_EVENTO);
  expect(r.result.current.error).toBeNull();
  expect(r.result.current.loading).toBe(false);
});

it("sin sitio no pregunta ni se queda «cargando»", async () => {
  const r = await renderHook(() => useMapaDeCalor(null), { wrapper: envoltorio() });
  expect(pide).not.toHaveBeenCalled();
  expect(r.result.current.loading).toBe(false);
  expect(r.result.current.data).toBeNull();
});

it("un fallo sin dato previo se DICE", async () => {
  pide.mockResolvedValue({ data: undefined, response: { status: 503 } });
  const r = await renderHook(() => useMapaDeCalor(SITE), { wrapper: envoltorio() });
  await waitFor(() => expect(r.result.current.error).not.toBeNull());
  expect(r.result.current.data).toBeNull();
});
