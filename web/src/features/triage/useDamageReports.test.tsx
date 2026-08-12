// [T-2.82.a] La edad de los reportes de campo.
//
// `StructuralTriage` es el único panel de la pantalla de firma que ni siquiera
// DECLARABA la entrada `staleSince` — callarse que un dato puede envejecer es
// afirmar que no puede. Y son los reportes que los tácticos levantan DENTRO del
// edificio durante la emergencia: los más volátiles de la pantalla, y los
// únicos que siguen llegando mientras el inspector lee.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listDamageReportsIncidentsIncidentIdDamageReportsGet: vi.fn(),
  verifyEvidenceEvidenceEvidenceIdVerifyPost: vi.fn(),
}));
vi.mock("@takab/sdk", () => mocks);

import { SIGNING_STALE_MS } from "./staleness";
import { useDamageReports } from "./useDamageReports";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue({
    data: [],
    response: { status: 200 },
  });
});

afterEach(() => vi.useRealTimers());

describe("useDamageReports · la edad del dato (T-2.82.a)", () => {
  it("recién llegado no es viejo", async () => {
    const { result } = renderHook(() => useDamageReports("i-1"), { wrapper });
    await waitFor(() => expect(result.current.reports).toBeDefined());
    expect(result.current.staleSince).toBeNull();
  });

  it("pasado el umbral marca LA HORA EN QUE SE SUPO, no `true`", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useDamageReports("i-1"), { wrapper });
    await waitFor(() => expect(result.current.reports).toBeDefined());
    expect(result.current.staleSince).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(SIGNING_STALE_MS + 60_000);
    });

    // Una lista de reportes de hace un cuarto de hora, presentada como la
    // situación del edificio AHORA, es la regla de oro 7 rota donde más duele:
    // «sin reportes de daños» puede significar que nadie ha podido enviarlos.
    expect(result.current.staleSince).toBeGreaterThan(0);
  });

  it("mientras la consulta está en vuelo NO hay edad que declarar", () => {
    const { result } = renderHook(() => useDamageReports("i-1"), { wrapper });
    expect(result.current.loading).toBe(true);
    expect(result.current.staleSince).toBeNull();
  });
});
