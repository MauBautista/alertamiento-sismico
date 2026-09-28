// [T-9.41] Los hooks del cierre ESPERAN al servidor y traducen lo que dijo.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  closeIncidentIncidentsIncidentIdClosePost: vi.fn(),
  getPostEventReportIncidentsIncidentIdPostEventReportGet: vi.fn(),
  confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost: vi.fn(),
  getIncidentIncidentsIncidentIdGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { CAUSA_409, cierreErrorMessage, useCerrarEvento } from "./useCerrarEvento";
import { confirmErrorMessage, useDictamenConfirm } from "./useDictamenConfirm";
import { useIncidente } from "./useIncidente";
import { useInformeAutomatico } from "./useInformeAutomatico";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("cierreErrorMessage · los cinco códigos del servidor, en español", () => {
  it.each(["ya_cerrado", "sin_acuse", "sismo_en_curso", "sin_clasificacion", "sin_dictamen"])(
    "%s se traduce y el código va detrás, nunca solo",
    (codigo) => {
      const msg = cierreErrorMessage(409, codigo);
      expect(msg).toContain(CAUSA_409[codigo]);
      expect(msg.startsWith("NO SE CERRÓ · ")).toBe(true);
      expect(msg).not.toBe(codigo);
      expect(msg.replace(`(HTTP 409 · ${codigo})`, "")).not.toContain(codigo);
    },
  );

  it("sin_dictamen pide firmar o escribir el motivo de 20 caracteres", () => {
    expect(cierreErrorMessage(409, "sin_dictamen")).toMatch(
      /FIRMA EL DICTAMEN O ESCRIBE UN MOTIVO DE AL MENOS 20 CARACTERES/,
    );
  });

  it("un 409 con un código desconocido no se inventa causa", () => {
    expect(cierreErrorMessage(409, "otra_cosa")).toBe(
      "NO SE CERRÓ · EL SERVIDOR RECHAZÓ EL CIERRE (HTTP 409) · otra_cosa",
    );
  });

  it("sin respuesta no inventa un código", () => {
    expect(cierreErrorMessage(null, null)).toBe("NO SE CERRÓ · SIN RESPUESTA DEL SERVIDOR");
  });
});

describe("useCerrarEvento", () => {
  it("manda el motivo recortado y resuelve con el cuerpo", async () => {
    sdk.closeIncidentIncidentsIncidentIdClosePost.mockResolvedValue({
      data: { incident_id: "i-1", closed_at: "x", classification: "real", sin_dictamen: true },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useCerrarEvento("i-1"), { wrapper });
    await result.current.mutateAsync("  el perito firmó en papel hoy  ");
    expect(sdk.closeIncidentIncidentsIncidentIdClosePost).toHaveBeenCalledWith({
      path: { incident_id: "i-1" },
      body: { motivo: "el perito firmó en papel hoy" },
    });
  });

  it("un 409 sin_dictamen rechaza con el texto en español", async () => {
    sdk.closeIncidentIncidentsIncidentIdClosePost.mockResolvedValue({
      data: undefined,
      error: { detail: "sin_dictamen" },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useCerrarEvento("i-1"), { wrapper });
    await expect(result.current.mutateAsync(null)).rejects.toThrow(
      /SIN DICTAMEN FIRMADO: FIRMA EL DICTAMEN/,
    );
    expect(sdk.closeIncidentIncidentsIncidentIdClosePost).toHaveBeenCalledWith({
      path: { incident_id: "i-1" },
      body: { motivo: null },
    });
  });

  it("la red caída rechaza: el cierre NO consta", async () => {
    sdk.closeIncidentIncidentsIncidentIdClosePost.mockRejectedValue(new TypeError("fetch"));
    const { result } = renderHook(() => useCerrarEvento("i-1"), { wrapper });
    await expect(result.current.mutateAsync(null)).rejects.toThrow(/SIN RESPUESTA/);
  });
});

describe("useDictamenConfirm", () => {
  it("confirma la cabeza por su id", async () => {
    sdk.confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost.mockResolvedValue({
      data: { dictamen_id: "d-2" },
      response: { status: 201 },
    });
    const { result } = renderHook(() => useDictamenConfirm("i-1"), { wrapper });
    await result.current.mutateAsync("d-1");
    expect(
      sdk.confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost,
    ).toHaveBeenCalledWith({ path: { incident_id: "i-1", dictamen_id: "d-1" } });
  });

  it("un 409 rechaza con el detalle del servidor detrás", async () => {
    sdk.confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost.mockResolvedValue({
      error: { detail: "el dictamen vigente ya está firmado" },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useDictamenConfirm("i-1"), { wrapper });
    await expect(result.current.mutateAsync("d-1")).rejects.toThrow(
      confirmErrorMessage(409, "el dictamen vigente ya está firmado"),
    );
  });
});

describe("useInformeAutomatico", () => {
  it("un 404 es «sin informe» (null), no un error", async () => {
    sdk.getPostEventReportIncidentsIncidentIdPostEventReportGet.mockResolvedValue({
      error: { detail: "sin_informe" },
      response: { status: 404 },
    });
    const { result } = renderHook(() => useInformeAutomatico("i-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.informe).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("un 500 es un error, y NO se confunde con «sin informe»", async () => {
    sdk.getPostEventReportIncidentsIncidentIdPostEventReportGet.mockResolvedValue({
      error: { detail: "boom" },
      response: { status: 500 },
    });
    const { result } = renderHook(() => useInformeAutomatico("i-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.informe).toBeUndefined();
    expect(result.current.error).toMatch(/500/);
  });

  it("devuelve el estado del servidor tal cual", async () => {
    sdk.getPostEventReportIncidentsIncidentIdPostEventReportGet.mockResolvedValue({
      data: { state: "ok", preliminar: true },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useInformeAutomatico("i-1"), { wrapper });
    await waitFor(() => expect(result.current.informe).toEqual({ state: "ok", preliminar: true }));
  });
});

describe("useIncidente", () => {
  it("un 404 dice que no existe o no está en tu alcance", async () => {
    sdk.getIncidentIncidentsIncidentIdGet.mockResolvedValue({
      error: { detail: "x" },
      response: { status: 404 },
    });
    const { result } = renderHook(() => useIncidente("i-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toMatch(/NO EXISTE O NO ESTÁ EN TU ALCANCE/);
  });
});
