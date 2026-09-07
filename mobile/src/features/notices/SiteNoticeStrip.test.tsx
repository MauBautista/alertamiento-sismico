// [T-6.19] La franja: forma, texto y movimiento (una entrada, una salida, ninguna
// con reduceMotion; jamás un bucle).
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";
import { Animated } from "react-native";

import { FADE_MS, SiteNoticeStrip } from "./SiteNoticeStrip";

function state(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: "s-1",
    site_name: "Torre Reforma",
    server_ts: "2026-09-06T15:00:00Z",
    phase: "idle",
    incident: null,
    latest_tier: null,
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: {
      active: false,
      next_scheduled_at: null,
      last_started_at: null,
      last_note: null,
      execution: "none",
      sites_total: 1,
      sites_executing: 0,
    },
    site_health: { status: "OPERATIVO", heartbeat_at: null, age_s: null, has_wr1: true },
    ...over,
  } as MobileStateOut;
}

function conDrill(execution: string, over: Record<string, unknown> = {}) {
  return state({
    drill: {
      active: execution === "executing",
      next_scheduled_at: null,
      last_started_at: null,
      last_note: null,
      execution,
      sites_total: 1,
      sites_executing: execution === "executing" ? 1 : 0,
      ...over,
    } as MobileStateOut["drill"],
  });
}

describe("SiteNoticeStrip", () => {
  it("sin avisos no pinta nada (ni la banda)", async () => {
    const v = await render(<SiteNoticeStrip data={state()} reduceMotion topInset={24} />);
    expect(v.queryByTestId("site-notices")).toBeNull();
    expect(v.queryByTestId("drill-banner")).toBeNull();
  });

  it("sin dato tampoco: la franja no inventa un simulacro", async () => {
    const v = await render(<SiteNoticeStrip data={null} reduceMotion topInset={24} />);
    expect(v.queryByTestId("site-notices")).toBeNull();
  });

  it("[U-01] gabinete en `rejected`: SIMULACRO ANUNCIADO, no EN CURSO", async () => {
    const v = await render(
      <SiteNoticeStrip data={conDrill("rejected")} reduceMotion topInset={24} />,
    );
    const banner = v.getByTestId("drill-banner");
    expect(banner).toHaveTextContent(/SIMULACRO ANUNCIADO — NINGÚN GABINETE LO EJECUTA/);
    expect(banner).not.toHaveTextContent(/EN CURSO/);
    expect(v.getByTestId("drill-notice-not_executing")).toBeTruthy();
  });

  it("gabinete ejecutando: SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL", async () => {
    const v = await render(
      <SiteNoticeStrip data={conDrill("executing")} reduceMotion topInset={24} />,
    );
    expect(v.getByTestId("drill-banner")).toHaveTextContent(
      /SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL/,
    );
  });

  it("[T-5.02] modo demostración: lo dice, y dice que el gabinete sigue armado", async () => {
    const v = await render(
      <SiteNoticeStrip data={state({ demo_mode: true })} reduceMotion topInset={24} />,
    );
    const demo = v.getByTestId("demo-mode-banner");
    expect(demo).toHaveTextContent(/LA NUBE NO ESTÁ ENVIANDO AVISOS/);
    expect(demo).toHaveTextContent(/sigue armada/);
    expect(v.queryByTestId("drill-banner")).toBeNull();
  });

  it("demostración y simulacro a la vez: dos avisos, la demostración primero", async () => {
    const v = await render(
      <SiteNoticeStrip
        data={{ ...conDrill("pending"), demo_mode: true }}
        reduceMotion
        topInset={24}
      />,
    );
    const json = JSON.stringify(v.toJSON());
    expect(json.indexOf("MODO DEMOSTRACIÓN")).toBeLessThan(json.indexOf("SIMULACRO ANUNCIADO"));
  });

  it("la FORMA distingue sin matiz: regla lateral y glifo, nunca relleno sólido", async () => {
    const v = await render(
      <SiteNoticeStrip data={conDrill("executing")} reduceMotion topInset={24} />,
    );
    const banner = v.getByTestId("drill-banner");
    const style = Object.assign({}, ...[banner.props.style].flat(Infinity).filter(Boolean));
    expect(style.borderLeftWidth).toBeGreaterThanOrEqual(4);
    // el fondo es el de tarjeta, no el ámbar del estado: el color va SOLO en la regla
    expect(style.backgroundColor).not.toBe(style.borderLeftColor);
    expect(banner.props.accessibilityRole).toBe("alert");
    expect(v.getByTestId("drill-glyph-volume-2")).toBeTruthy();
  });

  it("absorbe la barra de estado y solapa la banda que las pestañas reservan", async () => {
    const v = await render(
      <SiteNoticeStrip data={conDrill("executing")} reduceMotion topInset={30} />,
    );
    const strip = v.getByTestId("site-notices");
    const style = Object.assign({}, ...[strip.props.style].flat(Infinity).filter(Boolean));
    expect(style.paddingTop).toBe(30);
    expect(style.marginBottom).toBe(-(64 - 30));
  });

  it("con reduceMotion no anima: entra y sale sin transición", async () => {
    const timing = jest.spyOn(Animated, "timing");
    const v = await render(
      <SiteNoticeStrip data={conDrill("executing")} reduceMotion topInset={24} />,
    );
    expect(v.getByTestId("drill-banner")).toBeTruthy();
    await act(async () => {
      v.rerender(<SiteNoticeStrip data={state()} reduceMotion topInset={24} />);
    });
    expect(v.queryByTestId("drill-banner")).toBeNull();
    expect(timing).not.toHaveBeenCalled();
    timing.mockRestore();
  });

  it("sin reduceMotion: una entrada, una salida y NINGÚN bucle", async () => {
    jest.useFakeTimers();
    const loop = jest.spyOn(Animated, "loop");
    const timing = jest.spyOn(Animated, "timing");
    const v = await render(
      <SiteNoticeStrip data={conDrill("executing")} reduceMotion={false} topInset={24} />,
    );
    expect(v.getByTestId("drill-banner")).toBeTruthy();
    // el sondeo trae el MISMO aviso en un objeto nuevo: no se re-anima
    await act(async () => {
      v.rerender(
        <SiteNoticeStrip data={conDrill("executing")} reduceMotion={false} topInset={24} />,
      );
    });
    expect(timing).toHaveBeenCalledTimes(1);
    // se va: sigue montada mientras se funde, y desaparece al terminar
    await act(async () => {
      v.rerender(<SiteNoticeStrip data={state()} reduceMotion={false} topInset={24} />);
    });
    expect(v.getByTestId("drill-banner")).toBeTruthy();
    await act(async () => {
      jest.advanceTimersByTime(FADE_MS + 50);
    });
    expect(v.queryByTestId("drill-banner")).toBeNull();
    expect(timing).toHaveBeenCalledTimes(2);
    expect(loop).not.toHaveBeenCalled();
    loop.mockRestore();
    timing.mockRestore();
    jest.useRealTimers();
  });
});
