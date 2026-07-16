// Tests de HONESTIDAD de la máquina (spec §4.1 + §2.1-A).
import {
  ALERT_SOURCE_CARRIES_ETA,
  deriveAlertState,
  elapsedSeconds,
  formatElapsed,
  type ServerPhase,
} from "./machine";

const PHASES: ServerPhase[] = ["idle", "alert_active", "shaking_concluded", "reentry_approved"];

describe("deriveAlertState — el servidor manda", () => {
  it.each([
    ["idle", false, "idle"],
    ["idle", true, "idle"],
    ["alert_active", false, "alert_active"],
    ["alert_active", true, "alert_active"],
    ["shaking_concluded", false, "checkin_pending"],
    ["shaking_concluded", true, "reentry_blocked"],
    ["reentry_approved", false, "reentry_approved"],
    ["reentry_approved", true, "reentry_approved"],
  ] as const)("phase=%s, checkin=%s ⇒ %s", (phase, checkin, expected) => {
    expect(deriveAlertState(phase, checkin)).toBe(expected);
  });

  it("NINGÚN camino local produce reentry_approved (solo la fase del servidor)", () => {
    for (const phase of PHASES.filter((p) => p !== "reentry_approved")) {
      for (const checkin of [false, true]) {
        expect(deriveAlertState(phase, checkin)).not.toBe("reentry_approved");
      }
    }
  });

  it("modo prueba del gabinete ⇒ sin incidente ⇒ idle SIEMPRE (garantía server-side)", () => {
    // T-1.67/T-1.69: el edge en prueba suprime la publicación → no hay
    // incidente → el backend sirve phase=idle. La máquina no tiene más
    // insumos (firma de 2 argumentos): no existe "modo prueba" local.
    expect(deriveAlertState("idle", false)).toBe("idle");
    expect(deriveAlertState("idle", true)).toBe("idle");
    expect(deriveAlertState.length).toBe(2);
  });
});

describe("ALERT_SOURCE_CARRIES_ETA — §2.1-A", () => {
  it("es false: el WR-1 entrega un booleano, no hay ETA que mostrar", () => {
    expect(ALERT_SOURCE_CARRIES_ETA).toBe(false);
  });
});

describe("elapsedSeconds — T+ real, jamás negativo", () => {
  const t0 = Date.parse("2026-07-16T10:00:00Z");

  it("cuenta ascendente desde la apertura", () => {
    expect(elapsedSeconds("2026-07-16T10:00:00Z", t0 + 4_000)).toBe(4);
    expect(elapsedSeconds("2026-07-16T10:00:00Z", t0 + 125_500)).toBe(125);
  });

  it("sesgo de reloj del dispositivo ⇒ clamp a 0 (no un cronómetro fantasma)", () => {
    expect(elapsedSeconds("2026-07-16T10:00:00Z", t0 - 30_000)).toBe(0);
  });

  it("timestamp corrupto ⇒ 0 (jamás NaN en pantalla de vida o muerte)", () => {
    expect(elapsedSeconds("no-es-fecha", t0)).toBe(0);
  });
});

describe("formatElapsed — SIEMPRE con signo +, jamás regresivo", () => {
  it.each([
    [0, "T+00s"],
    [4, "T+04s"],
    [59, "T+59s"],
    [60, "T+1m00s"],
    [92, "T+1m32s"],
    [605, "T+10m05s"],
  ])("%d s ⇒ %s", (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected);
  });
});
