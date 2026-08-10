// Tests de la LÓGICA PURA de la cola (spec §4.2 / criterios T-2.06 y T-2.108).
import { BASE_DELAY_MS, MAX_DELAY_MS, retryDelayMs } from "./backoff";
import { canonicalJson } from "./custody";
import {
  blockingRefs,
  dueForDispatch,
  hasLocalCheckin,
  indexById,
  isDue,
  markFailed,
  markRetry,
  markSynced,
  markUploading,
  newQueueItem,
  recoverInterrupted,
  resolveEvidenceIds,
  RETENTION_AFTER_SYNC_MS,
  shouldPurge,
  withPriority,
  type CheckinPayload,
  type DamageReportPayload,
  type EvidencePayload,
  type QueueItem,
} from "./queue";

const PAYLOAD: CheckinPayload = {
  incident_id: "inc-1",
  status: "safe",
  zone_id: "z-1",
  location: null,
  ts_device: "2026-07-16T10:00:00Z",
};

const T0 = 1_800_000_000_000;

function item() {
  return newQueueItem({ kind: "checkin", id: "id-1", payload: PAYLOAD, sha256: "hash-1", now: T0 });
}

function foto(id: string, over: Partial<QueueItem> = {}): QueueItem {
  const payload: EvidencePayload = {
    incident_id: "inc-1",
    uri: `file:///priv/${id}.jpg`,
    content_type: "image/jpeg",
    bytes: 1024,
    ts_device: "2026-07-16T10:00:00Z",
  };
  return {
    ...newQueueItem({ kind: "evidence", id, payload, sha256: `sha-${id}`, now: T0 }),
    ...over,
  } as QueueItem;
}

function reporte(id: string, refs: string[], over: Partial<QueueItem> = {}): QueueItem {
  const payload: DamageReportPayload = {
    incident_id: "inc-1",
    categories: [{ key: "structural", severity: "high" }],
    notes: null,
    zone_id: "z-1",
    evidence_refs: refs,
    ts_device: "2026-07-16T10:00:00Z",
  };
  return {
    ...newQueueItem({ kind: "damage_report", id, payload, sha256: `sha-${id}`, now: T0 + 1 }),
    ...over,
  } as QueueItem;
}

describe("backoff — exponencial con jitter acotado", () => {
  it("crece exponencial y respeta el techo", () => {
    const noJitter = () => 0.5; // factor 1.0
    expect(retryDelayMs(1, noJitter)).toBe(BASE_DELAY_MS);
    expect(retryDelayMs(2, noJitter)).toBe(BASE_DELAY_MS * 2);
    expect(retryDelayMs(4, noJitter)).toBe(BASE_DELAY_MS * 8);
    expect(retryDelayMs(30, noJitter)).toBe(MAX_DELAY_MS);
  });

  it("jitter dentro de [0.5x, 1.5x] y jamás sobre el techo", () => {
    expect(retryDelayMs(1, () => 0)).toBe(BASE_DELAY_MS * 0.5);
    expect(retryDelayMs(1, () => 0.999999)).toBeLessThanOrEqual(BASE_DELAY_MS * 1.5);
    expect(retryDelayMs(30, () => 0.999999)).toBe(MAX_DELAY_MS);
  });
});

describe("transiciones de estado", () => {
  it("nace pending y elegible ya", () => {
    const i = item();
    expect(i.state).toBe("pending");
    expect(isDue(i, T0)).toBe(true);
  });

  it("uploading no es elegible; synced sella synced_at", () => {
    const up = markUploading(item());
    expect(isDue(up, T0 + 1)).toBe(false);
    const ok = markSynced(up, T0 + 5);
    expect(ok.state).toBe("synced");
    expect(ok.synced_at).toBe(T0 + 5);
  });

  it("error recuperable ⇒ pending con backoff FUTURO y attempts+1", () => {
    const r = markRetry(markUploading(item()), T0, "sin red", () => 0.5);
    expect(r.state).toBe("pending");
    expect(r.attempts).toBe(1);
    expect(r.next_attempt_at).toBe(T0 + BASE_DELAY_MS);
    expect(isDue(r, T0)).toBe(false);
    expect(isDue(r, T0 + BASE_DELAY_MS)).toBe(true);
    expect(r.last_error).toBe("sin red");
  });

  it("error NO recuperable ⇒ failed, visible y sin reintento", () => {
    const f = markFailed(markUploading(item()), "HTTP 422");
    expect(f.state).toBe("failed");
    expect(isDue(f, T0 + MAX_DELAY_MS * 10)).toBe(false);
  });

  it("uploading interrumpido (app muerta) se recupera a pending elegible", () => {
    const rec = recoverInterrupted(markUploading(item()));
    expect(rec.state).toBe("pending");
    expect(isDue(rec, T0)).toBe(true);
    // los demás estados quedan intactos (misma referencia)
    const ok = markSynced(item(), T0);
    expect(recoverInterrupted(ok)).toBe(ok);
  });
});

describe("retención — nada se borra hasta synced + 24 h", () => {
  it("synced reciente NO se poda; synced + 24 h sí", () => {
    const ok = markSynced(item(), T0);
    expect(shouldPurge(ok, T0 + RETENTION_AFTER_SYNC_MS - 1)).toBe(false);
    expect(shouldPurge(ok, T0 + RETENTION_AFTER_SYNC_MS + 1)).toBe(true);
  });

  it("pending/failed JAMÁS se podan, sin importar la edad", () => {
    const old = T0 + RETENTION_AFTER_SYNC_MS * 100;
    expect(shouldPurge(item(), old)).toBe(false);
    expect(shouldPurge(markFailed(item(), "x"), old)).toBe(false);
  });
});

describe("hasLocalCheckin — el dato local cuenta, el fallido no", () => {
  it("pending/synced del incidente cuentan; failed y otros incidentes no", () => {
    expect(hasLocalCheckin([item()], "inc-1")).toBe(true);
    expect(hasLocalCheckin([markSynced(item(), T0)], "inc-1")).toBe(true);
    expect(hasLocalCheckin([markFailed(item(), "x")], "inc-1")).toBe(false);
    expect(hasLocalCheckin([item()], "inc-OTRO")).toBe(false);
    expect(hasLocalCheckin([], "inc-1")).toBe(false);
  });

  it("una FOTO del incidente no se cuenta como check-in de vida", () => {
    // Sin el filtro por `kind`, la cola multi-tipo haría creer al ocupante que
    // ya dijo "estoy a salvo" por haber sacado una foto.
    expect(hasLocalCheckin([foto("ev-1")], "inc-1")).toBe(false);
  });
});

describe("canonicalJson — huella estable (cadena de custodia)", () => {
  it("mismo contenido, distinto orden de claves ⇒ misma serialización", () => {
    const a = { b: 1, a: [{ y: 2, x: 1 }], c: null };
    const b = { c: null, a: [{ x: 1, y: 2 }], b: 1 };
    expect(canonicalJson(a)).toBe(canonicalJson(b));
    expect(canonicalJson(a)).toBe('{"a":[{"x":1,"y":2}],"b":1,"c":null}');
  });
});

// ─── [T-2.108] Cola multi-tipo ───────────────────────────────────────────────

describe("dependencias: el reporte espera a SUS fotos", () => {
  it("una foto en vuelo RETIENE al reporte que la referencia", () => {
    const items = [foto("ev-1"), reporte("rep-1", ["ev-1"])];
    const byId = indexById(items);
    expect(blockingRefs(items[1], byId)).toEqual(["ev-1"]);
    expect(dueForDispatch(items, T0 + 10).map((i) => i.id)).toEqual(["ev-1"]);
  });

  it("con la foto ya sincronizada el reporte sale y se liga al evidence_id REAL", () => {
    const subida = markSynced(foto("ev-1"), T0 + 5, "ev-servidor-9");
    const items = [subida, reporte("rep-1", ["ev-1"])];
    expect(dueForDispatch(items, T0 + 10).map((i) => i.id)).toEqual(["rep-1"]);
    expect(resolveEvidenceIds(["ev-1"], indexById(items))).toEqual({
      ids: ["ev-servidor-9"],
      dropped: 0,
    });
  });

  it("una foto FALLIDA no retiene para siempre: el reporte sale y lo declara", () => {
    // Retener el reporte por una foto que ya nunca va a subir sería esconder
    // un daño estructural detrás de un JPEG.
    const rota = markFailed(foto("ev-1"), "HTTP 422");
    const items = [rota, reporte("rep-1", ["ev-1"])];
    expect(blockingRefs(items[1], indexById(items))).toEqual([]);
    expect(resolveEvidenceIds(["ev-1"], indexById(items))).toEqual({ ids: [], dropped: 1 });
  });

  it("una referencia ya podada (24 h) tampoco retiene", () => {
    const items = [reporte("rep-1", ["ev-desaparecida"])];
    expect(blockingRefs(items[0], indexById(items))).toEqual([]);
  });
});

describe("orden de despacho — §2.4: personas atrapadas al frente", () => {
  it("el urgente sale ANTES aunque se haya encolado después", () => {
    const viejo = { ...item(), id: "checkin-viejo", created_at: T0 } as QueueItem;
    const urgente = reporte("rep-urgente", [], { created_at: T0 + 1000, priority: 1 });
    expect(dueForDispatch([viejo, urgente], T0 + 2000).map((i) => i.id)).toEqual([
      "rep-urgente",
      "checkin-viejo",
    ]);
  });

  it("dentro del mismo nivel manda el orden de captura (FIFO)", () => {
    const a = { ...item(), id: "a", created_at: T0 } as QueueItem;
    const b = { ...item(), id: "b", created_at: T0 + 1 } as QueueItem;
    expect(dueForDispatch([b, a], T0 + 10).map((i) => i.id)).toEqual(["a", "b"]);
  });

  it("el backoff sigue mandando sobre la prioridad (no se martillea al servidor)", () => {
    const urgenteEnEspera = reporte("rep-urgente", [], {
      priority: 1,
      attempts: 1,
      next_attempt_at: T0 + 60_000,
    });
    expect(dueForDispatch([urgenteEnEspera, item()], T0 + 10).map((i) => i.id)).toEqual(["id-1"]);
  });

  it("withPriority solo SUBE (una foto ya urgente no se degrada)", () => {
    const f = foto("ev-1");
    expect(withPriority(f, 1).priority).toBe(1);
    expect(withPriority(withPriority(f, 1), 0).priority).toBe(1);
  });
});
