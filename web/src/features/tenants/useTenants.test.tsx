import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRuleSetPublish } from "./useRuleSetPublish";
import { useTenantGateways, useTenantSync, useTenants } from "./useTenants";

const mocks = vi.hoisted(() => ({
  listTenantsTenantsGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
  listGatewaysFleetGatewaysGet: vi.fn(),
  listGatewayConfigStatesFleetConfigStateGet: vi.fn(),
  putRuleSetRuleSetsPut: vi.fn(),
  publishRuleSetRuleSetsRuleSetIdPublishPost: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);

const OK = (data: unknown) => ({ data, response: { status: 200 } });
const FAIL = (status: number) => ({ data: undefined, response: { status } });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const TENANT = { tenant_id: "t-1", code: "A", name: "A", isolation_mode: "logical" };
const SITES = [
  { site_id: "s-1", tenant_id: "t-1" },
  { site_id: "s-2", tenant_id: "t-2" },
];
const GATEWAYS = [
  { gateway_id: "g-1", site_id: "s-1" },
  { gateway_id: "g-2", site_id: "s-2" },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listTenantsTenantsGet.mockResolvedValue(OK([TENANT]));
  mocks.listRuleSetsRuleSetsGet.mockResolvedValue(OK({ items: [] }));
  mocks.listSitesSitesGet.mockResolvedValue(OK(SITES));
  mocks.listGatewaysFleetGatewaysGet.mockResolvedValue(OK(GATEWAYS));
  mocks.listGatewayConfigStatesFleetConfigStateGet.mockResolvedValue(
    OK([
      { gateway_id: "g-1", in_sync: true, has_edge_config: true, is_syncable: true, version: 2 },
      { gateway_id: "g-2", in_sync: false, has_edge_config: true, is_syncable: true, version: 1 },
    ]),
  );
});

describe("useTenants", () => {
  it("no filtra tenants en el cliente: RLS decide qué filas llegan", async () => {
    const { result } = renderHook(() => useTenants(), { wrapper });
    await waitFor(() => expect(result.current.tenants).toHaveLength(1));
    expect(mocks.listTenantsTenantsGet).toHaveBeenCalledTimes(1);
  });

  it("si /sites falla, el catálogo sigue vivo (se pierde la cuenta, no la página)", async () => {
    mocks.listSitesSitesGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTenants(), { wrapper });
    await waitFor(() => expect(result.current.tenants).toHaveLength(1));
    expect(result.current.error).toBeNull();
    expect(result.current.sites).toBeUndefined();
  });

  it("si /rule-sets falla se reporta aparte: sin él no hay umbrales", async () => {
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTenants(), { wrapper });
    await waitFor(() => expect(result.current.ruleSetsError).toMatch(/rule-sets.*500/));
    expect(result.current.error).toBeNull();
  });

  it("si /tenants falla, ESO sí es el error de la página", async () => {
    mocks.listTenantsTenantsGet.mockResolvedValue(FAIL(403));
    const { result } = renderHook(() => useTenants(), { wrapper });
    await waitFor(() => expect(result.current.error).toMatch(/tenants.*403/));
  });
});

describe("useTenantGateways", () => {
  it("sólo los gateways de los sitios del tenant seleccionado", async () => {
    const { result } = renderHook(() => useTenantGateways("t-1"), { wrapper });
    await waitFor(() => expect(result.current.gatewayIds).toEqual(["g-1"]));
  });

  it("sin tenant seleccionado no hay gateways", async () => {
    const { result } = renderHook(() => useTenantGateways(null), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.gatewayIds).toEqual([]);
  });
});

describe("useTenantSync · no se afirma el sync sin evidencia completa", () => {
  it("sin gateways ⇒ lista vacía, no undefined", async () => {
    const { result } = renderHook(() => useTenantSync([]), { wrapper });
    expect(result.current.states).toEqual([]);
    expect(result.current.loading).toBe(false);
    // Y ni siquiera se pide el lote: no hay nada que preguntar.
    expect(mocks.listGatewayConfigStatesFleetConfigStateGet).not.toHaveBeenCalled();
  });

  it("[T-2.51] UNA sola consulta en lote, no una por gabinete", async () => {
    // El defecto que cierra: 500 gabinetes × 1 query cada 10 s = ~50 req/s desde
    // un navegador. `GET /fleet/config-state` devuelve el mismo SQL sin el WHERE.
    const { result } = renderHook(() => useTenantSync(["g-1", "g-2"]), { wrapper });
    await waitFor(() => expect(result.current.states).toHaveLength(2));
    expect(mocks.listGatewayConfigStatesFleetConfigStateGet).toHaveBeenCalledTimes(1);
  });

  it("del lote sólo se toman los gabinetes pedidos, en su orden", async () => {
    mocks.listGatewayConfigStatesFleetConfigStateGet.mockResolvedValue(
      OK([
        { gateway_id: "g-9", in_sync: true, has_edge_config: true, is_syncable: true, version: 7 },
        { gateway_id: "g-1", in_sync: true, has_edge_config: true, is_syncable: true, version: 2 },
      ]),
    );
    const { result } = renderHook(() => useTenantSync(["g-1"]), { wrapper });
    await waitFor(() => expect(result.current.states).toHaveLength(1));
    expect(result.current.states?.[0].gateway_id).toBe("g-1");
  });

  it("si un gabinete FALTA en el lote, states queda undefined (nada se afirma)", async () => {
    // La semántica honesta del N+1 se conserva: ausente ≠ sincronizado.
    mocks.listGatewayConfigStatesFleetConfigStateGet.mockResolvedValue(
      OK([
        { gateway_id: "g-1", in_sync: true, has_edge_config: true, is_syncable: true, version: 2 },
      ]),
    );
    const { result } = renderHook(() => useTenantSync(["g-1", "g-2"]), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.states).toBeUndefined();
  });

  it("si el lote falla, states queda undefined y el error se reporta", async () => {
    mocks.listGatewayConfigStatesFleetConfigStateGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useTenantSync(["g-1"]), { wrapper });
    await waitFor(() => expect(result.current.error).toMatch(/500/));
    expect(result.current.states).toBeUndefined();
  });
});

describe("useRuleSetPublish · PUT crea versión, publish registra intención", () => {
  it("encadena PUT y publish, en ese orden, con el scope de tenant", async () => {
    mocks.putRuleSetRuleSetsPut.mockResolvedValue(OK({ rule_set_id: "rs-9", version: 5 }));
    mocks.publishRuleSetRuleSetsRuleSetIdPublishPost.mockResolvedValue(
      OK({ rule_set_id: "rs-9", version: 5, status: "pending_sync" }),
    );
    const { result } = renderHook(() => useRuleSetPublish(), { wrapper });

    act(() => result.current.apply({ tenantId: "t-1", config: { edge: {} }, baseVersion: 4 }));

    await waitFor(() => expect(result.current.publishedVersion).toBe(5));
    expect(mocks.putRuleSetRuleSetsPut).toHaveBeenCalledWith({
      body: { scope_type: "tenant", scope_id: "t-1", config: { edge: {} }, base_version: 4 },
    });
    expect(mocks.publishRuleSetRuleSetsRuleSetIdPublishPost).toHaveBeenCalledWith({
      path: { rule_set_id: "rs-9" },
    });
  });

  it("un 403 en el PUT no publica nada", async () => {
    mocks.putRuleSetRuleSetsPut.mockResolvedValue(FAIL(403));
    const { result } = renderHook(() => useRuleSetPublish(), { wrapper });
    act(() => result.current.apply({ tenantId: "t-1", config: {}, baseVersion: null }));
    await waitFor(() => expect(result.current.error).toMatch(/PUT \/rule-sets.*403/));
    expect(mocks.publishRuleSetRuleSetsRuleSetIdPublishPost).not.toHaveBeenCalled();
  });

  it("un fallo en publish se reporta (la versión ya existe pero no se anunció)", async () => {
    mocks.putRuleSetRuleSetsPut.mockResolvedValue(OK({ rule_set_id: "rs-9", version: 5 }));
    mocks.publishRuleSetRuleSetsRuleSetIdPublishPost.mockResolvedValue(FAIL(404));
    const { result } = renderHook(() => useRuleSetPublish(), { wrapper });
    act(() => result.current.apply({ tenantId: "t-1", config: {}, baseVersion: null }));
    await waitFor(() => expect(result.current.error).toMatch(/publish.*404/));
    expect(result.current.publishedVersion).toBeNull();
  });
});
