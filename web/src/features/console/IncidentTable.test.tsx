import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import IncidentTable from "./IncidentTable";
import type { LiveIncident } from "./useLiveIncidents";

const NOW = Date.parse("2026-07-08T10:41:35Z");

function incident(id: string, over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: id,
    tenant_id: "t-1",
    site_id: `s-${id}`,
    event_id: null,
    opened_at: "2026-07-08T10:41:30Z",
    closed_at: null,
    severity: "critical",
    state: "open",
    trigger: "local_threshold",
    max_pga_g: 0.15,
    max_pgv_cms: 4.2,
    ...over,
  };
}

function renderTable(over: Partial<Parameters<typeof IncidentTable>[0]> = {}) {
  const onAck = vi.fn();
  const onSelect = vi.fn();
  render(
    <IncidentTable
      incidents={[incident("a")]}
      siteInfoOf={() => ({ name: "Planta Cholula", coords: "19.0633°N · 98.3014°W" })}
      nowMs={NOW}
      liveStatus="ready"
      operatorLabel="TENANT_ADMIN · SOC"
      selectedId={null}
      onSelect={onSelect}
      canAck
      onAck={onAck}
      {...over}
    />,
  );
  return { onAck, onSelect };
}

describe("IncidentTable", () => {
  it("pinta la fila con sitio, PGA, hora UTC y edad", () => {
    renderTable();
    expect(screen.getByText("Planta Cholula")).toBeInTheDocument();
    expect(screen.getByText("0.150g")).toBeInTheDocument();
    expect(screen.getByText("10:41:30 UTC")).toBeInTheDocument();
    expect(screen.getByText("T+05s")).toBeInTheDocument();
    expect(screen.getByText("1 ACTIVOS")).toBeInTheDocument();
  });

  it("el pill LIVE refleja el estado del WS con honestidad", () => {
    renderTable({ liveStatus: "connecting" });
    expect(screen.getByTestId("live-pill")).toHaveTextContent("SIN LIVE");
  });

  it("clic en la fila selecciona el incidente", () => {
    const { onSelect } = renderTable();
    fireEvent.click(screen.getByText("Planta Cholula"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ incident_id: "a" }));
  });

  it("CONFIRMAR ACUSE es two-step y solo con fila seleccionada", () => {
    const { onAck } = renderTable({ selectedId: "a" });
    const button = screen.getByRole("button", { name: /CONFIRMAR ACUSE/ });
    fireEvent.click(button); // arma
    expect(onAck).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    expect(onAck).toHaveBeenCalledWith("a");
  });

  it("sin allowed_actions.ack_incident el acuse queda deshabilitado", () => {
    const { onAck } = renderTable({ canAck: false, selectedId: "a" });
    const button = screen.getByRole("button", { name: /CONFIRMAR ACUSE/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onAck).not.toHaveBeenCalled();
  });

  it("muestra la identidad real de la sesión (sin selector de turno)", () => {
    renderTable();
    expect(screen.getByTestId("operator-label")).toHaveTextContent("TENANT_ADMIN · SOC");
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});
