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
    const pre = preconditionsFor("activate", state(), { siren: null });
    expect(pre.every((p) => p.met)).toBe(true);
  });

  it("activar sin incidente: precondición NO cumplida (no checkbox ciego)", () => {
    const pre = preconditionsFor("activate", state({ phase: "idle" }), { siren: null });
    expect(pre.find((p) => /evacuación/.test(p.label))?.met).toBe(false);
  });

  // [T-2.110] Antes entraba un `sirenActive: boolean` y con él se perdía DE
  // DÓNDE salía: el detalle decía «El gabinete reporta la sirena activa» tanto
  // si el gabinete había medido el relé como si sólo había un `siren_on` viejo
  // en la traza. Ahora entra la EVIDENCIA y cada procedencia tiene su frase.
  const evidencia = (active: boolean, fromRelay: boolean) => ({
    active,
    fromRelay,
    at: "2026-07-16T10:00:00Z",
  });

  it("silenciar refleja si la sirena suena de verdad", () => {
    expect(
      preconditionsFor("deactivate", state(), { siren: evidencia(true, true) })[0].met,
    ).toBe(true);
    expect(
      preconditionsFor("deactivate", state(), { siren: evidencia(false, true) })[0].met,
    ).toBe(false);
  });

  it("silenciar sin evidencia alguna NO se autoriza sola", () => {
    const pre = preconditionsFor("deactivate", state(), { siren: null })[0];
    expect(pre.met).toBe(false);
    expect(pre.detail).toMatch(/No consta ninguna actuación de sirena/);
  });

  it("el detalle sólo atribuye al gabinete lo que el gabinete midió", () => {
    expect(
      preconditionsFor("deactivate", state(), { siren: evidencia(true, true) })[0].detail,
    ).toMatch(/El gabinete reporta el relé/);
    expect(
      preconditionsFor("deactivate", state(), { siren: evidencia(true, false) })[0].detail,
    ).toMatch(/última orden ejecutada/);
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
          siren: null,
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
        preconditions={preconditionsFor("activate", state(), { siren: null })}
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
      // [T-2.116] El acuse REAL: el estado del canal tras el arbitraje.
      ack: {
        channel: "siren",
        action: "deactivate",
        success: true,
        detail: "relay",
        channel_state: {
          channel: "siren",
          energized: true,
          activated: true,
          fail_safe: "NO",
          reason: "alert",
          alert_latched: true,
        },
      },
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
