// [T-9.52 · D-44] El PNG de la superficie se pide CON LA SESIÓN y se pinta desde
// un `objectURL` que se revoca al cambiar de incidente o al desmontar.
//
// Lo que se prueba: que la petición pase por el cliente del SDK (Bearer y 401
// incluidos), que «cargando», «falló» y «listo» se distingan, y que ningún
// `blob:` viejo sobreviva a su incidente.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  incidentShakemapSuperficiePngIncidentsIncidentIdShakemapSuperficiePngGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { SUPERFICIE_PNG_KEY, useSuperficiePng } from "./useSuperficiePng";

const pedir = sdk.incidentShakemapSuperficiePngIncidentsIncidentIdShakemapSuperficiePngGet;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

let creados = 0;
const revocados: string[] = [];

describe("useSuperficiePng · el PNG de la superficie, con la sesión", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    creados = 0;
    revocados.length = 0;
    // jsdom no trae `createObjectURL`: se simula, contando cada URL.
    URL.createObjectURL = vi.fn(() => `blob:takab/${++creados}`);
    URL.revokeObjectURL = vi.fn((u: string) => void revocados.push(u));
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sin superficie que pedir NO consulta nada", () => {
    const { result } = renderHook(() => useSuperficiePng("i-1", null), { wrapper });
    expect(pedir).not.toHaveBeenCalled();
    expect(result.current).toEqual({ url: null, cargando: false, error: false });
  });

  it("pide el PNG por el cliente del SDK, como Blob, y lo entrega como objectURL", async () => {
    pedir.mockResolvedValue({ data: new Blob(["png"]), response: { status: 200 } });
    const { result } = renderHook(() => useSuperficiePng("i-1", "2026-09-14T10:41:30Z"), {
      wrapper,
    });
    expect(result.current.cargando).toBe(true);
    expect(result.current.url).toBeNull();
    await waitFor(() => expect(result.current.url).toBe("blob:takab/1"));
    expect(result.current).toMatchObject({ cargando: false, error: false });
    expect(pedir).toHaveBeenCalledWith({ path: { incident_id: "i-1" }, parseAs: "blob" });
  });

  it("un fallo se DECLARA, no se lee como «no hay superficie»", async () => {
    pedir.mockResolvedValue({ error: { detail: "x" }, response: { status: 500 } });
    const { result } = renderHook(() => useSuperficiePng("i-1", "c-1"), { wrapper });
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.url).toBeNull();
  });

  it("al cambiar de incidente revoca el blob viejo y NO lo devuelve mientras carga el nuevo", async () => {
    let soltar: (v: unknown) => void = () => undefined;
    pedir.mockResolvedValueOnce({ data: new Blob(["a"]), response: { status: 200 } });
    pedir.mockReturnValueOnce(new Promise((r) => (soltar = r)));
    const { result, rerender } = renderHook(({ id }) => useSuperficiePng(id, "c-1"), {
      wrapper,
      initialProps: { id: "i-1" },
    });
    await waitFor(() => expect(result.current.url).toBe("blob:takab/1"));
    rerender({ id: "i-2" });
    // Nada viejo en pantalla mientras llega el nuevo.
    expect(result.current.url).toBeNull();
    expect(result.current.cargando).toBe(true);
    await waitFor(() => expect(revocados).toContain("blob:takab/1"));
    soltar({ data: new Blob(["b"]), response: { status: 200 } });
    await waitFor(() => expect(result.current.url).toBe("blob:takab/2"));
  });

  it("al desmontar revoca el blob", async () => {
    pedir.mockResolvedValue({ data: new Blob(["png"]), response: { status: 200 } });
    const { result, unmount } = renderHook(() => useSuperficiePng("i-1", "c-1"), { wrapper });
    await waitFor(() => expect(result.current.url).toBe("blob:takab/1"));
    unmount();
    expect(revocados).toEqual(["blob:takab/1"]);
  });

  it("la clave de caché lleva la hora del cálculo: un snapshot nuevo pide otro PNG", () => {
    expect(SUPERFICIE_PNG_KEY("i-1", "a")).not.toEqual(SUPERFICIE_PNG_KEY("i-1", "b"));
  });
});
