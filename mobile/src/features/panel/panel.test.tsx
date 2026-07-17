// 2.1 — honestidad del dashboard: UPS sin dato ⇒ "S/D" (JAMÁS 0%), métricas
// nulas ⇒ S/D, features en espera declarada, y la traza BMS usa la MISMA
// agrupación compartida que la consola (@takab/sdk · groupActions).
import { groupActions, type IncidentActionOut, type MobileSiteHealthOut } from "@takab/sdk";
import { render } from "@testing-library/react-native";

import { mergeAction } from "./actions";
import { applyHealthFrame, fmtMetric, upsLabel } from "./health";
import { PanelView } from "./PanelView";

const NOW = 1_800_000_000_000;

const HEALTH: MobileSiteHealthOut = {
  status: "OPERATIVO",
  heartbeat_at: new Date(NOW - 60_000).toISOString(),
  age_s: 60,
  has_wr1: true,
  mqtt_rtt_ms: 77,
  seedlink_lag_s: 1.2,
  ntp_offset_ms: -0.2,
  cpu_temp_c: 51.3,
  power_status: null,
  battery_pct: null,
  cert_days_remaining: 120,
};

const ACTION: IncidentActionOut = {
  action_id: "a-1",
  incident_id: "i-1",
  tenant_id: "t-1",
  ts: "2026-07-16T10:00:05Z",
  kind: "siren_on",
  actor: "system",
  payload: {},
};

describe("health — S/D honesto (contrato T-1.40)", () => {
  it("UPS unknown/null ⇒ 'S/D', JAMÁS un 0%", () => {
    expect(upsLabel(null, null)).toBe("S/D");
    expect(upsLabel("unknown", null)).toBe("S/D");
    expect(upsLabel(null, 0)).toBe("S/D");
    expect(upsLabel("on_battery", null)).toBe("EN BATERÍA · S/D");
    expect(upsLabel("on_battery", 47.6)).toBe("EN BATERÍA · 48%");
    expect(upsLabel("mains", 100)).toBe("EN PARED");
  });

  it("métrica nula ⇒ S/D; con dato, formato con unidad", () => {
    expect(fmtMetric(null, " ms")).toBe("S/D");
    expect(fmtMetric(undefined, " s", 1)).toBe("S/D");
    expect(fmtMetric(77, " ms")).toBe("77 ms");
    expect(fmtMetric(1.234, " s", 1)).toBe("1.2 s");
  });

  it("applyHealthFrame: solo un frame MÁS NUEVO actualiza; el status NO se recalcula", () => {
    const older = applyHealthFrame(HEALTH, {
      kind: "device_health",
      tenant_id: "t-1",
      gateway_id: "g-1",
      ts: new Date(NOW - 120_000).toISOString(),
      mqtt_rtt_ms: 999,
    } as never);
    expect(older).toBe(HEALTH); // snapshot más fresco: intacto

    const newer = applyHealthFrame(HEALTH, {
      kind: "device_health",
      tenant_id: "t-1",
      gateway_id: "g-1",
      ts: new Date(NOW).toISOString(),
      mqtt_rtt_ms: 999,
      power_status: "on_battery",
      battery_pct: 80,
    } as never);
    expect(newer.mqtt_rtt_ms).toBe(999);
    expect(newer.power_status).toBe("on_battery");
    expect(newer.status).toBe("OPERATIVO"); // el estado lo deriva el SERVIDOR
    expect(newer.cpu_temp_c).toBeNull(); // el frame no lo trajo: S/D honesto
  });
});

describe("mergeAction — traza live idempotente", () => {
  it("dedupe por action_id y filtro por incidente", () => {
    const frame = { ...ACTION, type: "incident_action" as const };
    const once = mergeAction([], frame, "i-1");
    expect(once).toHaveLength(1);
    expect(mergeAction(once, frame, "i-1")).toHaveLength(1); // replay
    expect(mergeAction([], frame, "i-OTRO")).toHaveLength(0);
  });
});

describe("PanelView (2.1)", () => {
  const BASE = {
    siteName: "Torre Reforma",
    tier: "normal",
    health: HEALTH,
    live: "ready" as const,
    latestByChannel: [],
    featuresAtMs: null,
    groups: [],
    incidentOpen: false,
    nowMs: NOW,
  };

  it("UPS sin dato pinta S/D (jamás 0%) y las métricas reales con unidad", async () => {
    const v = await render(<PanelView {...BASE} />);
    expect(v.getByText("S/D")).toBeTruthy(); // UPS
    expect(v.getByText("77 ms")).toBeTruthy();
    expect(v.getByText(/SALUD DEL GABINETE · OPERATIVO/)).toBeTruthy();
    expect(v.queryByText(/0%/)).toBeNull();
  });

  it("sin frames de features: espera DECLARADA; sin incidente: traza en reposo", async () => {
    const v = await render(<PanelView {...BASE} />);
    expect(v.getByTestId("features-waiting")).toBeTruthy();
    expect(v.getByTestId("bms-idle")).toBeTruthy();
  });

  it("BMS: la agrupación COMPARTIDA de la consola pinta último estado + ×N", async () => {
    const groups = groupActions([
      ACTION,
      { ...ACTION, action_id: "a-2", ts: "2026-07-16T10:00:09Z" },
    ]);
    const v = await render(<PanelView {...BASE} groups={groups} incidentOpen={true} />);
    expect(v.getByTestId("bms-siren_on")).toHaveTextContent(/SIRENA/);
    expect(v.getByTestId("bms-siren_on")).toHaveTextContent(/ACTIVADA/);
    expect(v.getByTestId("bms-siren_on")).toHaveTextContent(/×2/);
  });

  it("features presentes: valores por canal, sin forma de onda", async () => {
    const v = await render(
      <PanelView
        {...BASE}
        featuresAtMs={NOW - 2_000}
        latestByChannel={[
          { channel: "EHZ", ts: new Date(NOW).toISOString(), pga_g: 0.152, stalta: 3.1 },
        ]}
      />,
    );
    expect(v.getByTestId("feat-EHZ")).toHaveTextContent(/PGA 0.152 g/);
    expect(v.getByTestId("feat-EHZ")).toHaveTextContent(/STA\/LTA 3.10/);
    expect(v.getByText(/sin forma de onda/)).toBeTruthy();
  });
});
