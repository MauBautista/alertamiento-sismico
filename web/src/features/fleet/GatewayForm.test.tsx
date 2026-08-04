import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { GatewayOut } from "@takab/sdk";

import GatewayForm from "./GatewayForm";

const GW: GatewayOut = {
  gateway_id: "g-1",
  site_id: "s-1",
  site_name: "Planta Cholula",
  site_code: "CHL-A",
  site_status: "active",
  serial: "TKB-0001",
  fw_version: "edge-1.4.0",
  iot_thing: "gw-dev-0001",
  status: "online",
  has_wr1: true,
  equipment: {
    siren: true,
    strobe: true,
    gas_valve: true,
    elevator: true,
    door_retainer: true,
  },
  installed_at: null,
  row_version: "8421",
  derived_state: "OPERATIVO",
  degrade_reasons: [],
  last_heartbeat_ts: null,
  power_status: null,
  battery_pct: null,
  cert_days_remaining: null,
  mqtt_rtt_ms: null,
  seedlink_lag_s: null,
  ntp_offset_ms: null,
};

function arrange(gw: Partial<GatewayOut> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(
    <GatewayForm
      gateway={{ ...GW, ...gw }}
      siteName="Planta Cholula"
      submitting={false}
      error={null}
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  );
  return { onSubmit, onCancel };
}

const save = () => screen.getByRole("button", { name: /GUARDAR GABINETE/ });

describe("GatewayForm · edición de gabinete [T-2.37]", () => {
  it("precarga el equipamiento del gabinete", () => {
    arrange({ equipment: { ...GW.equipment!, gas_valve: false } });
    expect(screen.getByLabelText("VÁLVULA DE GAS")).not.toBeChecked();
    expect(screen.getByLabelText("SIRENA")).toBeChecked();
  });

  it("envía el contrato COMPLETO de 5 booleanos, no solo lo cambiado", () => {
    const { onSubmit } = arrange();
    fireEvent.click(screen.getByLabelText("ASCENSORES"));
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0][0].equipment).toEqual({
      siren: true,
      strobe: true,
      gas_valve: true,
      elevator: false,
      door_retainer: true,
    });
  });

  // Sin `iot_thing` el worker de config sync excluye al gabinete: no es un detalle
  // cosmético, es la diferencia entre recibir umbrales firmados y no recibirlos nunca.
  it("avisa cuando el gabinete no tiene iot_thing", () => {
    arrange({ iot_thing: null });
    expect(screen.getByTestId("gateway-form-unsyncable")).toBeInTheDocument();
  });

  it("con iot_thing no muestra la advertencia", () => {
    arrange();
    expect(screen.queryByTestId("gateway-form-unsyncable")).not.toBeInTheDocument();
  });

  it("vaciar el iot_thing reactiva la advertencia en vivo", () => {
    arrange();
    fireEvent.change(screen.getByLabelText(/IOT THING/), { target: { value: "" } });
    expect(screen.getByTestId("gateway-form-unsyncable")).toBeInTheDocument();
  });

  it("recorta espacios de los identificadores", () => {
    const { onSubmit } = arrange();
    fireEvent.change(screen.getByLabelText(/SERIAL/), { target: { value: "  TKB-9  " } });
    fireEvent.change(screen.getByLabelText(/IOT THING/), { target: { value: " gw-9 " } });
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ serial: "TKB-9", iot_thing: "gw-9" });
  });

  it("sin serial no deja guardar", () => {
    arrange();
    fireEvent.change(screen.getByLabelText(/SERIAL/), { target: { value: "  " } });
    expect(save()).toBeDisabled();
  });

  it("CANCELAR no envía nada", () => {
    const { onSubmit, onCancel } = arrange();
    fireEvent.click(screen.getByRole("button", { name: "CANCELAR" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  // `status` lo deriva el heartbeat: un desplegable aquí haría que la Flota Edge
  // pudiera afirmar "online" sobre un gabinete muerto.
  it("no ofrece editar el estado del gabinete", () => {
    arrange();
    expect(screen.queryByLabelText(/ESTADO/)).not.toBeInTheDocument();
    expect(screen.queryByText("online")).not.toBeInTheDocument();
  });
});
