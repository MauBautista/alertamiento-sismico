// Derivaciones del simulacro (T-2.48). Puras y testeables: el reporte de acuse
// es evidencia de cumplimiento, no puede depender del render.

import { describe, expect, it } from "vitest";

import type { DrillOut, DrillSiteOut } from "@takab/sdk";

import {
  ARMED_EXPIRE_MS,
  ARMED_LEAD_MS,
  ackLabel,
  armedPhase,
  drillAckReport,
  drillSiteAck,
  nextArmedDrill,
} from "./drill";

function site(over: Partial<DrillSiteOut> = {}): DrillSiteOut {
  return {
    site_id: "s-1",
    site_name: "Sitio 1",
    command_id: "c-1",
    command_status: "acked",
    ack: { ok: true },
    commandable: true,
    ...over,
  };
}

function drill(over: Partial<DrillOut> = {}): DrillOut {
  return {
    drill_id: "d-1",
    tenant_id: "t-1",
    initiated_by: "u-1",
    note: null,
    duration_s: 300,
    started_at: "2026-08-04T18:00:00Z",
    stopped_at: null,
    stop_reason: null,
    scheduled_at: null,
    active: true,
    sites: [],
    ...over,
  };
}

describe("drillSiteAck", () => {
  it("acuse real del gabinete", () => {
    expect(drillSiteAck(site(), drill())).toBe("acked");
  });

  it("comando emitido sin respuesta todavía = pending", () => {
    expect(drillSiteAck(site({ command_status: "pending", ack: null }), drill())).toBe("pending");
  });

  it("rechazado o vencido = rejected (el gabinete NO lo ejecutó)", () => {
    expect(drillSiteAck(site({ command_status: "rejected", ack: null }), drill())).toBe("rejected");
    expect(drillSiteAck(site({ command_status: "expired", ack: null }), drill())).toBe("rejected");
  });

  it("SIN GABINETE COMANDABLE es su propio estado, no un 'sin acuse'", () => {
    const s = site({ command_id: null, command_status: null, ack: null, commandable: false });
    expect(drillSiteAck(s, drill())).toBe("no_gateway");
    expect(ackLabel("no_gateway")).toBe("SIN GABINETE COMANDABLE");
    expect(ackLabel("no_gateway")).not.toBe(ackLabel("not_sent"));
  });

  it("el comando que NO llegó a emitirse se distingue del que no acusó", () => {
    const s = site({ command_id: null, command_status: null, ack: null, commandable: true });
    expect(drillSiteAck(s, drill())).toBe("not_sent");
    expect(ackLabel("not_sent")).toBe("SIN COMANDO EMITIDO");
  });

  it("en una agenda pendiente el sitio está PROGRAMADO, no 'sin acuse'", () => {
    const agenda = drill({
      scheduled_at: "2026-08-05T18:00:00Z",
      active: false,
      sites: [],
    });
    const s = site({ command_id: null, command_status: null, ack: null });
    expect(drillSiteAck(s, agenda)).toBe("scheduled");
  });

  it("una agenda CANCELADA no deja sitios 'programados' colgando", () => {
    const cancelled = drill({
      scheduled_at: "2026-08-05T18:00:00Z",
      stopped_at: "2026-08-04T19:00:00Z",
      stop_reason: "cancelled",
      active: false,
    });
    const s = site({ command_id: null, command_status: null, ack: null, commandable: true });
    expect(drillSiteAck(s, cancelled)).toBe("not_sent");
  });
});

describe("drillAckReport", () => {
  it("N/M cuenta SOLO los sitios a los que se les mandó el comando", () => {
    const report = drillAckReport(
      drill({
        sites: [
          site({ site_id: "a", command_id: "c-a", command_status: "acked" }),
          site({ site_id: "b", command_id: "c-b", command_status: "pending", ack: null }),
          site({
            site_id: "c",
            command_id: null,
            command_status: null,
            ack: null,
            commandable: false,
          }),
        ],
      }),
    );
    // El sitio sin gabinete NO infla el denominador: decir "1/3 ACUSADOS"
    // haría creer que dos edificios ignoraron el simulacro.
    expect(report.commanded).toBe(2);
    expect(report.acked).toBe(1);
    expect(report.noGateway).toBe(1);
    expect(report.total).toBe(3);
  });

  it("un sitio sin gabinete NUNCA se cuenta como sin acuse", () => {
    const report = drillAckReport(
      drill({
        sites: [
          site({
            site_id: "c",
            command_id: null,
            command_status: null,
            ack: null,
            commandable: false,
          }),
        ],
      }),
    );
    expect(report.commanded).toBe(0);
    expect(report.acked).toBe(0);
    expect(report.pending).toBe(0);
    expect(report.notSent).toBe(0);
    expect(report.noGateway).toBe(1);
  });

  it("el fallo de emisión se cuenta aparte del rechazo del gabinete", () => {
    const report = drillAckReport(
      drill({
        sites: [
          site({ site_id: "a", command_id: null, command_status: null, ack: null }),
          site({ site_id: "b", command_status: "rejected", ack: null }),
        ],
      }),
    );
    expect(report.notSent).toBe(1);
    expect(report.rejected).toBe(1);
    expect(report.commanded).toBe(1);
  });

  it("simulacro sin sitios: todo a cero, sin dividir por cero", () => {
    const report = drillAckReport(drill({ sites: [] }));
    expect(report).toMatchObject({ total: 0, commanded: 0, acked: 0 });
  });
});

describe("armedPhase / nextArmedDrill", () => {
  const at = Date.parse("2026-08-04T18:00:00Z");
  const agenda = drill({
    drill_id: "ag-1",
    scheduled_at: "2026-08-04T18:00:00Z",
    active: false,
  });

  it("fuera de la ventana de armado no hay banner", () => {
    expect(armedPhase(agenda, at - ARMED_LEAD_MS - 1000)).toBe("waiting");
    expect(nextArmedDrill([agenda], at - ARMED_LEAD_MS - 1000)).toBeNull();
  });

  it("a T−15 min el simulacro queda ARMADO", () => {
    expect(armedPhase(agenda, at - ARMED_LEAD_MS + 1000)).toBe("armed");
    expect(nextArmedDrill([agenda], at - 60_000)?.drill_id).toBe("ag-1");
  });

  it("a T−0 el botón queda precargado (due)", () => {
    expect(armedPhase(agenda, at)).toBe("due");
    expect(armedPhase(agenda, at + 60_000)).toBe("due");
  });

  it("pasada la ventana de vigencia deja de anunciarse (ya es historial)", () => {
    expect(armedPhase(agenda, at + ARMED_EXPIRE_MS + 1000)).toBe("expired");
    expect(nextArmedDrill([agenda], at + ARMED_EXPIRE_MS + 1000)).toBeNull();
  });

  it("una agenda cancelada o ya ejecutada NO se anuncia como armada", () => {
    const cancelled = { ...agenda, stopped_at: "2026-08-04T17:50:00Z", stop_reason: "cancelled" };
    const executed = { ...agenda, stopped_at: "2026-08-04T17:50:00Z", stop_reason: "executed" };
    expect(nextArmedDrill([cancelled], at - 60_000)).toBeNull();
    expect(nextArmedDrill([executed], at - 60_000)).toBeNull();
  });

  it("un simulacro ya ejecutado (sin scheduled_at) nunca es una agenda", () => {
    expect(nextArmedDrill([drill()], at)).toBeNull();
  });

  it("con varias agendas gana la más próxima", () => {
    const later = { ...agenda, drill_id: "ag-2", scheduled_at: "2026-08-04T18:10:00Z" };
    expect(nextArmedDrill([later, agenda], at - 60_000)?.drill_id).toBe("ag-1");
  });
});
