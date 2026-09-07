// 1.1 — honestidad del reposo: el chip SASMEX solo con WR-1 declarado Y
// gabinete reportando, agenda de simulacros sin inventar datos. La franja de
// SIMULACRO ya no es de esta pantalla (T-6.19: `features/notices`).
import type { MobileStateOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";
import { Linking } from "react-native";

import { healthBanner, wr1Chip } from "./health";
import { HomeView } from "./HomeView";

const NOW = 1_800_000_000_000;

function state(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: "s-1",
    site_name: "Torre Reforma",
    server_ts: new Date(NOW).toISOString(),
    phase: "idle",
    incident: null,
    latest_tier: null,
    my_zone: {
      zone_id: "z-1",
      name: "P10-A",
      level_code: "P10",
      evac_policy: "shelter",
    },
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: {
      active: false,
      next_scheduled_at: null,
      last_started_at: null,
      last_note: null,
    },
    site_health: {
      status: "OPERATIVO",
      heartbeat_at: new Date(NOW - 30_000).toISOString(),
      age_s: 30,
      has_wr1: true,
    },
    ...over,
  } as MobileStateOut;
}

const NOOP = { onOpenRutas: jest.fn(), onOpenDirectorio: jest.fn() };

describe("HomeView (1.1)", () => {
  it("reposo sano: SEGURO + chip WR-1 + zona con política", async () => {
    const v = await render(
      <HomeView brigadistas={[]} data={state()} nowMs={NOW} {...NOOP} />,
    );
    expect(v.getByTestId("estado")).toHaveTextContent("SEGURO");
    expect(v.getByTestId("wr1-chip")).toHaveTextContent(
      "SASMEX WR-1 · GABINETE ENLAZADO",
    );
    expect(v.getByText("P10-A")).toBeTruthy();
    expect(v.getByText("ZONA DE REPLIEGUE")).toBeTruthy();
    expect(v.queryByTestId("drill-banner")).toBeNull();
  });

  it("[T-6.19] la franja de simulacro NO vive aquí: la pinta el layout, igual en todas las pestañas", async () => {
    // Antes esta pantalla pintaba «SIMULACRO EN CURSO» con solo `active` (la
    // ventana de reloj): el 2026-09-06 lo anunció tres minutos con los dos
    // gabinetes en RECHAZADO. Ahora la franja sale de `execution` y se monta
    // en `(occupant)/_layout.tsx`; INICIO sigue siendo contenido NORMAL bajo
    // ella — jamás una pantalla de crisis.
    const v = await render(
      <HomeView
        brigadistas={[]}
        data={state({
          demo_mode: true,
          drill: {
            active: true,
            next_scheduled_at: null,
            last_started_at: null,
            last_note: null,
            execution: "executing",
            sites_total: 1,
            sites_executing: 1,
          },
        })}
        nowMs={NOW}
        {...NOOP}
      />,
    );
    expect(v.queryByTestId("drill-banner")).toBeNull();
    expect(v.queryByTestId("demo-mode-banner")).toBeNull();
    expect(v.getByTestId("estado")).toBeTruthy();
    expect(v.queryByText(/EVACÚE|REPLIÉGUESE AHORA/)).toBeNull();
  });

  it("[T-6.19] reingreso autorizado: relleno sólido + glifo (forma, no solo verde)", async () => {
    const v = await render(
      <HomeView brigadistas={[]} data={state({ phase: "reentry_approved" })} nowMs={NOW} {...NOOP} />,
    );
    const banner = v.getByTestId("reentry-banner");
    expect(banner).toHaveTextContent(/REINGRESO AUTORIZADO/);
    const style = Object.assign({}, ...[banner.props.style].flat(Infinity).filter(Boolean));
    expect(style.backgroundColor).toBeTruthy();
    expect(style.borderLeftWidth).toBeUndefined();
    expect(v.getByTestId("reentry-glyph")).toBeTruthy();
  });

  it("agenda: sin datos dice 'sin programar'/'sin registro', no inventa", async () => {
    const v = await render(
      <HomeView brigadistas={[]} data={state()} nowMs={NOW} {...NOOP} />,
    );
    expect(v.getByText("sin programar")).toBeTruthy();
    expect(v.getByText("sin registro")).toBeTruthy();
  });

  it("brigadista con teléfono: LLAMAR dispara tel: (un toque)", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    const v = await render(
      <HomeView
        brigadistas={[
          {
            user_id: "b-1",
            display_name: "Brigada Uno",
            role: "brigadista",
            zone_id: "z-1",
            zone_name: "P10-A",
            phone: "+525511112222",
          },
        ]}
        data={state()}
        nowMs={NOW}
        {...NOOP}
      />,
    );
    await fireEvent.press(v.getByTestId("call-b-1"));
    expect(spy).toHaveBeenCalledWith("tel:+525511112222");
    spy.mockRestore();
  });
});

describe("health — mapeo puro del estado del servidor", () => {
  const base = {
    status: "OPERATIVO",
    heartbeat_at: new Date(NOW - 10 * 60_000).toISOString(),
    age_s: 600,
    has_wr1: true,
  };

  it("OPERATIVO⇒SEGURO(ok) · DEGRADADO(warn) · SIN ENLACE(crit) con último contacto", () => {
    expect(healthBanner({ ...base }, NOW)).toMatchObject({
      label: "SEGURO",
      tone: "ok",
    });
    expect(healthBanner({ ...base, status: "DEGRADADO" }, NOW).tone).toBe(
      "warn",
    );
    const sin = healthBanner({ ...base, status: "SIN ENLACE" }, NOW);
    expect(sin.tone).toBe("crit");
    expect(sin.detail).toMatch(/último contacto hace 10 min/);
  });

  it("sin gabinete jamás reportado: lo dice tal cual", () => {
    expect(
      healthBanner(
        {
          status: "SIN ENLACE",
          heartbeat_at: null,
          age_s: null,
          has_wr1: false,
        },
        NOW,
      ).detail,
    ).toMatch(/Sin gabinete reportando/);
  });

  it("chip WR-1: SOLO con hardware declarado Y gabinete reportando", () => {
    expect(wr1Chip({ ...base })).toMatch(/SASMEX WR-1/);
    expect(wr1Chip({ ...base, has_wr1: false })).toBeNull();
    expect(wr1Chip({ ...base, status: "SIN ENLACE" })).toBeNull();
  });
});
