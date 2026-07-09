import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { GatewayOut, RuleSetOut, SiteOut } from "@takab/sdk";

import { useFleet } from "./useFleet";

const mocks = vi.hoisted(() => ({
  listGatewaysFleetGatewaysGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);

const GW_OK: GatewayOut = {
  gateway_id: "g-1",
  site_id: "s-1",
  serial: "TKB-0001",
  fw_version: "edge-1.4.0",
  iot_thing: "gw-dev-0001",
  status: "active",
  has_wr1: true,
  installed_at: null,
  row_version: "1",
  derived_state: "OPERATIVO",
  last_heartbeat_ts: "2026-07-08T10:41:00Z",
  power_status: "line",
  battery_pct: 100,
  cert_days_remaining: 200,
  mqtt_rtt_ms: 42.5,
  seedlink_lag_s: 0.4,
  ntp_offset_ms: 3.2,
};

const GW_OFFLINE: GatewayOut = {
  ...GW_OK,
  gateway_id: "g-2",
  site_id: "s-2",
  serial: "TKB-0002",
  derived_state: "SIN ENLACE",
  last_heartbeat_ts: null,
  power_status: null,
  battery_pct: null,
  mqtt_rtt_ms: null,
  seedlink_lag_s: null,
};

const SITES: SiteOut[] = [
  {
    site_id: "s-1",
    tenant_id: "t-1",
    code: "CHL-A",
    name: "Planta Cholula",
    criticality: "high",
    lat: 19.06,
    lon: -98.3,
    timezone: "America/Mexico_City",
    status: "active",
    row_version: "1",
    created_at: "2026-01-01T00:00:00Z",
  },
];

function ruleSet(over: Partial<RuleSetOut>): RuleSetOut {
  return {
    rule_set_id: "rs-1",
    tenant_id: "t-1",
    scope_type: "site",
    scope_id: "s-1",
    version: 3,
    is_active: true,
    config: { relays: { siren: "NO", gas_valve: "fail_close" } },
    created_by: null,
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function ok<T>(data: T) {
  return { data, response: new Response(null) };
}

function fail(status: number) {
  return { data: undefined, response: new Response(null, { status }) };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function arrange({
  gateways = [GW_OK, GW_OFFLINE] as GatewayOut[] | number,
  sites = SITES as SiteOut[] | number,
  ruleSets = [ruleSet({})] as RuleSetOut[] | number,
} = {}) {
  mocks.listGatewaysFleetGatewaysGet.mockResolvedValue(
    typeof gateways === "number" ? fail(gateways) : ok(gateways),
  );
  mocks.listSitesSitesGet.mockResolvedValue(typeof sites === "number" ? fail(sites) : ok(sites));
  mocks.listRuleSetsRuleSetsGet.mockResolvedValue(
    typeof ruleSets === "number" ? fail(ruleSets) : ok({ items: ruleSets }),
  );
  return renderHook(() => useFleet(), { wrapper: makeWrapper() });
}

async function settled(result: { current: ReturnType<typeof useFleet> }) {
  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });
}

describe("useFleet", () => {
  it("une gateways con el nombre del sitio y respeta el orden del API", async () => {
    const { result } = arrange();
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[0].siteName).toBe("Planta Cholula");
    });
    expect(result.current.cabinets.map((c) => c.gateway.gateway_id)).toEqual(["g-1", "g-2"]);
    expect(result.current.cabinets[0].siteCode).toBe("CHL-A");
  });

  it("si /sites falla usa un fallback identificable y NO tumba la página", async () => {
    const { result } = arrange({ sites: 500 });
    await settled(result);
    expect(result.current.error).toBeNull();
    expect(result.current.cabinets[0].siteName).toBe("SITIO s-1");
  });

  it("deriva relays de la config site-scope activa: ARMADO con enlace vivo", async () => {
    const { result } = arrange();
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[0].relays).not.toBeNull();
    });
    expect(result.current.cabinets[0].relays).toEqual([
      { key: "siren", label: "SIRENA", wiring: "NO", armed: true },
      { key: "gas_valve", label: "GAS", wiring: "fail_close", armed: true },
    ]);
  });

  it("SIN ENLACE ⇒ armed=null (S/D): jamás se inventa estado de actuador", async () => {
    const { result } = arrange({ ruleSets: [ruleSet({ scope_id: "s-2" })] });
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[1].relays).not.toBeNull();
    });
    for (const relay of result.current.cabinets[1].relays ?? []) {
      expect(relay.armed).toBeNull();
    }
  });

  it("sin config site-scope cae al scope tenant activo", async () => {
    const { result } = arrange({
      ruleSets: [
        ruleSet({ rule_set_id: "rs-t", scope_type: "tenant", scope_id: "t-1" }),
        ruleSet({ rule_set_id: "rs-off", is_active: false, config: { relays: { doors: "NC" } } }),
      ],
    });
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[0].relays).not.toBeNull();
    });
    expect(result.current.cabinets[0].relays?.map((r) => r.key)).toEqual(["siren", "gas_valve"]);
  });

  it("si /rule-sets falla los relays quedan null (la tarjeta degrada, no rompe)", async () => {
    const { result } = arrange({ ruleSets: 403 });
    await settled(result);
    expect(result.current.error).toBeNull();
    expect(result.current.cabinets[0].relays).toBeNull();
  });

  it("error SOLO cuando /fleet/gateways falla sin datos previos", async () => {
    const { result } = arrange({ gateways: 503 });
    await settled(result);
    expect(result.current.error).toMatch(/503/);
    expect(result.current.cabinets).toEqual([]);
  });

  it("flota vacía ⇒ cabinets [] sin error", async () => {
    const { result } = arrange({ gateways: [] });
    await settled(result);
    expect(result.current.error).toBeNull();
    expect(result.current.cabinets).toEqual([]);
  });
});
