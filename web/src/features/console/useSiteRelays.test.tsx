// useSiteRelays (T-1.50): resuelve los relés del gabinete del sitio REUSANDO
// las queries de useFleet (caché compartida por queryKey).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  listGatewaysFleetGatewaysGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { useSiteRelays } from "./useSiteRelays";

const GW = {
  gateway_id: "g-1",
  tenant_id: "t-1",
  site_id: "s-1",
  serial: "gw-dev-0001",
  iot_thing: "gw-dev-0001",
  status: "provisioned",
  derived_state: "OPERATIVO",
};

const RULE_SET = {
  rule_set_id: "r-1",
  tenant_id: "t-1",
  scope_type: "tenant",
  scope_id: "t-1",
  version: 1,
  is_active: true,
  config: { relays: { siren: "NO", gas: "fail_close" } },
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useSiteRelays", () => {
  it("con gateway y rule_set activo devuelve los relés del sitio", async () => {
    sdk.listGatewaysFleetGatewaysGet.mockResolvedValue({ data: [GW], response: { status: 200 } });
    sdk.listSitesSitesGet.mockResolvedValue({ data: [], response: { status: 200 } });
    sdk.listRuleSetsRuleSetsGet.mockResolvedValue({
      data: { items: [RULE_SET] },
      response: { status: 200 },
    });

    const { result } = renderHook(() => useSiteRelays("s-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.relays).not.toBeNull());
    expect(result.current.relays?.map((r) => r.label)).toEqual(["SIRENA", "GAS"]);
  });

  it("sitio sin gabinete ⇒ null (la card muestra el estado honesto)", async () => {
    sdk.listGatewaysFleetGatewaysGet.mockResolvedValue({ data: [GW], response: { status: 200 } });
    sdk.listSitesSitesGet.mockResolvedValue({ data: [], response: { status: 200 } });
    sdk.listRuleSetsRuleSetsGet.mockResolvedValue({
      data: { items: [RULE_SET] },
      response: { status: 200 },
    });

    const { result } = renderHook(() => useSiteRelays("s-OTRO"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.relays).toBeNull();
  });

  it("siteId null ⇒ null sin reventar", () => {
    sdk.listGatewaysFleetGatewaysGet.mockResolvedValue({ data: [], response: { status: 200 } });
    sdk.listSitesSitesGet.mockResolvedValue({ data: [], response: { status: 200 } });
    sdk.listRuleSetsRuleSetsGet.mockResolvedValue({
      data: { items: [] },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useSiteRelays(null), { wrapper });
    expect(result.current.relays).toBeNull();
  });
});
