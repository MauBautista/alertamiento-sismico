// [T-7.20] La tarjeta del epicentro: la cifra NUNCA va sin quién la sostiene.
//
// Lo que fija, por orden de lo que costaría equivocarse:
//
// 1. **La magnitud solo se pinta si la procedencia lo autoriza** (`T-5.10`). Una
//    cifra sin procedencia se lee como propia, y TAKAB no calcula magnitudes.
// 2. **Y cuando no se pinta, se dice por qué** — nunca un hueco: un hueco se lee
//    como «no pasó nada», que es lo contrario de «no lo sé».
// 3. **La fecha del sismo REAL está en la línea.** Un epicentro de 2017 sin ella
//    se lee como un sismo de hoy.
// 4. **Sin reproducción no hay tarjeta**, ni un marco vacío: casi ningún
//    incidente es una reproducción, y un «SIN REPRODUCCIÓN» permanente en el
//    muro enseña al operador a no leer esa esquina.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ReproduccionOut } from "@takab/sdk";
import EpicentroCard, { fechaDelSismo, lineaDelEpicentro } from "./EpicentroCard";
import type { ReproduccionData } from "./useReproduccion";

function datos(): ReproduccionOut {
  return {
    incident_id: "i-1",
    event_id: "EVT-REP-1",
    catalog_key: "USGS-2017-09-19-PUE",
    magnitude: 7.1,
    lat: 18.5499,
    lon: -98.4887,
    depth_km: 48,
    t0_real: "2017-09-19T18:14:38Z",
    t0_demo: "2026-09-15T12:00:00Z",
    place: "Puebla-Morelos 19S (intraslab)",
    catalog_source: "USGS",
    review_status: "confirmado",
    v_p_km_s: 6.928203230275509,
    v_s_km_s: 4,
    arrivals: [],
  };
}

function hook(over: Partial<ReproduccionData> = {}): ReproduccionData {
  return { data: datos(), loading: false, error: false, refetch: vi.fn(), ...over };
}

describe("fechaDelSismo · la fecha del sismo REAL, sin hora", () => {
  it("formatea en UTC y sin hora: mezclar la hora de 2017 con la de hoy confunde", () => {
    expect(fechaDelSismo("2017-09-19T18:14:38Z")).toBe("19-09-2017");
    expect(fechaDelSismo("1985-09-19T13:17:47Z")).toBe("19-09-1985");
  });

  it("una fecha ilegible se DECLARA en vez de pintar `Invalid Date`", () => {
    expect(fechaDelSismo("no es una fecha")).toBe("FECHA NO LEGIBLE");
  });
});

describe("lineaDelEpicentro · la cifra no va sin quién la sostiene", () => {
  it("con la fuente confirmando, la línea entera", () => {
    expect(
      lineaDelEpicentro({
        t0_real: "2017-09-19T18:14:38Z",
        magnitude: 7.1,
        review_status: "confirmado",
        catalog_source: "USGS",
      }),
    ).toBe("EPICENTRO · REPRODUCCIÓN 19-09-2017 · M7.1 · CONFIRMADO POR LA FUENTE · USGS");
  });

  it("PRELIMINAR sí pinta la cifra, pero avisa de que puede cambiar", () => {
    const linea = lineaDelEpicentro({
      t0_real: "2017-09-19T18:14:38Z",
      magnitude: 7.1,
      review_status: "preliminar",
      catalog_source: "SSN",
    });
    expect(linea).toContain("M7.1");
    expect(linea).toContain("PUEDE CAMBIAR");
  });

  it("SIN procedencia no se pinta la cifra — y se dice por qué", () => {
    const linea = lineaDelEpicentro({
      t0_real: "2017-09-19T18:14:38Z",
      magnitude: 7.1,
      review_status: null,
      catalog_source: null,
    });
    expect(linea).not.toContain("M7.1");
    expect(linea).toContain("SIN DATO EXTERNO");
  });

  it("y sin magnitud tampoco se inventa una, aunque la fuente confirme", () => {
    const linea = lineaDelEpicentro({
      t0_real: "2017-09-19T18:14:38Z",
      magnitude: null,
      review_status: "confirmado",
      catalog_source: "USGS",
    });
    expect(linea).not.toMatch(/M\d/);
    expect(linea).toContain("CONFIRMADO POR LA FUENTE");
  });
});

describe("EpicentroCard · cuándo existe", () => {
  it("con reproducción pinta la tarjeta y se revela", () => {
    render(<EpicentroCard reproduccion={hook()} />);
    const card = screen.getByTestId("epicentro-card");
    expect(card.className).toContain("soc-reveal");
    expect(card.textContent).toContain("REPRODUCCIÓN 19-09-2017");
    expect(card.textContent).toContain("M7.1");
    expect(card.textContent).toContain("USGS");
    expect(card.textContent).toContain("Puebla-Morelos");
  });

  it("sin reproducción NO hay tarjeta, ni un marco vacío", () => {
    const { container } = render(<EpicentroCard reproduccion={hook({ data: null })} />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByText(/SIN REPRODUCCIÓN/)).toBeNull();
  });

  it("sin lugar en el catálogo lo declara en vez de dejar el hueco", () => {
    const sinLugar = { ...datos(), place: null };
    render(<EpicentroCard reproduccion={{ ...hook(), data: sinLugar }} />);
    expect(screen.getByTestId("epicentro-card").textContent).toContain("SIN LUGAR EN EL CATÁLOGO");
  });
});
