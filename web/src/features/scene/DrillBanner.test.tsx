// DrillBanner (T-1.60 · reescrito en T-2.48 · al shell en T-6.01): rotulado
// NO-real, precedencia decidida por la TABLA de escena, gates de matriz y los 4
// estados obligatorios sobre `/drills/active`.
//
// El bug que cerró T-2.48: el banner ignoraba `loading` y, si `/drills/active`
// fallaba con un simulacro VIVO, desaparecía en silencio. Un simulacro en curso
// que deja de anunciarse es indistinguible de una alerta real para quien está
// dentro del edificio.
//
// [T-6.01] El banner ya no llama al hook: recibe `data` de `SceneStrip` y la
// `scene` resuelta. Lo que se mide aquí es cómo PINTA cada escena; quién decide
// la escena lo mide `scene.test.ts`, y que nadie más la decida,
// `sceneCensus.test.ts`.

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import type { ActiveDrillData } from "../console/useActiveDrill";
import DrillBanner from "./DrillBanner";
import type { Scene } from "./scene";

const NOW = Date.parse("2026-08-04T18:00:00Z");

function drillData(over: Partial<ActiveDrillData> = {}): ActiveDrillData {
  return {
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
    pending: false,
    error: null,
    ...over,
  };
}

const DRILL = {
  drill_id: "d-1",
  tenant_id: "t-1",
  initiated_by: "u-1",
  note: null,
  duration_s: 300,
  scheduled_at: null,
  started_at: "2026-08-04T17:58:00Z",
  stopped_at: null,
  stop_reason: null,
  active: true,
  sites: [
    {
      site_id: "s-1",
      site_name: "Sitio Dev",
      command_id: "c-1",
      command_status: "acked",
      ack: null,
      commandable: true,
    },
  ],
};

/** Agenda a las 18:05Z: dentro de la ventana de armado desde las 17:50Z. */
const AGENDA = {
  ...DRILL,
  drill_id: "ag-1",
  active: false,
  scheduled_at: "2026-08-04T18:05:00Z",
  started_at: "2026-08-04T12:00:00Z",
  sites: [
    {
      site_id: "s-1",
      site_name: "Sitio Dev",
      command_id: null,
      command_status: null,
      ack: null,
      commandable: true,
    },
  ],
};

function pintar(data: ActiveDrillData, scene: Scene = "drill") {
  return render(<DrillBanner data={data} scene={scene} />);
}

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DrillBanner", () => {
  it("con drill activo pinta el banner rotulado NO-real", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    pintar(drillData({ drill: DRILL }));
    const banner = screen.getByTestId("drill-banner");
    expect(banner).toHaveTextContent("SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL");
    expect(banner).toHaveTextContent("1 SITIO(S)");
    // soc_operator no puede terminarlo (gate drill_start).
    expect(screen.queryByRole("button", { name: "TERMINAR" })).toBeNull();
  });

  it("con la ALERTA REAL mandando el banner se degrada a badge: lo real domina", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ drill: DRILL }), "alert");
    expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
    expect(screen.queryByTestId("drill-banner")).toBeNull();
  });

  it("[U-28] con un AVISO instrumental NO se degrada: una estación sola no domina nada", () => {
    // Hasta T-6.01 el badge salía con CUALQUIER incidente crítico, incluido el
    // umbral de una sola estación que por política (T-2.32) sólo avisa. La
    // escena `notice` es esa: el simulacro sigue siendo el banner completo.
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ drill: DRILL }), "notice");
    expect(screen.getByTestId("drill-banner")).toHaveTextContent("ESTO NO ES UNA ALERTA REAL");
    expect(screen.queryByTestId("drill-badge")).toBeNull();
  });

  it("en escena NORMAL (sin drill) no pinta NADA visible: la ausencia es la franja", () => {
    // [U-45] La consola dedicaba una franja permanente a «SIN SIMULACRO EN
    // CURSO». El estado sigue existiendo para la tabla y los tests (`empty`),
    // pero no ocupa un píxel.
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const { container } = pintar(drillData(), "normal");
    const marco = container.querySelector('[data-state="empty"]');
    expect(marco).not.toBeNull();
    expect(marco).toHaveAttribute("hidden");
    expect(screen.queryByText(/SIN SIMULACRO/)).toBeNull();
  });

  it("tenant_admin puede TERMINAR el drill activo", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const stop = vi.fn();
    pintar(drillData({ drill: DRILL, stop }));
    fireEvent.click(screen.getByRole("button", { name: "TERMINAR" }));
    expect(stop).toHaveBeenCalledWith("d-1");
  });

  it("el fallo de TERMINAR se pinta junto al botón, en la propia franja", () => {
    // Quien pulsa desde /fleet no tiene delante la tira de /console.
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ drill: DRILL, error: "el simulacro no se detuvo (HTTP 409)" }));
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP 409");
  });

  // --- El bug que motivó la reescritura de T-2.48 ---------------------------

  it("si /drills/active FALLA con el simulacro vivo, el banner NO desaparece", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const { container } = pintar(
      drillData({ drill: DRILL, readError: "GET /drills/active falló (503)" }),
    );
    // Sigue visible y rotulado NO-real…
    expect(screen.getByTestId("drill-banner")).toHaveTextContent("ESTO NO ES UNA ALERTA REAL");
    // …pero declarado como dato RETENIDO, jamás como lectura viva.
    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(screen.getByText(/DATOS RETENIDOS/)).toBeInTheDocument();
  });

  it("sin ningún dato conocido, el fallo se MUESTRA (no se calla)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const refetch = vi.fn();
    const { container } = pintar(
      drillData({ readError: "GET /drills/active falló (503)", refetch }),
      "normal",
    );
    expect(container.querySelector('[data-state="error"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("mientras carga NO afirma que no hay simulacro", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const { container } = pintar(drillData({ loading: true }), "normal");
    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
    expect(screen.queryByTestId("drill-banner")).toBeNull();
  });

  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const byState: Record<UiState, Partial<ActiveDrillData>> = {
      loading: { loading: true },
      error: { readError: "boom" },
      empty: {},
      stale: { drill: DRILL, readError: "boom" },
    };
    expectFourStates((state) => <DrillBanner data={drillData(byState[state])} scene="drill" />);
  });

  // --- Simulacro ARMADO ------------------------------------------------------

  it("a T−15 min aparece el banner armado; el disparo aún no está habilitado", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ scheduled: [AGENDA] }), "normal");
    const armed = screen.getByTestId("drill-armed");
    expect(armed).toHaveTextContent("SIMULACRO ARMADO");
    expect(armed).toHaveTextContent("18:05:00");
    expect(screen.getByRole("button", { name: "EJECUTAR AHORA" })).toBeDisabled();
  });

  it("fuera de la ventana de armado no hay banner", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:30:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ scheduled: [AGENDA] }), "normal");
    expect(screen.queryByTestId("drill-armed")).toBeNull();
  });

  it("a T−0 EJECUTAR AHORA queda precargado: un clic humano, con su agenda", () => {
    vi.setSystemTime(Date.parse("2026-08-04T18:06:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const start = vi.fn();
    pintar(drillData({ scheduled: [AGENDA], start }), "normal");
    const run = screen.getByRole("button", { name: "EJECUTAR AHORA" });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(start).toHaveBeenCalledWith({ fromScheduled: "ag-1" });
  });

  it("CANCELAR retira la agenda antes de que ocurra", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const cancel = vi.fn();
    pintar(drillData({ scheduled: [AGENDA], cancel }), "normal");
    fireEvent.click(screen.getByRole("button", { name: "CANCELAR" }));
    expect(cancel).toHaveBeenCalledWith("ag-1");
  });

  it("un rol sin drill_start VE el armado pero no puede tocarlo", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    pintar(drillData({ scheduled: [AGENDA] }), "normal");
    expect(screen.getByTestId("drill-armed")).toHaveTextContent("SIMULACRO ARMADO");
    expect(screen.queryByRole("button", { name: "EJECUTAR AHORA" })).toBeNull();
    expect(screen.queryByRole("button", { name: "CANCELAR" })).toBeNull();
  });

  it("el armado NO se degrada bajo alerta real: es un aviso, no un simulacro sonando", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    pintar(drillData({ scheduled: [AGENDA] }), "alert");
    expect(screen.getByTestId("drill-armed")).toBeInTheDocument();
    expect(screen.queryByTestId("drill-badge")).toBeNull();
  });

  it("el simulacro EN CURSO manda sobre el armado", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    pintar(drillData({ drill: DRILL, scheduled: [AGENDA] }));
    expect(screen.getByTestId("drill-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("drill-armed")).toBeNull();
  });
});
