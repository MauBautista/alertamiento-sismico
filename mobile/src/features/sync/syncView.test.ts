// 2.5 — resumen honesto de la cola: pendiente = no synced; el badge de cifrado
// solo afirma AES-256 si SQLCipher se verificó.
import type { QueueItem, QueueItemState } from "@/offline/queue";

import {
  countByState,
  encryptionBadge,
  formatBytes,
  pendingBytes,
  pendingCount,
  syncItemView,
} from "./syncView";

function item(state: QueueItemState, over: Record<string, unknown> = {}): QueueItem {
  return {
    id: `id-${state}`,
    kind: "checkin",
    payload: {},
    sha256: "h",
    state,
    attempts: 0,
    next_attempt_at: 0,
    created_at: 1,
    synced_at: null,
    last_error: null,
    priority: 0,
    server_id: null,
    ...over,
  } as QueueItem;
}

function foto(state: QueueItemState, bytes: number, id = `ev-${state}`): QueueItem {
  return item(state, {
    id,
    kind: "evidence",
    payload: {
      incident_id: "inc-1",
      uri: `file:///priv/${id}.jpg`,
      content_type: "image/jpeg",
      bytes,
      ts_device: "t",
    },
  });
}

function reporte(refs: string[], over: Record<string, unknown> = {}): QueueItem {
  return item("pending", {
    id: "rep-1",
    kind: "damage_report",
    payload: {
      incident_id: "inc-1",
      categories: [],
      notes: null,
      zone_id: null,
      evidence_refs: refs,
      ts_device: "t",
    },
    ...over,
  });
}

describe("countByState / pendingCount", () => {
  it("cuenta por estado; pendiente = todo lo no synced", () => {
    const items = [item("pending"), item("uploading"), item("synced"), item("failed")];
    expect(countByState(items)).toEqual({ pending: 1, uploading: 1, synced: 1, failed: 1 });
    expect(pendingCount(items)).toBe(3); // synced no cuenta
  });
});

describe("syncItemView", () => {
  it("fallido muestra el error y es reintentable", () => {
    const v = syncItemView(item("failed", { last_error: "HTTP 422" }), 0);
    expect(v.stateLabel).toBe("FALLÓ");
    expect(v.tone).toBe("crit");
    expect(v.detail).toBe("HTTP 422");
    expect(v.retriable).toBe(true);
  });

  it("pending con backoff muestra intentos y segundos al reintento", () => {
    const v = syncItemView(item("pending", { attempts: 2, next_attempt_at: 10_000 }), 3_000);
    expect(v.detail).toMatch(/2 intento\(s\) · reintenta en 7 s/);
    expect(v.retriable).toBe(false);
  });

  it("synced es ok y no reintentable", () => {
    const v = syncItemView(item("synced"), 0);
    expect(v.tone).toBe("ok");
    expect(v.retriable).toBe(false);
  });
});

// ─── [T-2.108] La cola multi-tipo, con nombre y tamaño ───────────────────────

describe("la cola SE NOMBRA a sí misma (§7 · 2.5)", () => {
  it("cada tipo tiene un título que una persona entiende", () => {
    // Antes solo `checkin` tenía etiqueta: una foto se habría pintado como el
    // literal "evidence" en la pantalla que promete transparencia.
    expect(syncItemView(item("pending"), 0).title).toBe("Check-in de vida");
    expect(syncItemView(foto("pending", 100), 0).title).toBe("Foto forense");
    expect(syncItemView(reporte([]), 0).title).toBe("Reporte de daños");
  });

  it("una foto pendiente declara cuánto pesa; el reporte urgente, su prioridad", () => {
    expect(syncItemView(foto("pending", 2 * 1024 * 1024), 0).detail).toBe("2.0 MB");
    expect(syncItemView(reporte([], { priority: 1 }), 0).urgent).toBe(true);
    expect(syncItemView(reporte([]), 0).urgent).toBe(false);
  });

  it("el reporte retenido por sus fotos EXPLICA por qué espera", () => {
    const items = [foto("pending", 10, "ev-1"), reporte(["ev-1"])];
    expect(syncItemView(items[1], 0, items).detail).toBe(
      "Espera 1 foto(s) para conservar el enlace forense",
    );
  });
});

describe("tamaño pendiente", () => {
  it("suma SOLO las fotos que faltan por subir", () => {
    const items = [foto("pending", 1500, "a"), foto("synced", 9_000_000, "b"), item("pending")];
    expect(pendingBytes(items)).toBe(1500);
    expect(pendingCount(items)).toBe(2);
  });

  it("se lee en unidades humanas", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("encryptionBadge — honesto (§4.2)", () => {
  it("afirma AES-256 SOLO con SQLCipher verificado", () => {
    expect(encryptionBadge({ active: true, cipher: "SQLCipher 4.6.1 (AES-256)" })).toEqual({
      label: "CIFRADO · SQLCipher 4.6.1 (AES-256)",
      secure: true,
    });
  });

  it("sin cifrado verificado ⇒ lo declara, jamás finge", () => {
    expect(encryptionBadge({ active: false, cipher: null }).secure).toBe(false);
    expect(encryptionBadge(null).secure).toBe(false);
  });
});
