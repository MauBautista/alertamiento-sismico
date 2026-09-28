// Catálogo de referencia (T-1.52): claramente separado del historial del
// tenant, con fuente citada por fila y sin disfrazarse de incidente.

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogEarthquakeOut } from "@takab/sdk";

const mocks = vi.hoisted(() => ({ useCatalog: vi.fn() }));
vi.mock("./useCatalog", () => ({ useCatalog: mocks.useCatalog }));

import CatalogPanel from "./CatalogPanel";

function eq(over: Partial<CatalogEarthquakeOut> = {}): CatalogEarthquakeOut {
  return {
    ref_id: "r-1",
    catalog_key: "SSN-2017-09-19-PUE",
    origin_time: "2017-09-19T18:14:40Z",
    magnitude: 7.1,
    place: "Puebla-Morelos 19S (intraslab)",
    lat: 18.4,
    lon: -98.72,
    depth_km: 57,
    source: "SSN",
    source_ref: "SSN Reporte Especial SSNMX_rep_esp_20170919",
    notes: null,
    ...over,
  };
}

function catalogData(over: Record<string, unknown> = {}) {
  return {
    items: [eq()],
    primeraPagina: [eq()],
    loading: false,
    error: null,
    refetch: vi.fn(),
    hayMas: false,
    cargandoMas: false,
    errorMas: null,
    cargarMas: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  mocks.useCatalog.mockReturnValue(catalogData());
});

describe("CatalogPanel", () => {
  it("etiquetado inconfundible: REFERENCIA · SSN/USGS · no son incidentes del tenant", () => {
    render(<CatalogPanel />);
    expect(screen.getByText("CATÁLOGO DE REFERENCIA · SSN/USGS")).toBeInTheDocument();
    expect(screen.getByText("REFERENCIA")).toBeInTheDocument();
    expect(screen.getByText(/NO SON INCIDENTES DEL TENANT/)).toBeInTheDocument();
  });

  it("colapsado por defecto; al expandir pinta fila con M/fecha/prof/fuente citada", () => {
    render(<CatalogPanel />);
    expect(screen.queryByText("M 7.1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("M 7.1")).toBeInTheDocument();
    expect(screen.getByText("2017-09-19")).toBeInTheDocument();
    expect(screen.getByText("57 km")).toBeInTheDocument();
    expect(screen.getByText("Puebla-Morelos 19S (intraslab)")).toBeInTheDocument();
    const src = screen.getByText("SSN");
    expect(src).toHaveAttribute("title", expect.stringContaining("Reporte Especial"));
    // no se disfraza de incidente: sin SevTag ni estados de incidente
    expect(document.querySelector(".soc-sev")).toBeNull();
  });

  it("error del catálogo: alert con retry (no tumba el historial)", () => {
    mocks.useCatalog.mockReturnValue(catalogData({ error: "GET falló (503)", items: [] }));
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("alert")).toHaveTextContent("GET falló (503)");
  });

  it("catálogo vacío: instrucción honesta de seed", () => {
    mocks.useCatalog.mockReturnValue(catalogData({ items: [] }));
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(/CATÁLOGO SIN SEMBRAR/)).toBeInTheDocument();
  });

  it("[T-9.61] con más páginas hay «CARGAR MÁS» y pide la siguiente", () => {
    const cargarMas = vi.fn();
    mocks.useCatalog.mockReturnValue(catalogData({ hayMas: true, cargarMas }));
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: "CARGAR MÁS" }));
    expect(cargarMas).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("catalog-count")).toHaveTextContent("1 SISMO CARGADO");
  });

  it("[T-9.61] sin más páginas no se ofrece «CARGAR MÁS» y se dice que es el final", () => {
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByRole("button", { name: "CARGAR MÁS" })).toBeNull();
    expect(screen.getByTestId("catalog-count")).toHaveTextContent("FIN DEL CATÁLOGO");
  });

  it("[T-9.61] cargando la siguiente: botón deshabilitado con su rótulo", () => {
    mocks.useCatalog.mockReturnValue(catalogData({ hayMas: true, cargandoMas: true }));
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("button", { name: "CARGANDO…" })).toBeDisabled();
  });

  it("[T-9.61] si falla la siguiente página, lo cargado sigue y el fallo se dice con reintentar", () => {
    const cargarMas = vi.fn();
    mocks.useCatalog.mockReturnValue(
      catalogData({ hayMas: true, errorMas: "GET falló (502)", cargarMas }),
    );
    render(<CatalogPanel />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("M 7.1")).toBeInTheDocument();
    expect(screen.getByTestId("catalog-more-error")).toHaveTextContent("GET falló (502)");
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR CARGAR MÁS" }));
    expect(cargarMas).toHaveBeenCalledTimes(1);
  });
});
