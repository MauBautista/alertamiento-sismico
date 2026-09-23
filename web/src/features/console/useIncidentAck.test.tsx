// [A-011 · T-8.07] El acuse rechaza con lo que dijo el servidor, y con la red
// caída también: «no consta» nunca se confunde con «acusado».

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ ackIncidentIncidentsIncidentIdAckPost: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { ackErrorMessage, useIncidentAck } from "./useIncidentAck";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ackErrorMessage", () => {
  it("el 409 dice que alguien llegó antes, no que el sistema falló", () => {
    expect(ackErrorMessage(409, null)).toBe(
      "NO SE ACUSÓ · EL INCIDENTE YA NO ESTÁ ABIERTO: OTRO OPERADOR LO ACUSÓ O PASÓ A REVISIÓN (HTTP 409)",
    );
  });

  it("el detalle del servidor va detrás, tal cual", () => {
    expect(ackErrorMessage(500, "boom")).toBe(
      "NO SE ACUSÓ · EL SERVIDOR NO REGISTRÓ EL ACUSE (HTTP 500) · boom",
    );
  });

  it("sin respuesta no inventa un código", () => {
    expect(ackErrorMessage(null, null)).toBe("NO SE ACUSÓ · SIN RESPUESTA DEL SERVIDOR");
  });
});

describe("useIncidentAck", () => {
  it("un 2xx resuelve con el cuerpo", async () => {
    sdk.ackIncidentIncidentsIncidentIdAckPost.mockResolvedValue({
      data: { incident_id: "i-1", state: "acked" },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useIncidentAck(), { wrapper });
    await expect(result.current.mutateAsync("i-1")).resolves.toEqual({
      incident_id: "i-1",
      state: "acked",
    });
  });

  it("un 403 rechaza aunque el cliente no lance", async () => {
    sdk.ackIncidentIncidentsIncidentIdAckPost.mockResolvedValue({
      data: undefined,
      error: { detail: "Forbidden" },
      response: { status: 403 },
    });
    const { result } = renderHook(() => useIncidentAck(), { wrapper });
    await expect(result.current.mutateAsync("i-1")).rejects.toThrow(/HTTP 403.*Forbidden/);
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("con la red caída rechaza con SIN RESPUESTA, no se queda colgado", async () => {
    sdk.ackIncidentIncidentsIncidentIdAckPost.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useIncidentAck(), { wrapper });
    await expect(result.current.mutateAsync("i-1")).rejects.toThrow("SIN RESPUESTA DEL SERVIDOR");
  });
});
