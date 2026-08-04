import { describe, expect, it } from "vitest";

import { inspectionMatrix, inspectionPriority } from "./priority";
import type { TriageRow } from "./model";

describe("inspectionPriority · sacudida medida × criticidad [T-2.40]", () => {
  it("sacudida fuerte en inmueble crítico ⇒ inspección inmediata", () => {
    expect(inspectionPriority(0.12, "critical").level).toBe("rojo");
    expect(inspectionPriority(0.12, "high").level).toBe("rojo");
  });

  it("sacudida fuerte en inmueble normal ⇒ prioritaria, no inmediata", () => {
    expect(inspectionPriority(0.12, "medium").level).toBe("naranja");
  });

  it("sacudida moderada en inmueble crítico sube de nivel", () => {
    expect(inspectionPriority(0.05, "critical").level).toBe("naranja");
    expect(inspectionPriority(0.05, "low").level).toBe("amarillo");
  });

  it("sacudida leve no genera prioridad", () => {
    expect(inspectionPriority(0.001, "critical").level).toBe("verde");
  });

  // El caso que más importa: un hospital cuyo sensor estaba mudo NO puede pintarse
  // de verde. "No midió" y "no se sacudió" son cosas distintas.
  it("sin PGA el nivel es GRIS, jamás verde", () => {
    expect(inspectionPriority(null, "critical").level).toBe("gris");
    expect(inspectionPriority(undefined, "low").level).toBe("gris");
  });

  it("cada nivel explica QUÉ combinación lo produjo", () => {
    expect(inspectionPriority(0.12, "critical").why).toMatch(/criticidad alta/);
    expect(inspectionPriority(null, "critical").why).toMatch(/no reportó/);
  });

  it("una criticidad desconocida se trata como no crítica, no como crítica", () => {
    expect(inspectionPriority(0.12, null).level).toBe("naranja");
    expect(inspectionPriority(0.12, "lo-que-sea").level).toBe("naranja");
  });
});

function row(id: string, siteId: string, pga: number | null, eventId: string | null): TriageRow {
  return {
    incident: {
      incident_id: id,
      site_id: siteId,
      event_id: eventId,
      max_pga_g: pga,
    } as TriageRow["incident"],
    event: null,
    siteName: `Sitio ${siteId}`,
    nodeCount: null,
  };
}

describe("inspectionMatrix", () => {
  const ROWS = [
    row("i-1", "s-1", 0.001, "EVT-1"),
    row("i-2", "s-2", 0.15, "EVT-1"),
    row("i-3", "s-3", null, "EVT-1"),
    row("i-4", "s-4", 0.99, "EVT-OTRO"),
  ];
  const critical = (siteId: string) => (siteId === "s-2" ? "critical" : "low");

  it("solo incluye los sitios del MISMO evento", () => {
    const rows = inspectionMatrix(ROWS, "EVT-1", critical);
    expect(rows.map((r) => r.incidentId)).not.toContain("i-4");
    expect(rows).toHaveLength(3);
  });

  it("ordena por urgencia y pone lo DESCONOCIDO antes que lo sano", () => {
    const rows = inspectionMatrix(ROWS, "EVT-1", critical);
    expect(rows.map((r) => r.incidentId)).toEqual(["i-2", "i-3", "i-1"]);
  });

  it("sin evento no hay matriz: no se comparan incidentes de sismos distintos", () => {
    expect(inspectionMatrix(ROWS, null, critical)).toEqual([]);
  });

  it("adjunta la banda de sacudida legible de cada sitio", () => {
    const rows = inspectionMatrix(ROWS, "EVT-1", critical);
    expect(rows.find((r) => r.incidentId === "i-3")?.feltLabel).toBe("SIN MEDICIÓN");
  });
});
