// Tests de la LÓGICA PURA de la cola (spec §4.2 / criterios T-2.06).
import { BASE_DELAY_MS, MAX_DELAY_MS, retryDelayMs } from "./backoff";
import { canonicalJson } from "./custody";
import {
  hasLocalCheckin,
  isDue,
  markFailed,
  markRetry,
  markSynced,
  markUploading,
  newQueueItem,
  recoverInterrupted,
  RETENTION_AFTER_SYNC_MS,
  shouldPurge,
  type CheckinPayload,
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
  return newQueueItem("id-1", PAYLOAD, "hash-1", T0);
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
});

describe("canonicalJson — huella estable (cadena de custodia)", () => {
  it("mismo contenido, distinto orden de claves ⇒ misma serialización", () => {
    const a = { b: 1, a: [{ y: 2, x: 1 }], c: null };
    const b = { c: null, a: [{ x: 1, y: 2 }], b: 1 };
    expect(canonicalJson(a)).toBe(canonicalJson(b));
    expect(canonicalJson(a)).toBe('{"a":[{"x":1,"y":2}],"b":1,"c":null}');
  });
});
