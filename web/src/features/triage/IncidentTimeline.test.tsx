// [T-2.75] La bitácora del incidente es lo que un perito lee para reconstruir
// lo ocurrido. Si una notificación que nadie recibió se lee ahí como
// "NOTIFICACIÓN ENVIADA", la evidencia miente — y `incident_actions` es
// justamente la tabla exenta de poda por retención.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import IncidentTimeline, { kindLabel, type TimelineAction } from "./IncidentTimeline";

function action(kind: string, payload: Record<string, unknown> = {}): TimelineAction {
  return {
    action_id: `a-${kind}`,
    ts: "2026-07-10T03:14:00Z",
    kind,
    actor: "system:notify:sms:cascade",
    payload,
  };
}

function renderTimeline(data: TimelineAction[]) {
  render(<IncidentTimeline actions={{ data, loading: false, error: null }} onRetry={vi.fn()} />);
}

describe("kindLabel · enviada ≠ simulada ≠ no entregada", () => {
  it("da tres verbos DISTINTOS, y solo uno dice que se envió", () => {
    const sent = kindLabel(action("notify_sent"));
    const simulated = kindLabel(action("notify_simulated", { simulated: true }));
    const failed = kindLabel(action("notify_failed"));
    expect(new Set([sent, simulated, failed]).size).toBe(3);
    expect(sent).toContain("ENVIADA");
    expect(simulated).not.toContain("ENVIADA");
    expect(failed).not.toContain("ENVIADA");
  });

  it("delata la simulación por el PAYLOAD, no por una lista de kinds", () => {
    // El kind es inventado a propósito: representa el canal que todavía no
    // existe. Una lista de rótulos se queda ciega ante el siguiente; la
    // bandera que el servidor ya escribe, no.
    const label = kindLabel(action("notify_canal_del_futuro", { simulated: true }));
    expect(label).toMatch(/SIMULAD/);
    expect(label).not.toContain("ENVIADA");
  });

  it("no contagia a una acción sin bandera", () => {
    expect(kindLabel(action("ack"))).toBe("ACUSE DE OPERADOR");
    expect(kindLabel(action("notify_sent", { simulated: false }))).not.toMatch(/SIMULAD/);
  });
});

describe("IncidentTimeline", () => {
  it("pinta la fila simulada con marca propia, no como una acción cualquiera", () => {
    renderTimeline([action("notify_simulated", { simulated: true })]);
    const row = screen.getByText(/SIMULAD/);
    expect(row.className).toContain("timeline__kind--undelivered");
  });

  it("una notificación entregada NO lleva la marca", () => {
    renderTimeline([action("notify_sent", { deadline_met: true })]);
    const row = screen.getByText("NOTIFICACIÓN ENVIADA");
    expect(row.className).not.toContain("timeline__kind--undelivered");
  });
});
