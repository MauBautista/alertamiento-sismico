import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GatewayOut } from "@takab/sdk";

import SiteCard from "./SiteCard";
import type { FleetCabinet } from "./useFleet";

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

  it("autodiagnóstico silencioso: visible pero deshabilitado con la razón", () => {
    render(<SiteCard cabinet={cabinet()} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("self_test"));
  });

  it("footer con fw y último heartbeat en UTC", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText(/edge-1\.4\.0/)).toBeInTheDocument();
    expect(screen.getByText(/HB 10:41:00 UTC/)).toBeInTheDocument();
  });
});
