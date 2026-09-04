import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { IncidentOut, SeismicEventOut } from "@takab/sdk";

import TriageTable from "./TriageTable";
import type { TriageRow } from "./model";

function incident(over: Partial<IncidentOut> = {}): IncidentOut {
  return {
    incident_id: "11111111-2222-3333-4444-555555555555",
    tenant_id: "t-1",
    site_id: "s-1",
    event_id: "EVT-001",
    opened_at: "2026-08-03T10:00:00Z",
    closed_at: null,
    severity: "warning",
    state: "open",
    trigger: "sasmex",
    max_pga_g: 0.081,
    max_pgv_cms: 3.2,
    ...over,
  } as IncidentOut;
}

function event(over: Partial<SeismicEventOut> = {}): SeismicEventOut {
  return {
    event_id: "EVT-001",
    source: "local_quorum",
    magnitude: null,
    depth_km: null,
    detected_at: "2026-08-03T09:59:50Z",
    epicenter_lat: 19.06,
    epicenter_lon: -98.3,
    meta: {},
    ...over,
  } as SeismicEventOut;
}

function row(over: Partial<TriageRow> = {}): TriageRow {
  return {
    incident: incident(),
    event: event(),
    siteName: "Torre Norte",
    nodeCount: 3,
    ...over,
  };
}

function arrange(rows: TriageRow[] = [row()], selectedId: string | null = null) {
  const onSelect = vi.fn();
  render(<TriageTable rows={rows} selectedId={selectedId} onSelect={onSelect} />);
  return { onSelect };
}

describe("TriageTable [T-2.39]", () => {
  // `aria-selected` en un <tr> es inválido fuera de un role="grid": los lectores de
  // pantalla lo ignoran y la selección deja de anunciarse.
  it("la tabla declara role=grid para que aria-selected sea válido", () => {
    arrange();
    expect(screen.getByRole("grid")).toBeInTheDocument();
  });

  it("marca la fila seleccionada", () => {
    arrange([row()], "11111111-2222-3333-4444-555555555555");
    expect(screen.getByTestId("triage-row")).toHaveAttribute("aria-selected", "true");
  });

  // Antes la fila era un <tr onClick>: con teclado no se podía seleccionar nada.
  it("se puede seleccionar con teclado", () => {
    const { onSelect } = arrange();
    const pick = screen.getByRole("button");
    pick.focus();
    expect(pick).toHaveFocus();
    fireEvent.click(pick);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("el clic en la celda no dispara la selección dos veces", () => {
    const { onSelect } = arrange();
    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  // Los estados de la magnitud: es SIEMPRE null hoy, y un guion se leía como
  // "el dato falló". [T-5.10] El rótulo sale del glosario compartido de
  // procedencia: sin haber consultado a ninguna fuente, el estado es
  // `sin_dato_externo` — que NO es lo mismo que «se consultó y no correlaciona».
  it("sin dato externo lo dice, no un guion", () => {
    arrange();
    expect(screen.getByText("SIN DATO EXTERNO")).toBeInTheDocument();
  });

  it("sin evento asociado dice SIN EVENTO", () => {
    arrange([row({ event: null, incident: incident({ event_id: null }) })]);
    expect(screen.getByText("SIN EVENTO")).toBeInTheDocument();
  });

  // [T-5.10] La cifra externa se pinta SOLO con procedencia completa: fuente y
  // hora de consulta. Sin ellas no es que falte el número — es que no consta de
  // dónde salió, y en la pantalla se leería como una medición NUESTRA.
  it("con magnitud CONFIRMADA por la fuente la muestra", () => {
    arrange([
      row({
        event: event({
          magnitude: 7.1,
          procedencia: "confirmado",
          procedencia_fuente: "SSN",
          procedencia_consultada_en: "2026-09-04T12:00:00Z",
        }),
      }),
    ]);
    expect(screen.getByText("M 7.1")).toBeInTheDocument();
  });

  it("con magnitud pero SIN procedencia NO la muestra", () => {
    arrange([row({ event: event({ magnitude: 7.1 }) })]);
    expect(screen.queryByText("M 7.1")).toBeNull();
    expect(screen.getByText("SIN DATO EXTERNO")).toBeInTheDocument();
  });

  // Un centroide entre estaciones NO es una localización sísmica: presentarlo sin
  // decirlo invita a compararlo con el epicentro del SSN y concluir que la red falló.
  it("el epicentro por quórum se rotula CENTROIDE", () => {
    arrange();
    expect(screen.getByText(/CENTROIDE/)).toBeInTheDocument();
  });

  it("un epicentro de catálogo externo no lleva esa nota", () => {
    arrange([row({ event: event({ source: "sasmex" }) })]);
    expect(screen.queryByText(/CENTROIDE/)).not.toBeInTheDocument();
  });

  it("sin filas no revienta", () => {
    arrange([]);
    expect(screen.queryByTestId("triage-row")).not.toBeInTheDocument();
  });
});
