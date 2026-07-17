// 2.2 — flujo de 2 pasos y ack honesto: precondiciones prellenadas bloquean
// el paso 2; el ack se muestra tal cual (jamás finge que la sirena se apagó).
import type { CommandOut, MobileStateOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";

import { ControlSheet } from "./ControlSheet";
import { preconditionsFor } from "./preconditions";

function state(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: "s-1",
    site_name: "Torre",
    server_ts: "2026-07-16T10:00:00Z",
    phase: "alert_active",
    incident: null,
    latest_tier: "watch",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, next_scheduled_at: null, last_started_at: null, last_note: null },
    site_health: {
      status: "OPERATIVO",
      heartbeat_at: "2026-07-16T09:59:30Z",
      age_s: 30,
      has_wr1: true,
      mqtt_rtt_ms: 77,
      seedlink_lag_s: 1,
      ntp_offset_ms: 0,
      cpu_temp_c: 50,
      power_status: "mains",
      battery_pct: 100,
      cert_days_remaining: 90,
    },
    ...over,
  } as MobileStateOut;
}

const CB = { onConfirm: jest.fn(), onClose: jest.fn() };

describe("preconditionsFor — estado REAL prellenado", () => {
  it("activar: en evacuación + gabinete enlazado ⇒ todas cumplidas", () => {
    const pre = preconditionsFor("activate", state(), { sirenActive: false });
    expect(pre.every((p) => p.met)).toBe(true);
  });

  it("activar sin incidente: precondición NO cumplida (no checkbox ciego)", () => {
    const pre = preconditionsFor("activate", state({ phase: "idle" }), { sirenActive: false });
    expect(pre.find((p) => /evacuación/.test(p.label))?.met).toBe(false);
  });

  it("silenciar refleja si la sirena suena de verdad", () => {
    expect(preconditionsFor("deactivate", state(), { sirenActive: true })[0].met).toBe(true);
    expect(preconditionsFor("deactivate", state(), { sirenActive: false })[0].met).toBe(false);
  });
});

describe("ControlSheet (2.2)", () => {
  it("precondición no cumplida bloquea el paso 2", async () => {
    const v = await render(
      <ControlSheet
        {...CB}
        action="activate"
        busy={false}
        error={null}
        preconditions={preconditionsFor("activate", state({ phase: "idle" }), {
          sirenActive: false,
        })}
        result={null}
      />,
    );
    expect(v.getByTestId("pre-blocked")).toBeTruthy();
    await fireEvent.press(v.getByTestId("to-step-2"));
    expect(v.queryByTestId("slide-track")).toBeNull(); // sigue en paso 1
  });

  it("precondiciones cumplidas ⇒ avanza al deslizador (paso 2)", async () => {
    const v = await render(
      <ControlSheet
        {...CB}
        action="activate"
        busy={false}
        error={null}
        preconditions={preconditionsFor("activate", state(), { sirenActive: false })}
        result={null}
      />,
    );
    await fireEvent.press(v.getByTestId("to-step-2"));
    expect(v.getByTestId("slide-track")).toBeTruthy();
  });

  it("ack de silenciar con alerta vigente: NO finge éxito", async () => {
    const cmd = {
      command_id: "c",
      tenant_id: "t",
      site_id: "s",
      gateway_id: "g",
      issued_by: "u",
      channel: "siren",
      action: "deactivate",
      event_id: null,
      nonce: "n",
      issued_at: "2026-07-16T10:00:00Z",
      expires_at: "2026-07-16T10:00:30Z",
      status: "acked",
      ack: { siren: "on" },
      error: null,
    } as CommandOut;
    const v = await render(
      <ControlSheet
        {...CB}
        action="deactivate"
        busy={false}
        error={null}
        preconditions={[]}
        result={cmd}
      />,
    );
    expect(v.getByTestId("ack-title")).toHaveTextContent(/LA SIRENA SIGUE ACTIVA/);
  });
});
