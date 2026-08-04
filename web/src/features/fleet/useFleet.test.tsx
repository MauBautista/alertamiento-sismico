import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GatewayOut, RuleSetOut } from "@takab/sdk";

import { resetSessionStoreForTests } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { seedAuthenticated } from "../../test-utils/renderRoutes";
import { buildCabinets, useFleet } from "./useFleet";

const mocks = vi.hoisted(() => ({
  listGatewaysFleetGatewaysGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);

const GW_OK: GatewayOut = {
  gateway_id: "g-1",
  site_id: "s-1",
  // [T-2.35] El nombre viaja con la fila: la UI no vuelve a cruzar contra /sites.
  site_name: "Planta Cholula",
  site_code: "CHL-A",
  site_status: "active",
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
  site_name: "Torre Sur",
  site_code: "TS-B",
  serial: "TKB-0002",
  derived_state: "SIN ENLACE",
  last_heartbeat_ts: null,
  power_status: null,
  battery_pct: null,
  mqtt_rtt_ms: null,
  seedlink_lag_s: null,
};

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
  ruleSets = [ruleSet({})] as RuleSetOut[] | number,
  /** Rol en sesión: /fleet/gateways solo se pide si su matriz lo permite. */
  role = "takab_superadmin" as keyof typeof ME_FIXTURES,
  includeRetired = false,
} = {}) {
  seedAuthenticated(ME_FIXTURES[role]);
  mocks.listGatewaysFleetGatewaysGet.mockResolvedValue(
    typeof gateways === "number" ? fail(gateways) : ok(gateways),
  );
  mocks.listRuleSetsRuleSetsGet.mockResolvedValue(
    typeof ruleSets === "number" ? fail(ruleSets) : ok({ items: ruleSets }),
  );
  return renderHook(() => useFleet({ includeRetired }), { wrapper: makeWrapper() });
}

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
});

async function settled(result: { current: ReturnType<typeof useFleet> }) {
  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });
}

describe("useFleet", () => {
  it("toma el nombre del sitio del servidor y respeta el orden del API", async () => {
    const { result } = arrange();
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[0].siteName).toBe("Planta Cholula");
    });
    expect(result.current.cabinets.map((c) => c.gateway.gateway_id)).toEqual(["g-1", "g-2"]);
    expect(result.current.cabinets[0].siteCode).toBe("CHL-A");
    // `listSitesSitesGet` ni siquiera está mockeada: si el hook volviera a pedir
    // /sites, este test reventaría con un TypeError. Ese es el guard.
  });

  // [T-2.35] El bug de las "estaciones fantasma": al cruzar contra /sites (que
  // oculta los retirados) un gabinete huérfano perdía su nombre y la UI lo
  // rebautizaba `SITIO <8 hex>`. Dos huérfanos se veían idénticos e indelebles.
  it("nunca fabrica un nombre a partir del site_id", async () => {
    const { result } = arrange();
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets).toHaveLength(2);
    });
    for (const cab of result.current.cabinets) {
      expect(cab.siteName).not.toMatch(/^SITIO /);
      expect(cab.siteName).not.toContain(cab.gateway.site_id.slice(0, 8));
    }
  });

  it("dos gabinetes del MISMO sitio se distinguen por serial", async () => {
    // `sites.name` no es único (db/schema.sql solo restringe (tenant_id, code)):
    // el rótulo puede repetirse legítimamente y la identidad la pone el serial.
    const twin: GatewayOut = { ...GW_OK, gateway_id: "g-3", serial: "TKB-0003" };
    const { result } = arrange({ gateways: [GW_OK, twin] });
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets).toHaveLength(2);
    });
    const [a, b] = result.current.cabinets;
    expect(a.siteName).toBe(b.siteName);
    expect(a.gateway.serial).not.toBe(b.gateway.serial);
  });

  it("includeRetired viaja al servidor como query param", async () => {
    const { result } = arrange({ includeRetired: true });
    await settled(result);
    expect(mocks.listGatewaysFleetGatewaysGet).toHaveBeenCalledWith({
      query: { include_retired: true },
    });
  });

  it("por defecto NO pide los retirados", async () => {
    const { result } = arrange();
    await settled(result);
    expect(mocks.listGatewaysFleetGatewaysGet).toHaveBeenCalledWith(undefined);
  });

  it("expone el estado del sitio padre para rotular al huérfano", async () => {
    const orphan: GatewayOut = { ...GW_OK, site_status: "retired" };
    const { result } = arrange({ gateways: [orphan], includeRetired: true });
    await settled(result);
    await waitFor(() => {
      expect(result.current.cabinets[0]?.siteStatus).toBe("retired");
    });
  });

  // El rol sin /fleet en su matriz (inspector, building_admin) SÍ entra a la
  // consola, y ahí useSiteRelays monta este hook: sin gate, cada carga de
  // /console le disparaba un 403 contra /fleet/gateways.
  it("rol sin /fleet: no pide el inventario y no se queda cargando", async () => {
    const { result } = arrange({ role: "inspector" });
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(mocks.listGatewaysFleetGatewaysGet).not.toHaveBeenCalled();
    expect(result.current.cabinets).toEqual([]);
    expect(result.current.error).toBeNull();
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

describe("buildCabinets · perfil de equipamiento [T-2.31]", () => {
  const EQUIP_ALL = {
    siren: true,
    strobe: true,
    gas_valve: true,
    elevator: true,
    door_retainer: true,
  };

  it("un canal no instalado se OCULTA aunque el rule_set declare su cableado", () => {
    const gw = { ...GW_OK, equipment: { ...EQUIP_ALL, gas_valve: false } };
    const [cab] = buildCabinets([gw], [ruleSet({})]);
    expect(cab.relays?.map((r) => r.key)).not.toContain("gas_valve");
    expect(cab.relays?.map((r) => r.key)).toContain("siren");
  });

  it("un canal instalado SIN cableado declarado aparece con wiring S/D", () => {
    const gw = { ...GW_OK, equipment: EQUIP_ALL };
    const [cab] = buildCabinets([gw], [ruleSet({})]);
    const strobe = cab.relays?.find((r) => r.key === "strobe");
    expect(strobe).toBeDefined();
    expect(strobe?.wiring).toBe("S/D");
    expect(strobe?.label).toBe("ESTROBO");
  });

  it("alias del rule_set (gas/doors) se filtran por su canal de equipment", () => {
    const gw = { ...GW_OK, equipment: { ...EQUIP_ALL, door_retainer: false } };
    const [cab] = buildCabinets(
      [gw],
      [ruleSet({ config: { relays: { siren: "NO", doors: "NC" } } })],
    );
    expect(cab.relays?.map((r) => r.key)).not.toContain("doors");
    expect(cab.relays?.map((r) => r.key)).toContain("siren");
  });

  it("gateway sin equipment (SDK viejo) conserva la conducta previa", () => {
    const [cab] = buildCabinets([GW_OK], [ruleSet({})]);
    expect(cab.relays?.map((r) => r.key)).toEqual(["siren", "gas_valve"]);
  });
});
