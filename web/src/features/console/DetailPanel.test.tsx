import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { IncidentActionOut, SiteStateFrame } from "@takab/sdk";

import { expectFourStates, type UiState } from "../../test-utils/states";
import DetailPanel, { FEATURES_STALE_MS, ageLabel } from "./DetailPanel";
import type { LiveIncident } from "./useLiveIncidents";
import type { IncidentActionsData } from "./useIncidentActions";
import type { FeaturePoint, SiteFeaturesData } from "./useSiteFeatures";
import type { SiteRelaysData } from "./useSiteRelays";

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

function action(over: Partial<IncidentActionOut> = {}): IncidentActionOut {
  return {
    action_id: `a-${Math.random().toString(36).slice(2, 8)}`,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts: "2026-07-08T10:41:31Z",
    kind: "siren_on",
    actor: "edge:gw-dev-0001",
    payload: {},
    ...over,
  } as IncidentActionOut;
}

function actions(over: Partial<IncidentActionsData> = {}): IncidentActionsData {
  return {
    actions: [action({ action_id: "a-1" })],
    loading: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

const INCIDENT: LiveIncident = {
  incident_id: "i-1",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: null,
  opened_at: "2026-07-08T10:38:35Z",
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "sasmex",
  max_pga_g: null,
  max_pgv_cms: null,
};

const NO_RELAYS: SiteRelaysData = {
  relays: null,
  loading: false,
  error: null,
  dataUpdatedAt: Date.now(),
  refetch: () => undefined,
};

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
      incident={INCIDENT}
      relays={NO_RELAYS}
      nowMs={NOW}
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
    // Solo el readout de features promete física; la card del incidente usa
    // unidades del backend (numeric g) — aquí el incidente va sin picos.
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

  // ---- Card INCIDENTE (T-1.50) -------------------------------------------
  it("card del incidente: trigger etiquetado, evento honesto y edad — sin magnitud", () => {
    renderPanel();
    const card = screen.getByTestId("incident-card");
    expect(within(card).getByText("SASMEX")).toBeInTheDocument();
    expect(within(card).getByText("SIN EVENTO SÍSMICO ASOCIADO")).toBeInTheDocument();
    expect(within(card).getByText(/OPEN · T\+3min/)).toBeInTheDocument();
    expect(within(card).getByText(/— · —/)).toBeInTheDocument(); // PGA/PGV sin datos
    expect(within(card).getByText("SIN ACUSE")).toBeInTheDocument();
    expect(within(card).queryByText(/M \d/)).toBeNull(); // §14: sin magnitud
  });

  it("card del incidente: con evento y picos reales los muestra; acuse con actor", () => {
    renderPanel({
      incident: {
        ...INCIDENT,
        event_id: "EVT-MAN-1a2b3c4d",
        max_pga_g: 0.567,
        max_pgv_cms: 12.3,
      },
      actions: actions({
        actions: [
          action({ action_id: "a-1", kind: "siren_on", ts: "2026-07-08T10:39:00Z" }),
          action({ action_id: "a-2", kind: "ack", actor: "user:abc", ts: "2026-07-08T10:40:00Z" }),
        ],
      }),
    });
    const card = screen.getByTestId("incident-card");
    expect(within(card).getByText("EVT-MAN-1a2b3c4d")).toBeInTheDocument();
    expect(within(card).getByText(/0\.567 g · 12\.3 cm\/s/)).toBeInTheDocument();
    expect(within(card).getByText(/USER:ABC · 10:40:00 UTC/)).toBeInTheDocument();
  });

  it("sin incidente abierto la card lo declara (empty honesto)", () => {
    renderPanel({ incident: null });
    expect(screen.getByText("SIN INCIDENTE ABIERTO EN EL SITIO")).toBeInTheDocument();
  });

  // ---- BMS agrupado (T-1.50) ----------------------------------------------
  it("BMS agrupa por canal: una fila con último estado y ×N; expandir da la traza", () => {
    renderPanel({
      actions: actions({
        actions: [
          action({ action_id: "a-1", kind: "siren_on", ts: "2026-07-08T10:39:00Z" }),
          action({ action_id: "a-2", kind: "siren_on", ts: "2026-07-08T10:41:00Z" }),
          action({ action_id: "a-3", kind: "gas_valve_close", ts: "2026-07-08T10:39:30Z" }),
        ],
      }),
    });
    expect(screen.getByText("SIRENA")).toBeInTheDocument();
    expect(screen.getByText("×2")).toBeInTheDocument();
    expect(screen.getByText("ACTIVADA")).toBeInTheDocument();
    expect(screen.getByText("VÁLVULAS DE GAS")).toBeInTheDocument();
    // la hora mostrada es la de la acción MÁS RECIENTE del grupo
    expect(screen.getByText(/EDGE:GW-DEV-0001 · 10:41:00 UTC/)).toBeInTheDocument();

    const groupBtn = screen.getByRole("button", { name: /SIRENA/ });
    expect(groupBtn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(groupBtn);
    expect(groupBtn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/10:39:00 UTC · EDGE:GW-DEV-0001/)).toBeInTheDocument();
  });

  // ---- Relés (T-1.50) ------------------------------------------------------
  it("relés del gabinete: pinta la config activa o el estado honesto", () => {
    renderPanel({
      relays: {
        ...NO_RELAYS,
        relays: [{ key: "siren", label: "SIRENA", wiring: "NO", armed: true }],
      },
    });
    const card = screen.getByTestId("relays-card");
    expect(within(card).getByText("ARMADO")).toBeInTheDocument();
  });

  it("relés no visibles ⇒ mensaje honesto, jamás estados inventados", () => {
    renderPanel({ relays: NO_RELAYS });
    expect(screen.getByText(/CONFIG DE RELÉS NO VISIBLE/)).toBeInTheDocument();
  });

  it("M-6: un 500 de /fleet NO es 'config no visible' — es error con reintento", () => {
    const refetch = vi.fn();
    renderPanel({
      relays: { ...NO_RELAYS, error: "GET /fleet/gateways falló (500)", refetch },
    });
    const card = screen.getByTestId("relays-card");
    expect(within(card).queryByText(/CONFIG DE RELÉS NO VISIBLE/)).toBeNull();
    expect(within(card).getByText(/falló \(500\)/)).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: /REINTENTAR/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("M-6: flota vieja se rotula stale, no se pinta como fresca", () => {
    renderPanel({
      relays: {
        ...NO_RELAYS,
        relays: [{ key: "siren", label: "SIRENA", wiring: "NO", armed: true }],
        dataUpdatedAt: Date.now() - 10 * 60_000,
      },
    });
    const card = screen.getByTestId("relays-card");
    expect(within(card).getByText(/DATOS RETENIDOS/)).toBeInTheDocument();
  });

  // ---- CCTV (T-1.50) -------------------------------------------------------
  it("CCTV SIEMPRE visible con empty-state honesto (ahí VA la cámara)", () => {
    renderPanel();
    expect(screen.getByTestId("cctv-empty")).toHaveTextContent(
      "SIN CÁMARA CONFIGURADA · PENDIENTE DE HARDWARE",
    );
    expect(screen.getByText(/CCTV ONVIF/)).toBeInTheDocument();
  });

  it("sin SOH muestra S/D (jamás inventa salud) y sin live el pill lo dice", () => {
    renderPanel({ soh: null, features: features({ lastFrameAt: NOW - FEATURES_STALE_MS - 1 }) });
    expect(screen.getAllByText("S/D").length).toBeGreaterThan(0);
    expect(screen.getByTestId("features-live-pill")).toHaveTextContent("SIN LIVE");
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
        incident={INCIDENT}
        relays={NO_RELAYS}
        nowMs={NOW}
        onClose={vi.fn()}
      />
    ));
  });
});

describe("ageLabel", () => {
  it("segundos bajo 2 min, minutos después", () => {
    expect(ageLabel("2026-07-08T10:41:00Z", Date.parse("2026-07-08T10:41:45Z"))).toBe("T+45s");
    expect(ageLabel("2026-07-08T10:00:00Z", Date.parse("2026-07-08T10:41:45Z"))).toBe("T+41min");
  });
});
