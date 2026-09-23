// [T-6.17] El frame `drill` del canal live invalida el banner de simulacro sin
// esperar al sondeo de 10 s. Sin socket, el hook sigue funcionando por sondeo.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TOPIC_INCIDENTS } from "@takab/sdk";

import { FakeLiveSocket } from "../../test-utils/liveSocket";
import { LiveSocketContext } from "./socket";
import { useActiveDrill } from "./useActiveDrill";

const sdk = vi.hoisted(() => ({
  activeDrillDrillsActiveGet: vi.fn(),
  listDrillsDrillsGet: vi.fn(),
  startDrillDrillsPost: vi.fn(),
}));

vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  activeDrillDrillsActiveGet: sdk.activeDrillDrillsActiveGet,
  listDrillsDrillsGet: sdk.listDrillsDrillsGet,
  startDrillDrillsPost: sdk.startDrillDrillsPost,
}));

function wrapper(socket: FakeLiveSocket | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <LiveSocketContext.Provider value={socket}>{children}</LiveSocketContext.Provider>
      </QueryClientProvider>
    );
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("useActiveDrill · push por WS", () => {
  it("un frame `drill` re-consulta el simulacro activo sin esperar al sondeo", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    const socket = new FakeLiveSocket();
    renderHook(() => useActiveDrill(), { wrapper: wrapper(socket) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));

    socket.emit(TOPIC_INCIDENTS, {
      type: "drill",
      tenant_id: "t-1",
      drill_id: "d-1",
    } as never);
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(2));
  });

  it("otros frames del mismo topic no disparan la re-consulta", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    const socket = new FakeLiveSocket();
    renderHook(() => useActiveDrill(), { wrapper: wrapper(socket) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));

    socket.emit(TOPIC_INCIDENTS, { type: "checkin", tenant_id: "t-1" } as never);
    await new Promise((r) => setTimeout(r, 20));
    expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1);
  });

  it("sin socket sigue consultando por REST (el sondeo es el respaldo)", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));
  });
});

// [A-094 · T-8.07] Quien lanza tiene que poder ESPERAR al servidor: el modal se
// cerraba en el acto y el botón decía «EJECUTADO» aunque el POST fallara.
// `start` devuelve si arrancó, y NO rechaza nunca: el banner del shell lo sigue
// llamando sin esperar y un rechazo suelto sería un error no atendido.
describe("useActiveDrill · start dice si arrancó", () => {
  function base(): void {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
  }

  it("con 201 resuelve true", async () => {
    base();
    sdk.startDrillDrillsPost.mockResolvedValue({
      data: { drill_id: "d-1" },
      response: { status: 201 },
    });
    const { result } = renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await expect(result.current.start({ siteIds: ["s-1"] })).resolves.toBe(true);
  });

  it("con un 400 resuelve false (no rechaza) y el error queda para pintarlo", async () => {
    base();
    sdk.startDrillDrillsPost.mockResolvedValue({ data: undefined, response: { status: 400 } });
    const { result } = renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await expect(result.current.start({})).resolves.toBe(false);
    await waitFor(() => expect(result.current.error).toContain("400"));
  });
});

// [T-8.07] El motivo del servidor llega al operador. hey-api no lanza con un
// 4xx: devuelve `{ error, response }`, y el `detail` de FastAPI se tiraba. El
// modal pintaba «el simulacro no arrancó (HTTP 409)» sin decir por qué, justo
// cuando el porqué es lo único que le permite arreglarlo.
describe("useActiveDrill · el error dice el motivo del servidor", () => {
  function base(): void {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
  }

  it("un 409 con `detail` lo lleva en el error, con su código", async () => {
    base();
    sdk.startDrillDrillsPost.mockResolvedValue({
      data: undefined,
      error: {
        detail: "ninguno de los 2 sitio(s) de la lista tiene hoy gateway comandable",
      },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await expect(result.current.start({ fromScheduled: "d-9" })).resolves.toBe(false);
    await waitFor(() =>
      expect(result.current.error).toContain(
        "ninguno de los 2 sitio(s) de la lista tiene hoy gateway comandable",
      ),
    );
    expect(result.current.error).toContain("409");
  });

  it("un `detail` que no es texto (el 422 de validación) no se imprime como [object Object]", async () => {
    base();
    sdk.startDrillDrillsPost.mockResolvedValue({
      data: undefined,
      error: { detail: [{ loc: ["body", "duration_s"], msg: "fuera de rango" }] },
      response: { status: 422 },
    });
    const { result } = renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await expect(result.current.start({})).resolves.toBe(false);
    await waitFor(() => expect(result.current.error).toContain("422"));
    expect(result.current.error).not.toContain("[object Object]");
  });
});
