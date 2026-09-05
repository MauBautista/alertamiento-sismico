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
      forensics={{
        data,
        loading: false,
        error: null,
        refetch: vi.fn(),
        dataUpdatedAt: Date.now(),
        staleSince: null,
        ...over,
      }}
    />,
  );
}

/** 2026-08-03 10:41:30 UTC — la hora que el marco tiene que imprimir. */
const HORA = Date.UTC(2026, 7, 3, 10, 41, 30);

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

describe("catalogView · correlación con el catálogo de referencia (T-5.11)", () => {
  // El criterio de identidad, tal como lo devuelve la API. Se declara una vez
  // porque los tres casos de abajo se distinguen SOLO por él.
  const criterio = { v_s_km_s: 3.6, margen_s: 30, radio_km: 1200, pga_minima_g: 0.001 };

  it("sin ningún candidato lo dice, y ya no cita una ventana fija", () => {
    const view = catalogView(
      forensics({
        catalog_correlation: {
          estado: "sin_correlacion",
          criterio,
          descartes: [],
        } as ForensicsOut["catalog_correlation"],
      }),
    );
    expect(view.value).toBe("SIN CORRELACIÓN");
    expect(view.note).toMatch(/criterio de identidad/);
    // El ±120 s era TODO el criterio, y citarlo lo presentaba como suficiente.
    expect(view.note).not.toMatch(/120 s/);
  });

  it("HAY UN EVENTO EN EL CATÁLOGO Y NO ES EL NUESTRO — y se puede decir", () => {
    // Es lo que el sistema no sabía afirmar. Sin esto, un descarte se pinta
    // igual que un catálogo vacío, y una pantalla vacía se lee «no pasó nada».
    const view = catalogView(
      forensics({
        catalog_correlation: {
          estado: "sin_correlacion",
          criterio,
          descartes: [
            {
              catalog_key: "SSN-CHILE",
              motivo: "fuera_de_radio",
              detalle: "el epicentro está fuera del radio máximo al sitio (6389 km)",
              km_al_sitio: 6389,
            },
          ],
        } as ForensicsOut["catalog_correlation"],
      }),
    );
    expect(view.value).toBe("SIN CORRELACIÓN");
    expect(view.note).toMatch(/ninguno es éste/);
    expect(view.note).toMatch(/SSN-CHILE/);
    expect(view.note).toMatch(/fuera del radio/);
  });

  it("con epicentro propio da distancia, rumbo y Δt: eso sí es un contraste", () => {
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
        catalog_correlation: {
          estado: "confirmado",
          verificacion: "contrastado",
          criterio,
          descartes: [],
        } as ForensicsOut["catalog_correlation"],
      }),
    );
    expect(view.value).toBe("187 km SSO");
    expect(view.note).toMatch(/SSN SSN-2026-001 · M 7.1 · Δt 12 s/);
  });

  it("[T-5.10] sin procedencia NO pinta la magnitud del catálogo", () => {
    // Casar no concede procedencia: una fila sin hora de consulta ni estado de
    // revisión es un dato que existe y no es citable.
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
        catalog_correlation: {
          estado: "sin_dato_externo",
          verificacion: "contrastado",
          criterio,
          descartes: [],
        } as ForensicsOut["catalog_correlation"],
      }),
    );
    expect(view.note).not.toMatch(/M 7.1/);
  });

  it("sin epicentro propio el acierto NO se presenta como contraste", () => {
    // Es la ruta del receptor, que es la normal. La identidad se estableció por
    // ventana, radio y coherencia — una afirmación distinta y más modesta.
    const view = catalogView(
      forensics({
        catalog: {
          catalog_key: "SSN-X",
          origin_time: "2026-08-03T10:00:00Z",
          source: "SSN",
          dt_s: 5,
          km_al_sitio: 295.4,
        } as ForensicsOut["catalog"],
        catalog_delta: { km: null, bearing: null, dt_s: 5, magnitude: null },
        catalog_correlation: {
          estado: "sin_dato_externo",
          verificacion: "no_verificable",
          criterio,
          descartes: [],
        } as ForensicsOut["catalog_correlation"],
      }),
    );
    expect(view.value).toBe("NO VERIFICABLE");
    expect(view.note).toMatch(/295 km del sitio/);
    expect(view.note).toMatch(/sin epicentro propio que contrastar/);
    // Y no inventa una distancia epicentro↔epicentro que no existe.
    expect(view.value).not.toMatch(/km [NSEO]/);
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

describe("PostEventSummary · el desempeño congelado se cita igual [T-2.82.a]", () => {
  it("con el dato viejo lo DICE, con la hora en que se supo", () => {
    // "35 s de aviso ganado" y "4 estaciones contribuyeron" son los números que
    // una Protección Civil cita como desempeño de la red. Congelados se citan
    // exactamente igual: nada en el panel distinguía la medición de hace un
    // segundo de la de hace media hora.
    arrange(forensics(), { staleSince: HORA });
    expect(screen.getByTestId("post-event-summary")).toHaveTextContent(
      "DATOS RETENIDOS · 10:41:30 UTC",
    );
  });

  it("y sigue enseñando los números bajo la franja, no en su lugar", () => {
    arrange(forensics(), { staleSince: HORA });
    expect(screen.getByTestId("post-event-summary")).toHaveTextContent("35.0 s");
  });

  it("con el dato fresco no hay franja que leer", () => {
    arrange(forensics());
    expect(screen.getByTestId("post-event-summary")).not.toHaveTextContent("DATOS RETENIDOS");
  });
});
