import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { act } from "react";

import { anEvent, anIncident, aSite } from "./fixtures";
import { HISTORY_LIMIT, useTriage, type TriageFilters } from "./useTriage";

/** Filtros completos (T-1.58: from/to son parte del contrato del hook). */
function F(over: Partial<TriageFilters> = {}): TriageFilters {
  return { severity: null, q: "", from: null, to: null, ...over };
}

const mocks = vi.hoisted(() => ({
  listIncidentsIncidentsGet: vi.fn(),
  listEventsEventsGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);

const OK = (data: unknown) => ({ data, response: { status: 200 } });
const FAIL = (status: number) => ({ data: undefined, response: { status } });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const RULE_SET = {
  rule_set_id: "rs-1",
  tenant_id: "t-1",
  scope_type: "tenant",
  scope_id: "t-1",
  version: 3,
  is_active: true,
  config: { quorum: { min_nodes: 3 } },
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listIncidentsIncidentsGet.mockResolvedValue(
    OK({ items: [anIncident()], next_cursor: null }),
  );
  mocks.listEventsEventsGet.mockResolvedValue(OK({ items: [anEvent()], next_cursor: null }));
  mocks.listSitesSitesGet.mockResolvedValue(OK([aSite()]));
  mocks.listRuleSetsRuleSetsGet.mockResolvedValue(OK({ items: [RULE_SET] }));
});

describe("useTriage", () => {
  it("compone incidentes + eventos + sitios en filas del historial", async () => {
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.rows[0].siteName).toBe("Planta Cholula");
    expect(result.current.rows[0].event?.magnitude).toBe(6.8);
  });

  it("pasa severity y q al servidor (no filtra en cliente)", async () => {
    renderHook(() => useTriage(F({ severity: "critical", q: " EVT-2026 " })), { wrapper });
    await waitFor(() =>
      expect(mocks.listIncidentsIncidentsGet).toHaveBeenCalledWith({
        query: {
          severity: "critical",
          q: "EVT-2026",
          from: null,
          to: null,
          cursor: null,
          limit: HISTORY_LIMIT,
        },
      }),
    );
  });

  it("una búsqueda vacía manda q=null, no cadena vacía", async () => {
    renderHook(() => useTriage(F({ q: "   " })), { wrapper });
    await waitFor(() =>
      expect(mocks.listIncidentsIncidentsGet).toHaveBeenCalledWith({
        query: {
          severity: null,
          q: null,
          from: null,
          to: null,
          cursor: null,
          limit: HISTORY_LIMIT,
        },
      }),
    );
  });

  it("min_nodes sale del rule_set activo de tenant cuando no hay uno de sitio", async () => {
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.minNodesFor("s-1")).toBe(3));
  });

  it("el rule_set de SITIO gana al de tenant (igual que el motor)", async () => {
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue(
      OK({
        items: [
          RULE_SET, // tenant, min_nodes 3
          {
            ...RULE_SET,
            rule_set_id: "rs-site",
            scope_type: "site",
            scope_id: "s-1",
            version: 1,
            config: { quorum: { min_nodes: 2 } },
          },
        ],
      }),
    );
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.minNodesFor("s-1")).toBe(2));
    // …pero sólo para SU sitio: otro sitio sigue con el de tenant.
    expect(result.current.minNodesFor("s-9")).toBe(3);
  });

  it("a igualdad de scope gana la versión más alta", async () => {
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue(
      OK({
        items: [
          { ...RULE_SET, version: 1, config: { quorum: { min_nodes: 5 } } },
          { ...RULE_SET, rule_set_id: "rs-2", version: 9, config: { quorum: { min_nodes: 4 } } },
        ],
      }),
    );
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.minNodesFor("s-1")).toBe(4));
  });

  it("un rule_set INACTIVO no cuenta", async () => {
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue(
      OK({ items: [{ ...RULE_SET, is_active: false }] }),
    );
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.minNodesFor("s-1")).toBeNull();
  });

  it("sin rule_set activo min_nodes es null (no se asume 3)", async () => {
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue(OK({ items: [] }));
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.minNodesFor("s-1")).toBeNull();
  });

  it("si /events falla, el historial sigue vivo sin contexto sísmico", async () => {
    mocks.listEventsEventsGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.error).toBeNull();
    expect(result.current.rows[0].event).toBeNull();
  });

  it("si /sites falla, el historial degrada a id corto de sitio", async () => {
    mocks.listSitesSitesGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.rows[0].siteName).toMatch(/^SITIO /);
    expect(result.current.error).toBeNull();
  });

  it("si /incidents falla, ESO sí es el estado error de la página", async () => {
    mocks.listIncidentsIncidentsGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.error).toMatch(/incidents.*500/));
    expect(result.current.rows).toEqual([]);
  });
});

describe("useTriage · paginación keyset + fechas (T-1.58)", () => {
  it("loadMore pide la página siguiente con el cursor y ANEXA sin duplicar", async () => {
    const second = anIncident({
      incident_id: "99999999-9999-9999-9999-999999999999",
      opened_at: "2026-07-08T09:00:00Z",
    });
    mocks.listIncidentsIncidentsGet
      .mockResolvedValueOnce(OK({ items: [anIncident()], next_cursor: "cur-1" }))
      .mockResolvedValueOnce(OK({ items: [second], next_cursor: null }));

    const { result } = renderHook(() => useTriage(F()), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(result.current.hasMore).toBe(false);
    const secondCall = mocks.listIncidentsIncidentsGet.mock.calls[1][0];
    expect(secondCall.query.cursor).toBe("cur-1");
    const ids = result.current.rows.map((r) => r.incident.incident_id);
    expect(new Set(ids).size).toBe(2);
  });

  it("los días del picker van al server como RFC3339 con `to` EXCLUSIVO (+1 día)", async () => {
    renderHook(() => useTriage(F({ from: "2026-07-01", to: "2026-07-10" })), { wrapper });
    await waitFor(() => expect(mocks.listIncidentsIncidentsGet).toHaveBeenCalled());
    const call = mocks.listIncidentsIncidentsGet.mock.calls[0][0];
    // Medianoche LOCAL del día elegido; `to` incluye el día completo (día+1).
    expect(call.query.from).toBe(new Date("2026-07-01T00:00:00").toISOString());
    expect(call.query.to).toBe(new Date("2026-07-11T00:00:00").toISOString());
  });
});
