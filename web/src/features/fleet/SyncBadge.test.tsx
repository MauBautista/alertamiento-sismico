import { describe, expect, it } from "vitest";

import type { GatewayConfigStateOut } from "@takab/sdk";

import { syncView } from "./SyncBadge";

function state(over: Partial<GatewayConfigStateOut> = {}): GatewayConfigStateOut {
  return {
    gateway_id: "g-1",
    version: 7,
    published_at: "2026-08-03T10:00:00Z",
    sig_fingerprint: "a1b2c3d4e5f6",
    in_sync: true,
    has_edge_config: true,
    is_syncable: true,
    ...over,
  };
}

describe("syncView · qué le pasa a la config firmada [T-2.37]", () => {
  it("sincronizado muestra la versión que tiene el gabinete", () => {
    expect(syncView(state())).toMatchObject({ label: "SINCRONIZADO v7", tone: "ok" });
  });

  it("pendiente: hay algo que publicar y el worker lo hará", () => {
    expect(syncView(state({ in_sync: false }))).toMatchObject({
      label: "PENDIENTE",
      tone: "warn",
    });
  });

  // Estos dos se veían idénticos a PENDIENTE y el operador esperaba en vano.
  it("sin iot_thing dice NO SINCRONIZABLE, no 'pendiente para siempre'", () => {
    const view = syncView(state({ is_syncable: false, in_sync: false }));
    expect(view.label).toBe("NO SINCRONIZABLE");
    expect(view.tone).toBe("crit");
    expect(view.title).toMatch(/iot_thing/);
  });

  it("sin bloque edge en el rule_set lo dice y apunta a Multi-Tenant", () => {
    const view = syncView(state({ has_edge_config: false, in_sync: false }));
    expect(view.label).toBe("SIN CONFIG EDGE");
    expect(view.title).toMatch(/Multi-Tenant/);
  });

  // [B3] `has_edge_config` es el espejo del gate de publicación del worker
  // (`base IS NOT NULL`), no "el rule_set activo trae bloque edge". El worker
  // recompone la base desde el último doc publicado, así que un rule_set
  // inactivo NO basta para que no haya nada que mandar. El título tenía que
  // nombrar las DOS causas o el operador iba a Multi-Tenant a arreglar algo que
  // no era el problema.
  it("el título nombra las DOS causas de que no haya nada que publicar", () => {
    const view = syncView(state({ has_edge_config: false, in_sync: false }));
    expect(view.title).toMatch(/edge/i);
    expect(view.title).toMatch(/anterior|previo/i);
  });

  // Regla de oro 7: si la consulta falla, NO se asume que esté sincronizado.
  it("sin dato dice S/D y no inventa un estado", () => {
    const view = syncView(undefined);
    expect(view.label).toBe("SYNC S/D");
    expect(view.tone).toBe("idle");
  });

  it("la prioridad es no-sincronizable > sin-config > in_sync", () => {
    // Un gabinete retirado puede traer in_sync=true de una publicación vieja: lo que
    // importa es que ya no recibirá nada más.
    expect(syncView(state({ is_syncable: false })).label).toBe("NO SINCRONIZABLE");
  });
});
