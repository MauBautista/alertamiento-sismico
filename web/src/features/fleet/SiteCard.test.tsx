import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GatewayOut } from "@takab/sdk";

// T-1.59: SiteCard monta useSelfTest (react-query + SDK) — se mockean SOLO las
// dos funciones de comandos; el resto del módulo no se usa en esta card.
const sdk = vi.hoisted(() => ({
  issueCommandSitesSiteIdCommandsPost: vi.fn(),
  listCommandsSitesSiteIdCommandsGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import SiteCard from "./SiteCard";
import type { FleetCabinet } from "./useFleet";

/** Render con QueryClient limpio (useSelfTest lo exige); sesión opcional aparte. */
function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
  sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
    data: { items: [] },
    response: { status: 200 },
  });
});

const GW: GatewayOut = {
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

function cabinet(over: Partial<FleetCabinet> = {}, gw: Partial<GatewayOut> = {}): FleetCabinet {
  return {
    gateway: { ...GW, ...gw },
    siteName: "Planta Cholula",
    siteCode: "CHL-A",
    relays: [
      { key: "siren", label: "SIRENA", wiring: "NO", armed: true },
      { key: "gas_valve", label: "GAS", wiring: "fail_close", armed: true },
    ],
    ...over,
  };
}

describe("SiteCard", () => {
  it("pinta el estado server-derived tal cual (OPERATIVO ⇒ pill ok)", () => {
    const { container } = render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("OPERATIVO")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--ok")).not.toBeNull();
    expect(container.querySelector(".fleet-card--ok")).not.toBeNull();
  });

  it("muestra lags crudos: MQTT ↔ ms y SeedLink lag s", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("↔ 42.5 ms")).toBeInTheDocument();
    expect(screen.getByText("lag 0.40 s")).toBeInTheDocument();
  });

  it("SIN ENLACE ⇒ pill crit, pills de enlace en crit con — sin enlace — y relays S/D", () => {
    const { container } = render(
      <SiteCard
        cabinet={cabinet(
          {
            relays: [{ key: "siren", label: "SIRENA", wiring: "NO", armed: null }],
          },
          {
            derived_state: "SIN ENLACE",
            mqtt_rtt_ms: null,
            seedlink_lag_s: null,
            power_status: null,
            battery_pct: null,
            last_heartbeat_ts: null,
          },
        )}
      />,
    );
    expect(screen.getByText("SIN ENLACE")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--crit")).not.toBeNull();
    expect(screen.getAllByText("— sin enlace —")).toHaveLength(2);
    expect(screen.getByText("S/D")).toBeInTheDocument();
    expect(screen.queryByText("ARMADO")).toBeNull();
    expect(screen.getByText(/HB —/)).toBeInTheDocument();
  });

  it("DEGRADADO ⇒ pill warn; el detalle de la métrica NO se recalcula en UI", () => {
    const { container } = render(
      <SiteCard
        cabinet={cabinet(
          {},
          { derived_state: "DEGRADADO", power_status: "battery", battery_pct: 72 },
        )}
      />,
    );
    expect(screen.getByText("DEGRADADO")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--warn")).not.toBeNull();
    expect(screen.getByText("EN BATERÍA")).toBeInTheDocument();
  });

  it("DEGRADADO con degrade_reasons ⇒ pills server-derived con QUÉ degrada (T-1.40)", () => {
    render(
      <SiteCard
        cabinet={cabinet(
          {},
          {
            derived_state: "DEGRADADO",
            ntp_offset_ms: 180,
            cert_days_remaining: 12,
            degrade_reasons: ["CERT 12d", "NTP +180ms"],
          },
        )}
      />,
    );
    expect(screen.getByText("CERT 12d")).toBeInTheDocument();
    expect(screen.getByText("NTP +180ms")).toBeInTheDocument();
  });

  it("OPERATIVO jamás pinta razones aunque el campo venga (defensa en la UI)", () => {
    const { container } = render(
      <SiteCard cabinet={cabinet({}, { degrade_reasons: ["CERT 12d"] })} />,
    );
    expect(container.querySelector(".fleet-card__reasons")).toBeNull();
  });

  it("un derived_state desconocido JAMÁS pinta ok", () => {
    const { container } = render(<SiteCard cabinet={cabinet({}, { derived_state: "???" })} />);
    expect(container.querySelector(".soc-pill--ok")).toBeNull();
    expect(container.querySelector(".soc-pill--warn")).not.toBeNull();
  });

  it("relays de la config: etiqueta, numeración y cableado en title + caption honesto", () => {
    const { container } = render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("SIRENA")).toBeInTheDocument();
    expect(screen.getByText("GAS")).toBeInTheDocument();
    expect(screen.getAllByText("ARMADO")).toHaveLength(2);
    expect(screen.getByText("R1")).toBeInTheDocument();
    expect(container.querySelector('[title="cableado NO"]')).not.toBeNull();
    expect(screen.getByText("CONFIG ACTIVA · ESTADO DERIVADO DEL ENLACE")).toBeInTheDocument();
  });

  it("sin config visible degrada al badge agregado (enlace vivo)", () => {
    render(<SiteCard cabinet={cabinet({ relays: null })} />);
    expect(screen.getByText("ARMADOS · CONFIG DE RELAYS NO VISIBLE")).toBeInTheDocument();
  });

  it("autodiagnóstico: sin la acción self_test queda deshabilitado con la razón", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    render(<SiteCard cabinet={cabinet()} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("self_test"));
  });

  it("autodiagnóstico (T-1.59): tenant_admin lo dispara y llega el POST system/self_test", async () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: { command_id: "c-st-1", status: "pending" },
      response: { status: 201 },
    });
    render(<SiteCard cabinet={cabinet()} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    await waitFor(() =>
      expect(sdk.issueCommandSitesSiteIdCommandsPost).toHaveBeenCalledWith({
        path: { site_id: "s-1" },
        body: { channel: "system", action: "self_test" },
      }),
    );
  });

  it("autodiagnóstico: SIN ENLACE queda deshabilitado (el comando expiraría por TTL)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    render(<SiteCard cabinet={cabinet({}, { derived_state: "SIN ENLACE" })} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("TTL"));
  });

  it("autodiagnóstico: el ack del edge pinta chips por relé (jamás inventados)", async () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: { command_id: "c-st-2", status: "pending" },
      response: { status: 201 },
    });
    sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
      data: {
        items: [
          {
            command_id: "c-st-2",
            status: "acked",
            ack: {
              detail: "self-test completado",
              results: {
                relays: {
                  gas_valve: { pulsed: true, readback_ok: true },
                  elevator: { pulsed: true, readback_ok: false },
                  siren: { pulsed: false, readback_ok: true },
                },
              },
            },
            error: null,
          },
        ],
      },
      response: { status: 200 },
    });
    render(<SiteCard cabinet={cabinet()} />);
    fireEvent.click(screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ }));
    const result = await screen.findByTestId("selftest-result");
    expect(result).toHaveTextContent("GAS_VALVE ✓");
    expect(result).toHaveTextContent("ELEVATOR ✗");
    expect(result).toHaveTextContent("SIREN LECTURA"); // la sirena solo se lee
  });

  it("footer con fw y último heartbeat en UTC", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText(/edge-1\.4\.0/)).toBeInTheDocument();
    expect(screen.getByText(/HB 10:41:00 UTC/)).toBeInTheDocument();
  });
});
