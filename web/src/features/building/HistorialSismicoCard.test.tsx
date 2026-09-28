// [T-9.66 · D-46] La tarjeta «HISTORIAL SÍSMICO DEL INMUEBLE»: lo que MIDIÓ el
// gabinete y lo que el catálogo ESTIMA que ahí se sintió, en una sola lista por
// fecha, sin confundir una cosa con la otra.
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectFourStates, type UiState } from "../../test-utils/states";
import { colorDeMmi } from "../console/escalaSismos";
import type { EventoHistorial, HistorialSismicoData } from "./useHistorialSismico";

const mocks = vi.hoisted(() => ({ useHistorialSismico: vi.fn() }));
vi.mock("./useHistorialSismico", async () => ({
  ...(await vi.importActual<typeof import("./useHistorialSismico")>("./useHistorialSismico")),
  useHistorialSismico: mocks.useHistorialSismico,
}));

import HistorialSismicoCard from "./HistorialSismicoCard";
import { HISTORIAL_STALE_MS } from "./useHistorialSismico";

const INCIDENTE: EventoHistorial = {
  tipo: "incidente",
  incident_id: "i-7",
  opened_at: "2026-09-10T08:00:00Z",
  severity: "critical",
  estado: "closed",
  clasificacion: "real",
  pga_medida_g: 0.1234,
  trigger: "sasmex",
};

const SISMO_NUEVO: EventoHistorial = {
  tipo: "sismo",
  origin_time: "2026-09-20T12:00:00Z",
  magnitude: 6.2,
  place: "12 km al S de Pinotepa, Oax.",
  dist_km: 181.6,
  mmi_estimada: 4.4,
  mmi_romano: "IV",
  usgs_url: "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
};

const SISMO_VIEJO: EventoHistorial = {
  tipo: "sismo",
  origin_time: "2026-01-02T03:04:05Z",
  magnitude: 5.1,
  place: "Costa de Guerrero",
  dist_km: 250,
  mmi_estimada: 3.1,
  mmi_romano: "III",
  usgs_url: null,
};

function datos(over: Partial<HistorialSismicoData> = {}): HistorialSismicoData {
  return {
    // Desordenados a propósito: la tarjeta ordena por fecha, no confía en el orden.
    eventos: [SISMO_VIEJO, INCIDENTE, SISMO_NUEVO],
    atribucion: "Catálogo: USGS ComCat · MMI estimada con Wald et al. (1999)",
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function ui(canTriage = true) {
  return (
    <MemoryRouter>
      <HistorialSismicoCard siteId="s-1" canTriage={canTriage} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mocks.useHistorialSismico.mockReturnValue(datos());
});

describe("HistorialSismicoCard", () => {
  it("consulta el historial DEL SITIO y se titula como tal", () => {
    render(ui());
    expect(mocks.useHistorialSismico).toHaveBeenCalledWith("s-1");
    expect(screen.getByRole("heading", { name: /HISTORIAL SÍSMICO DEL INMUEBLE/ })).toBeVisible();
  });

  it("mezcla incidentes y sismos por fecha, el más reciente primero", () => {
    render(ui());
    const filas = screen.getAllByTestId(/^historial-(incidente|sismo)$/);
    expect(filas.map((f) => f.getAttribute("data-testid"))).toEqual([
      "historial-sismo",
      "historial-incidente",
      "historial-sismo",
    ]);
    expect(filas[0]).toHaveTextContent("M 6.2");
    expect(filas[2]).toHaveTextContent("M 5.1");
  });

  it("el incidente dice lo que MIDIÓ: severidad, estado, clasificación, PGA medida y enlace al triage", () => {
    render(ui());
    const fila = screen.getByTestId("historial-incidente");
    expect(fila).toHaveTextContent("CERRADO");
    expect(fila).toHaveTextContent("REAL");
    expect(fila).toHaveTextContent("PGA MEDIDA 0.123 g");
    expect(fila.querySelector(".soc-sev")).not.toBeNull();
    expect(within(fila).getByRole("link")).toHaveAttribute("href", "/triage?incident=i-7");
  });

  it("sin clasificar y sin PGA no se inventa nada", () => {
    mocks.useHistorialSismico.mockReturnValue(
      datos({ eventos: [{ ...INCIDENTE, clasificacion: null, pga_medida_g: null }] }),
    );
    render(ui());
    const fila = screen.getByTestId("historial-incidente");
    expect(fila).toHaveTextContent("SIN CLASIFICAR");
    expect(fila).toHaveTextContent("PGA MEDIDA —");
  });

  it("sin la ruta de triage, el incidente no enlaza", () => {
    render(ui(false));
    expect(within(screen.getByTestId("historial-incidente")).queryByRole("link")).toBeNull();
  });

  it("el sismo dice que su MMI es ESTIMADA, con distancia, color de la escala y enlace a USGS", () => {
    render(ui());
    const fila = screen.getAllByTestId("historial-sismo")[0];
    expect(fila).toHaveTextContent("12 km al S de Pinotepa, Oax.");
    expect(fila).toHaveTextContent("182 km");
    expect(fila).toHaveTextContent("MMI ESTIMADA IV");
    const chip = within(fila).getByTestId("historial-mmi");
    expect(chip).toHaveStyle({ background: colorDeMmi(4.4) as string });
    const usgs = within(fila).getByRole("link", { name: /USGS/ });
    expect(usgs).toHaveAttribute("href", SISMO_NUEVO.usgs_url as string);
    expect(usgs).toHaveAttribute("target", "_blank");
    expect(usgs).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("un sismo sin página de USGS no pinta un enlace roto", () => {
    render(ui());
    const viejo = screen.getAllByTestId("historial-sismo")[1];
    expect(within(viejo).queryByRole("link")).toBeNull();
  });

  it("cita la atribución del servidor", () => {
    render(ui());
    expect(screen.getByTestId("historial-atribucion")).toHaveTextContent("USGS ComCat");
  });

  it("no hay magnitud preliminar ni cuenta regresiva (CLAUDE.md §8)", () => {
    render(ui());
    expect(document.body.textContent).not.toMatch(/PRELIMINAR|T-MINUS|SEGUNDOS PARA/i);
  });

  it("los cuatro estados (regla de oro 7)", () => {
    expectFourStates((state: UiState) => {
      mocks.useHistorialSismico.mockReturnValue(
        datos({
          loading: state === "loading",
          error: state === "error" ? "GET falló (503)" : null,
          eventos: state === "stale" ? [INCIDENTE] : [],
          dataUpdatedAt: state === "stale" ? Date.now() - HISTORIAL_STALE_MS - 1_000 : Date.now(),
        }),
      );
      return ui();
    });
  });

  it("vacío honesto: dice la ventana y el umbral de lo que se habría sentido", () => {
    mocks.useHistorialSismico.mockReturnValue(datos({ eventos: [] }));
    render(ui());
    expect(screen.getByTestId("historial-card")).toHaveTextContent(
      /SIN INCIDENTES NI SISMOS SENTIDOS \(MMI ESTIMADA ≥ III\) EN 365 DÍAS/,
    );
  });
});
