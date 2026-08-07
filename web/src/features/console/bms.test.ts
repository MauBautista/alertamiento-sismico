// groupActions (T-1.50): la traza append-only se agrupa por canal — una fila
// por actuador con el último estado; el design system lo pide así porque un
// incidente SASMEX real repite siren/gas/elevator varias veces.

import { describe, expect, it } from "vitest";

import type { IncidentActionOut } from "@takab/sdk";

import { groupActions } from "./bms";

function action(kind: string, ts: string, id = `${kind}-${ts}`): IncidentActionOut {
  return {
    action_id: id,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts,
    kind,
    actor: "edge:gw-dev-0001",
    payload: {},
  } as IncidentActionOut;
}

describe("groupActions", () => {
  it("agrupa por kind con la acción MÁS RECIENTE al mando (estado/hora/×N)", () => {
    const groups = groupActions([
      action("siren_on", "2026-07-10T03:14:00Z"),
      action("siren_on", "2026-07-10T03:31:00Z"),
      action("siren_on", "2026-07-10T03:20:00Z"),
      action("gas_valve_close", "2026-07-10T03:14:05Z"),
    ]);
    expect(groups).toHaveLength(2);
    const siren = groups.find((g) => g.kind === "siren_on");
    expect(siren?.count).toBe(3);
    expect(siren?.last.ts).toBe("2026-07-10T03:31:00Z");
    expect(siren?.label).toBe("SIRENA");
    expect(siren?.view).toEqual({ state: "ACTIVADA", kind: "critical" });
    // la traza va de más nueva a más vieja (auditoría)
    expect(siren?.trace.map((a) => a.ts)).toEqual([
      "2026-07-10T03:31:00Z",
      "2026-07-10T03:20:00Z",
      "2026-07-10T03:14:00Z",
    ]);
  });

  it("ordena los grupos por recencia de su última acción", () => {
    const groups = groupActions([
      action("gas_valve_close", "2026-07-10T03:10:00Z"),
      action("siren_on", "2026-07-10T03:30:00Z"),
      action("door_release", "2026-07-10T03:20:00Z"),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(["siren_on", "door_release", "gas_valve_close"]);
  });

  it("kind desconocido: etiqueta cruda en mayúsculas y estado neutro (nunca revienta)", () => {
    const groups = groupActions([action("nuevo_kind_x", "2026-07-10T03:00:00Z")]);
    expect(groups[0].label).toBe("NUEVO KIND X");
    expect(groups[0].view).toEqual({ state: "NUEVO_KIND_X", kind: "ok" });
  });

  it("acuses y acciones de operador también agrupan", () => {
    const groups = groupActions([
      action("ack", "2026-07-10T03:35:00Z"),
      action("epicenter_relocate", "2026-07-10T03:36:00Z"),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["EPICENTRO", "ACUSES"]);
  });

  it("lista vacía ⇒ sin grupos", () => {
    expect(groupActions([])).toEqual([]);
  });

  // [T-2.75] Entregado, simulado y no entregado son TRES cosas, y el operador
  // reacciona distinto a cada una: nada / contratar el canal / el proveedor
  // está caído AHORA. Pintarlas iguales es el tablero mentiroso otra vez.
  describe("notificaciones: enviada ≠ simulada ≠ no entregada", () => {
    it("cada desenlace tiene su propia fila, su propia palabra y su propio color", () => {
      const groups = groupActions([
        action("notify_sent", "2026-07-10T03:00:00Z"),
        action("notify_simulated", "2026-07-10T03:00:01Z"),
        action("notify_failed", "2026-07-10T03:00:02Z"),
      ]);
      const byKind = new Map(groups.map((g) => [g.kind, g]));
      expect(byKind.get("notify_sent")?.view).toEqual({ state: "ENVIADA", kind: "ok" });
      expect(byKind.get("notify_simulated")?.view.kind).toBe("warning");
      expect(byKind.get("notify_failed")?.view.kind).toBe("critical");
      // Tres etiquetas distintas: no se funden en una sola fila "NOTIFICACIONES".
      const labels = groups.map((g) => g.label);
      expect(new Set(labels).size).toBe(3);
      // Y ninguna de las dos que NO llegaron dice "ENVIADA".
      expect(byKind.get("notify_simulated")?.view.state).not.toContain("ENVIADA");
      expect(byKind.get("notify_failed")?.view.state).not.toContain("ENVIADA");
    });

    it("la bandera `simulated` del payload MANDA sobre el mapa de kinds", () => {
      // Derivado, no enumerado: el sexto canal que alguien enchufe mañana
      // escribirá un kind que este mapa no conoce. Si el estado saliera del
      // mapa, caería en el fallback `ok` — verde, "todo bien", justo la mentira.
      const futuro = {
        ...action("notify_telegram_algo", "2026-07-10T03:00:00Z"),
        payload: { simulated: true },
      };
      expect(groupActions([futuro])[0].view.kind).toBe("warning");
      expect(groupActions([futuro])[0].view.state).not.toContain("ENVIADA");
    });

    it("un notify_sent legítimo NO se contagia de la bandera", () => {
      const real = {
        ...action("notify_sent", "2026-07-10T03:00:00Z"),
        payload: { simulated: false, deadline_met: true },
      };
      expect(groupActions([real])[0].view).toEqual({ state: "ENVIADA", kind: "ok" });
    });
  });
});
