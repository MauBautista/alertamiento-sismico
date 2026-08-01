// [T-2.28] ComparePanel: cifras honestas, rótulo maestro y estados.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CatalogEarthquakeOut, MapSiteState } from "@takab/sdk";

vi.mock("maplibre-gl", () => ({ default: { Map: vi.fn() } }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import ComparePanel, { MASTER_LABEL, NO_MEASURED_NOTE } from "./ComparePanel";

const QUAKE_19S: CatalogEarthquakeOut = {
  ref_id: "r-19s",
  catalog_key: "SSN-2017-09-19-PUE",
  magnitude: 7.1,
  depth_km: 57,
  lat: 18.4,
  lon: -98.72,
  origin_time: "2017-09-19T18:14:00Z",
  place: "Axochiapan, Morelos",
  source: "SSN",
  source_ref: "SSN reporte especial",
  notes: null,
};

const SITES: MapSiteState[] = [
  { site_id: "s-puebla", name: "Hospital Puebla", lat: 19.0414, lon: -98.2063 } as MapSiteState,
  { site_id: "s-cdmx", name: "Corporativo CDMX", lat: 19.4326, lon: -99.1332 } as MapSiteState,
];

describe("ComparePanel", () => {
  it("muestra distancias, arribo P, PGA estimados y los rótulos honestos", () => {
    render(
      <ComparePanel quake={QUAKE_19S} sites={SITES} initialSiteId="s-puebla" onClose={vi.fn()} />,
    );
    expect(screen.getByText("DISTANCIA EPICENTRAL")).toBeInTheDocument();
    expect(screen.getByText("DISTANCIA HIPOCENTRAL")).toBeInTheDocument();
    expect(screen.getByText("ARRIBO P TEÓRICO")).toBeInTheDocument();
    expect(screen.getByText("PGA EST. EPICENTRO")).toBeInTheDocument();
    expect(screen.getByText("PGA EST. ESTACIÓN")).toBeInTheDocument();
    expect(screen.getByText(MASTER_LABEL)).toBeInTheDocument();
    expect(screen.getByTestId("compare-no-measured")).toHaveTextContent(NO_MEASURED_NOTE);
    expect(screen.getByTestId("compare-chart")).toBeInTheDocument();
    // Axochiapan → Puebla ≈ 90 km: la cifra vive en el <dd> de la epicentral.
    expect(screen.getByText(/^9\d km [A-Z]{1,3}$/)).toBeInTheDocument();
  });

  it("cambiar de estación recalcula la distancia", () => {
    render(
      <ComparePanel quake={QUAKE_19S} sites={SITES} initialSiteId="s-puebla" onClose={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("ESTACIÓN / SITIO A COMPARAR"), {
      target: { value: "s-cdmx" },
    });
    // Axochiapan → CDMX ≈ 120 km; solo la EPICENTRAL lleva rumbo — sin ambigüedad
    // con la hipocentral, que también cae en 1xx km.
    expect(screen.getByText(/^1[12]\d km [A-Z]{1,3}$/)).toBeInTheDocument();
  });

  it("sin profundidad lo declara y degrada la hipocentral", () => {
    render(
      <ComparePanel
        quake={{ ...QUAKE_19S, depth_km: null }}
        sites={SITES}
        initialSiteId="s-puebla"
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/SIN PROFUNDIDAD REPORTADA/)).toBeInTheDocument();
  });

  it("sin sitios con coordenadas: estado vacío honesto", () => {
    render(<ComparePanel quake={QUAKE_19S} sites={[]} initialSiteId={null} onClose={vi.fn()} />);
    expect(screen.getByText("SIN SITIOS CON COORDENADAS EN EL TENANT")).toBeInTheDocument();
    expect(screen.getByText(MASTER_LABEL)).toBeInTheDocument();
  });
});
