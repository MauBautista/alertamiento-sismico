import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SiteStateFrame } from "@takab/sdk";

import { expectFourStates, type UiState } from "../../test-utils/states";
import DetailPanel, { FEATURES_STALE_MS } from "./DetailPanel";
import type { IncidentActionsData } from "./useIncidentActions";
import type { FeaturePoint, SiteFeaturesData } from "./useSiteFeatures";

const NOW = Date.parse("2026-07-08T10:41:35Z");
const SITE = { site_id: "s-1", name: "Planta Cholula", coords: "19.0633°N · 98.3014°W" };

function point(ts: number, pga: number): FeaturePoint {
  return { ts, pga, pgv: 1.5, stalta: 1.0, clipping: false };
}

function features(over: Partial<SiteFeaturesData> = {}): SiteFeaturesData {
  return {
    points: [point(NOW - 2000, 0.01), point(NOW - 1000, 0.02)],
    latest: point(NOW - 1000, 0.02),
    calibrated: false,
    loading: false,
    error: null,
    lastFrameAt: NOW - 1000,
    refetch: vi.fn(),
    ...over,
  };
}

function actions(over: Partial<IncidentActionsData> = {}): IncidentActionsData {
  return {
    actions: [
      {
        action_id: "a-1",
        incident_id: "i-1",
        tenant_id: "t-1",
        ts: "2026-07-08T10:41:31Z",
        kind: "siren_on",
        actor: "edge:gw-dev-0001",
        payload: {},
      },
    ],
    loading: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

const SOH: SiteStateFrame = {
  type: "site_state",
  kind: "device_health",
  tenant_id: "t-1",
  gateway_id: "g-1",
  site_id: "s-1",
  ts: "2026-07-08T10:41:30Z",
  ntp_offset_ms: 4.2,
  seedlink_lag_s: 0.4,
};

function renderPanel(over: Partial<Parameters<typeof DetailPanel>[0]> = {}) {
  const onClose = vi.fn();
  render(
    <DetailPanel
      site={SITE}
      features={features()}
      soh={SOH}
      actions={actions()}
      nowMs={NOW}
      cctvEnabled={false}
      onClose={onClose}
      {...over}
    />,
  );
  return { onClose };
}

describe("DetailPanel", () => {
  it("readouts PGA/PGV, SOH real y caption honesto de features 1 s", () => {
    renderPanel();
    expect(screen.getByText("Planta Cholula")).toBeInTheDocument();
    expect(screen.getByText("0.020")).toBeInTheDocument(); // PGA
    expect(screen.getByText("±4 ms")).toBeInTheDocument(); // NTP del frame real
    expect(screen.getByText("0.4 s")).toBeInTheDocument(); // lag seedlink
    expect(screen.getAllByText(/FEATURES 1 s/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/200 Hz/)).toBeNull(); // sin framing de waveform crudo
    expect(screen.getByTestId("features-live-pill")).toHaveTextContent("LIVE");
  });

  it("sin calibrar: unidades relativas y aviso, nunca 'g' ni 'cm/s'", () => {
    // El edge escala counts con sensibilidades placeholder (T-1.6 diferida). Pintar
    // 'g' aquí sería inventarse una magnitud física (regla de oro 7).
    renderPanel({ features: features({ calibrated: false }) });
    expect(screen.getByTestId("not-calibrated-badge")).toBeInTheDocument();
    expect(screen.getAllByText("rel.")).toHaveLength(2); // PGA y PGV
    expect(screen.queryByText("g")).toBeNull();
    expect(screen.queryByText("cm/s")).toBeNull();
  });

  it("calibrado: unidades físicas y sin aviso", () => {
    renderPanel({ features: features({ calibrated: true }) });
    expect(screen.queryByTestId("not-calibrated-badge")).toBeNull();
    expect(screen.getByText("g")).toBeInTheDocument();
    expect(screen.getByText("cm/s")).toBeInTheDocument();
  });

  it("con el flag aún sin cargar tampoco se promete física", () => {
    renderPanel({ features: features({ calibrated: undefined }) });
    expect(screen.getByTestId("not-calibrated-badge")).toBeInTheDocument();
  });

  it("traza de actuadores con ACK del edge y timestamp", () => {
    renderPanel();
    expect(screen.getByText("SIREN ON")).toBeInTheDocument();
    expect(screen.getByText("ACTIVADA")).toBeInTheDocument();
    expect(screen.getByText(/EDGE:GW-DEV-0001 · 10:41:31 UTC/)).toBeInTheDocument();
  });

  it("sin SOH muestra S/D (jamás inventa salud) y sin live el pill lo dice", () => {
    renderPanel({ soh: null, features: features({ lastFrameAt: NOW - FEATURES_STALE_MS - 1 }) });
    expect(screen.getAllByText("S/D").length).toBeGreaterThan(0);
    expect(screen.getByTestId("features-live-pill")).toHaveTextContent("SIN LIVE");
  });

  it("CCTV solo existe tras la feature flag (criterio #2)", () => {
    renderPanel();
    expect(screen.queryByTestId("cctv-placeholder")).toBeNull();
    renderPanel({ cctvEnabled: true });
    expect(screen.getByTestId("cctv-placeholder")).toBeInTheDocument();
  });

  it("cerrar despacha onClose", () => {
    const { onClose } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    const byState: Record<UiState, Partial<SiteFeaturesData>> = {
      loading: { loading: true },
      error: { error: "GET falló (503)", points: [], latest: null },
      empty: { points: [], latest: null, lastFrameAt: null },
      stale: { lastFrameAt: NOW - FEATURES_STALE_MS - 1 },
    };
    expectFourStates((state) => (
      <DetailPanel
        site={SITE}
        features={features(byState[state])}
        soh={SOH}
        actions={actions()}
        nowMs={NOW}
        cctvEnabled={false}
        onClose={vi.fn()}
      />
    ));
  });
});
