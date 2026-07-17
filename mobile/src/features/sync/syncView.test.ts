// 2.5 — resumen honesto de la cola: pendiente = no synced; el badge de cifrado
// solo afirma AES-256 si SQLCipher se verificó.
import type { QueueItem, QueueItemState } from "@/offline/queue";

import { countByState, encryptionBadge, pendingCount, syncItemView } from "./syncView";

function item(state: QueueItemState, over: Partial<QueueItem> = {}): QueueItem {
  return {
    id: `id-${state}`,
    kind: "checkin",
    payload: {} as never,
    sha256: "h",
    state,
    attempts: 0,
    next_attempt_at: 0,
    created_at: 1,
    synced_at: null,
    last_error: null,
    ...over,
  };
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
