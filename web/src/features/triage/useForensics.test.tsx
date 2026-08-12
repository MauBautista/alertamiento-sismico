// [T-2.82.a] La EDAD del dato en la pantalla donde se firma un dictamen.
//
// `useForensics` alimenta los dos paneles que el inspector lee justo antes de
// firmar —el resumen post-evento y el marco normativo declarado— y no exponía
// `dataUpdatedAt`: ninguno de los dos podía decir que su dato estaba viejo. En
// esa pantalla, un dato congelado pintado como vivo es la regla de oro 7 rota
// en el peor sitio posible, porque encima alguien firma sobre él.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ incidentForensicsIncidentsIncidentIdForensicsGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { SIGNING_STALE_MS } from "./staleness";
import { useForensics } from "./useForensics";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.useRealTimers();
  sdk.incidentForensicsIncidentsIncidentIdForensicsGet.mockReset();
});

describe("useForensics · la edad del dato (T-2.82.a)", () => {
  it("expone `dataUpdatedAt` en cuanto el dato llega", async () => {
    sdk.incidentForensicsIncidentsIncidentIdForensicsGet.mockResolvedValue({
      data: { station_count: 3 },
      response: { status: 200 },
    });
    const antes = Date.now();
    const { result } = renderHook(() => useForensics("inc-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.dataUpdatedAt).toBeGreaterThanOrEqual(antes);
    // Recién llegado no es viejo: `staleSince` null = fresco.
    expect(result.current.staleSince).toBeNull();
  });

  it("sin incidente que pedir, la edad es 0 y NO se inventa frescura", async () => {
    // `enabled:false` deja la query sin resolver para siempre. Un
    // `dataUpdatedAt` de 0 con `staleSince` calculado a ciegas daría "viejo
    // desde 1970": ni siquiera hay dato del que hablar.
    const { result } = renderHook(() => useForensics(null), { wrapper });
    expect(result.current.dataUpdatedAt).toBe(0);
    expect(result.current.staleSince).toBeNull();
    expect(sdk.incidentForensicsIncidentsIncidentIdForensicsGet).not.toHaveBeenCalled();
  });

  it("pasado el umbral, `staleSince` marca LA HORA EN QUE SE SUPO, no `true`", async () => {
    // La hora es el contenido: "no lo sé desde las hh:mm" es verificable,
    // "viejo" no dice nada que el operador pueda usar.
    sdk.incidentForensicsIncidentsIncidentIdForensicsGet.mockResolvedValue({
      data: { station_count: 3 },
      response: { status: 200 },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useForensics("inc-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const llegada = result.current.dataUpdatedAt;
    expect(result.current.staleSince).toBeNull();

    // El reloj avanza más allá del umbral; el dato no se ha vuelto a pedir.
    await act(async () => {
      vi.advanceTimersByTime(SIGNING_STALE_MS + 60_000);
    });

    expect(result.current.staleSince).toBe(llegada);
  });

  it("el umbral es MAYOR que el `staleTime` de la consulta, y por una razón", () => {
    // Si el rótulo de "viejo" saltara antes de que la propia consulta se
    // considere refrescable, la pantalla acusaría de congelado a un dato que
    // está dentro de su ventana normal de refresco: un aviso que siempre está
    // encendido se deja de leer, y con él el día que sí importe.
    expect(SIGNING_STALE_MS).toBeGreaterThan(300_000);
  });
});
