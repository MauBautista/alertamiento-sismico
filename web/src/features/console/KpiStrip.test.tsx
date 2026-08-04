import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import KpiStrip from "./KpiStrip";
import { consoleKpis, type ConsoleKpis } from "./stats";

function kpis(over: Partial<ConsoleKpis> = {}): ConsoleKpis {
  return { ...consoleKpis([], []), ...over };
}

function renderStrip(over: Partial<Parameters<typeof KpiStrip>[0]> = {}) {
  const onToggleHideNoLink = vi.fn();
  render(
    <KpiStrip
      kpis={kpis()}
      shown={0}
      hideNoLink={false}
      onToggleHideNoLink={onToggleHideNoLink}
      {...over}
    />,
  );
  return { onToggleHideNoLink };
}

describe("KpiStrip", () => {
  it("cuenta los cuatro estados de enlace por separado", () => {
    renderStrip({
      kpis: kpis({ stations: 10, operativo: 6, degradado: 2, sinEnlace: 1, sinGabinete: 1 }),
      shown: 10,
    });
    const strip = screen.getByTestId("kpi-strip");
    // SIN ENLACE y SIN GABINETE NO se suman en un solo número: uno manda a
    // revisar una antena y el otro a instalar un gabinete.
    expect(within(strip).getByText("SIN ENLACE").previousSibling).toHaveTextContent("1");
    expect(within(strip).getByText("SIN GABINETE").previousSibling).toHaveTextContent("1");
    expect(within(strip).getByText("OPERATIVO").previousSibling).toHaveTextContent("6");
  });

  it("sin latencia reportada pinta S/D, JAMÁS 0 ms", () => {
    renderStrip({ kpis: kpis({ rttP50Ms: null, rttMaxMs: null, lagMaxS: null }) });
    const strip = screen.getByTestId("kpi-strip");
    expect(within(strip).getAllByText("S/D").length).toBe(3);
    expect(within(strip).queryByText("0 ms")).toBeNull();
  });

  it("con latencia la muestra con unidades", () => {
    renderStrip({ kpis: kpis({ rttP50Ms: 42, rttMaxMs: 310, lagMaxS: 2.4 }) });
    expect(screen.getByText("42 ms")).toBeInTheDocument();
    expect(screen.getByText("310 ms")).toBeInTheDocument();
    expect(screen.getByText("2.4 s")).toBeInTheDocument();
  });

  it("declara el recorte del viewport: MOSTRANDO n DE N", () => {
    renderStrip({ kpis: kpis({ stations: 40 }), shown: 7 });
    expect(screen.getByTestId("kpi-showing")).toHaveTextContent("MOSTRANDO 7 DE 40");
  });

  it("el filtro OCULTAR SIN ENLACE es un toggle explícito y declarado", () => {
    const { onToggleHideNoLink } = renderStrip({ hideNoLink: false });
    const button = screen.getByTestId("hide-no-link");
    expect(button).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(button);
    expect(onToggleHideNoLink).toHaveBeenCalledTimes(1);
  });

  it("SIN MEDICIÓN se cuenta aparte de las bandas medidas", () => {
    renderStrip({ kpis: kpis({ trip: 1, watch: 2, normal: 3, feltDesconocido: 4 }) });
    const strip = screen.getByTestId("kpi-strip");
    expect(within(strip).getByText("SIN MEDICIÓN").previousSibling).toHaveTextContent("4");
    expect(within(strip).getByText("SUPERÓ DISPARO").previousSibling).toHaveTextContent("1");
  });

  it("incidentes: críticos sobre abiertos, sin inventar un total", () => {
    renderStrip({ kpis: kpis({ incidentesAbiertos: 5, incidentesCriticos: 2 }) });
    expect(screen.getByText("2/5")).toBeInTheDocument();
  });
});
