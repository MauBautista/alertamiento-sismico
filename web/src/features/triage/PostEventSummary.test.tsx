import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ForensicsOut } from "@takab/sdk";

import PostEventSummary, { catalogView, leadTimeView } from "./PostEventSummary";

function forensics(over: Partial<ForensicsOut> = {}): ForensicsOut {
  return {
    incident_id: "i-1",
    site: null,
    window_from: "2026-08-03T09:59:55Z",
    window_to: "2026-08-03T10:03:00Z",
    channels: [{ channel: "ENZ", clipped: false, samples: 120 }],
    peak_pga_g: 0.081,
    peak_pgv_cms: 3.2,
    peak_ts: "2026-08-03T10:00:35Z",
    felt_band: "trip",
    lead_time_s: 35,
    lead_time_reason: null,
    station_count: 4,
    peers: [],
    catalog: null,
    catalog_delta: null,
    sensors: [],
    calibrated: true,
    ...over,
  } as ForensicsOut;
}

function arrange(data: ForensicsOut | undefined, over = {}) {
  render(
    <PostEventSummary
      forensics={{ data, loading: false, error: null, refetch: vi.fn(), ...over }}
    />,
  );
}

describe("leadTimeView · el tiempo de aviso ganado [T-2.40]", () => {
  it("con SASMEX y pico medido da los segundos", () => {
    expect(leadTimeView(forensics())).toMatchObject({ value: "35.0 s", tone: "ok" });
  });

  // Un "0 s" sin explicación se lee como un fallo del sistema; casi siempre significa
  // que el incidente ni siquiera vino de SASMEX.
  it("sin SASMEX dice NO CALCULABLE y explica por qué", () => {
    const view = leadTimeView(forensics({ lead_time_s: null, lead_time_reason: "not_sasmex" }));
    expect(view.value).toBe("NO CALCULABLE");
    expect(view.note).toMatch(/no vino de SASMEX/);
  });

  it("sin pico medido también explica la causa", () => {
    expect(
      leadTimeView(forensics({ lead_time_s: null, lead_time_reason: "no_peak" })).note,
    ).toMatch(/SIN PICO/);
  });

  it("una razón desconocida se muestra tal cual, no se traga", () => {
    expect(
      leadTimeView(forensics({ lead_time_s: null, lead_time_reason: "algo_nuevo" })).note,
    ).toBe("algo_nuevo");
  });
});

describe("catalogView · contraste con el catálogo de referencia", () => {
  it("sin coincidencia lo dice y acota la ventana", () => {
    const view = catalogView(forensics());
    expect(view.value).toBe("SIN COINCIDENCIA");
    expect(view.note).toMatch(/±120 s/);
  });

  it("con coincidencia da distancia, rumbo y Δt", () => {
    const view = catalogView(
      forensics({
        catalog: {
          catalog_key: "SSN-2026-001",
          origin_time: "2026-08-03T10:00:00Z",
          magnitude: 7.1,
          source: "SSN",
          dt_s: 12,
        } as ForensicsOut["catalog"],
        catalog_delta: { km: 187.4, bearing: "SSO", dt_s: 12, magnitude: 7.1 },
      }),
    );
    expect(view.value).toBe("187 km SSO");
    expect(view.note).toMatch(/SSN SSN-2026-001 · M 7.1 · Δt 12 s/);
  });

  it("sin epicentro propio no inventa una distancia", () => {
    const view = catalogView(
      forensics({
        catalog: {
          catalog_key: "SSN-X",
          origin_time: "2026-08-03T10:00:00Z",
          source: "SSN",
          dt_s: 5,
        } as ForensicsOut["catalog"],
        catalog_delta: { km: null, bearing: null, dt_s: 5, magnitude: null },
      }),
    );
    expect(view.value).toBe("SIN EPICENTRO PROPIO");
  });
});

describe("PostEventSummary", () => {
  it("pinta los cuatro números del post-mortem", () => {
    arrange(forensics());
    const panel = screen.getByTestId("post-event-summary");
    expect(panel).toHaveTextContent("TIEMPO DE AVISO GANADO");
    expect(panel).toHaveTextContent("35.0 s");
    expect(panel).toHaveTextContent("ESTACIONES QUE CONTRIBUYERON");
    expect(panel).toHaveTextContent("4");
    expect(panel).toHaveTextContent("0.081 g");
  });

  // Sin procedencia de calibración el número NO está en gravedades.
  it("un sensor sin calibrar convierte el pico en unidades relativas, y lo dice", () => {
    arrange(forensics({ calibrated: false }));
    expect(screen.getByTestId("post-event-summary")).toHaveTextContent(
      /UNIDADES RELATIVAS · SENSOR SIN CALIBRAR/,
    );
  });

  it("sin pico medido no escribe 0.000 g", () => {
    arrange(forensics({ peak_pga_g: null }));
    const panel = screen.getByTestId("post-event-summary");
    expect(panel).toHaveTextContent("SIN MEDICIÓN");
    expect(panel).not.toHaveTextContent("0.000 g");
  });

  it("el error de la consulta se declara con reintento", () => {
    arrange(undefined, { error: "GET /forensics falló (503)" });
    expect(screen.getByRole("alert")).toHaveTextContent(/503/);
  });
});
