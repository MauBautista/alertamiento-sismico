/**
 * [T-7.05 · C-4] DONDE EL ALTA TERMINA, EMPIEZA EL CAMINO A MONITOREO.
 *
 * El censo de flujos de `T-7.04` cronometró el alta completa en 8 clics desde el wall
 * y midió que el octavo —la pestaña Monitoreo— aterrizaba en una consola sin nada
 * seleccionado: `fila_seleccionada: null`, «MOSTRANDO 61 DE 61». La estación recién
 * dada de alta había que buscarla entre los pins, un clic más y con el cliente
 * delante. `/console?sitio=<site_id>` (T-6.14) la abre ya seleccionada.
 *
 * Lo que se mide aquí es el DESTINO del enlace, que es lo único que puede romperse en
 * silencio: un enlace presente pero apuntando a `/console` a secas, o al sitio
 * equivocado, deja el defecto igual y ningún barrido visual lo vería.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { SiteOut } from "@takab/sdk";

import HardwareForm from "./HardwareForm";

const CHOLULA: SiteOut = {
  site_id: "s-cholula",
  tenant_id: "t-1",
  code: "CHL-A",
  name: "Planta Cholula",
  timezone: "America/Mexico_City",
  criticality: "high",
  lat: 19.06,
  lon: -98.3,
  address: null,
  building_type: null,
  status: "active",
  row_version: "8421",
  created_at: "2026-01-01T00:00:00Z",
};

/** El OTRO sitio: dos hrefs distintos es lo que prueba que sale de la prop. */
const ANGELOPOLIS: SiteOut = {
  ...CHOLULA,
  site_id: "s-angelopolis",
  code: "PUE-B",
  name: "Torre Angelópolis",
};

function pintar(site: SiteOut) {
  return render(
    <MemoryRouter>
      <HardwareForm
        site={site}
        existing={[]}
        submitting={false}
        error={null}
        onCreateGateway={vi.fn()}
        onCreateSensor={vi.fn()}
        onDone={vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe("[T-7.05 · C-4] el alta de hardware lleva a Monitoreo con ESTA estación abierta", () => {
  it("el enlace apunta a la ficha del sitio que se está dando de alta, no a otro", () => {
    // Los dos identificadores son DISTINTOS a propósito: con el mismo literal en los
    // dos sitios, la aserción pasaría también con el enlace cableado a una constante
    // o al primer sitio de la lista, que es el defecto que puede aparecer.
    expect(CHOLULA.site_id).not.toBe(ANGELOPOLIS.site_id);

    const { rerender } = pintar(CHOLULA);
    expect(screen.getByTestId("hardware-ver-en-monitoreo")).toHaveAttribute(
      "href",
      "/console?sitio=s-cholula",
    );

    rerender(
      <MemoryRouter>
        <HardwareForm
          site={ANGELOPOLIS}
          existing={[]}
          submitting={false}
          error={null}
          onCreateGateway={vi.fn()}
          onCreateSensor={vi.fn()}
          onDone={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hardware-ver-en-monitoreo")).toHaveAttribute(
      "href",
      "/console?sitio=s-angelopolis",
    );
  });

  it("vive en la fila de acciones finales, junto a VOLVER, y no entre los campos", () => {
    // El sitio importa: en el acuse del gabinete el mismo enlace era una salida de un
    // solo sentido que se llevaba los UUID del `edge.env` (`GatewayAcuse.test.tsx`).
    pintar(CHOLULA);
    const acciones = screen.getByTestId("hardware-formactions");
    expect(within(acciones).getByTestId("hardware-ver-en-monitoreo")).toBeInTheDocument();
    expect(within(acciones).getByRole("button", { name: "VOLVER" })).toBeInTheDocument();
    expect(screen.getByTestId("hardware-ver-en-monitoreo").closest("fieldset")).toBeNull();
  });

  it("el rótulo no promete un foco en el mapa que la consola no da", () => {
    // `?sitio=` abre la FICHA lateral; `MapPanel` no recibe sitio seleccionado alguno,
    // así que el pin no se centra ni se resalta (`features/console/MapPanel.tsx`,
    // `MapPanelProps`). Un rótulo que dijera «VER EN EL MAPA» prometería lo que la
    // pantalla de destino no cumple. Cuando el mapa aprenda a enfocar, este test es
    // el sitio donde consta que el rótulo puede volver a hablar de mapa.
    pintar(CHOLULA);
    const enlace = screen.getByTestId("hardware-ver-en-monitoreo");
    expect(enlace).toHaveTextContent("VER LA ESTACIÓN EN MONITOREO");
    expect(enlace.textContent).not.toMatch(/MAPA/);
  });
});
