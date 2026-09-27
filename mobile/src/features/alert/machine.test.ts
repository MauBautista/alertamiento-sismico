// Tests de HONESTIDAD de la máquina (spec §4.1 + §2.1-A).
import {
  ALERT_SOURCE_CARRIES_ETA,
  deriveAlertState,
  elapsedSeconds,
  esFaseConocida,
  faseEnReposo,
  formatElapsed,
  type ServerPhase,
} from "./machine";

const PHASES: ServerPhase[] = [
  "idle",
  "alert_active",
  "shaking_concluded",
  "reentry_approved",
  "building_alarm",
  "reentry_blocked",
];

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
    // [T-2.106] Alarma del inmueble: no hay sismo, así que el check-in de vida
    // no la modifica (no hay de qué dar parte).
    ["building_alarm", false, "building_alarm"],
    ["building_alarm", true, "building_alarm"],
    // [T-9.04] Bloqueo PERSISTENTE del servidor: el incidente ya cerró y lo que
    // sobrevive es el veredicto. Reutiliza el estado de la app —el reingreso
    // está bloqueado, diga lo que diga el check-in propio (ya no hay incidente
    // abierto al que reportarse).
    ["reentry_blocked", false, "reentry_blocked"],
    ["reentry_blocked", true, "reentry_blocked"],
  ] as const)("phase=%s, checkin=%s ⇒ %s", (phase, checkin, expected) => {
    expect(deriveAlertState(phase, checkin)).toBe(expected);
  });

  it("[T-2.106] una alarma del inmueble JAMÁS se convierte en alert_active", () => {
    // Criterio 3 en el borde del cliente: aunque el servidor es quien decide, la
    // máquina tampoco puede ASCENDER una alarma de inmueble a crisis sísmica.
    for (const checkin of [false, true]) {
      expect(deriveAlertState("building_alarm", checkin)).not.toBe("alert_active");
    }
  });

  it("[T-2.106] ningún camino local produce building_alarm sin que el servidor lo diga", () => {
    for (const phase of PHASES.filter((p) => p !== "building_alarm")) {
      for (const checkin of [false, true]) {
        expect(deriveAlertState(phase, checkin)).not.toBe("building_alarm");
      }
    }
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

describe("[T-9.06] una fase que esta versión de la app NO conoce", () => {
  // Una APK vieja frente a un servidor nuevo: el `switch` no tenía `default`, así
  // que una fase desconocida devolvía `undefined` —ni `idle` ni nada—, y cada
  // pantalla que compara `state === …` se quedaba muda sin decir por qué.
  let warn: jest.SpyInstance;
  beforeEach(() => {
    warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
  });
  afterEach(() => {
    warn.mockRestore();
  });

  it("cae a idle, jamás a undefined", () => {
    const futura = "fase_del_futuro" as unknown as ServerPhase;
    expect(deriveAlertState(futura, false)).toBe("idle");
    expect(deriveAlertState(futura, true)).toBe("idle");
  });

  it("y lo DICE en el registro, con la fase que no reconoció", () => {
    deriveAlertState("fase_del_registro" as unknown as ServerPhase, false);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.join(" "))).toMatch(/fase_del_registro/);
  });

  it("UNA vez por fase: re-renderizar o sondear no repite el aviso", () => {
    const repetida = "fase_repetida" as unknown as ServerPhase;
    for (let i = 0; i < 5; i += 1) {
      deriveAlertState(repetida, false);
    }
    deriveAlertState("otra_fase_nueva" as unknown as ServerPhase, false);
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it("esFaseConocida: las del contrato sí, una inventada no", () => {
    for (const phase of PHASES) {
      expect(esFaseConocida(phase)).toBe(true);
    }
    expect(esFaseConocida("fase_del_futuro")).toBe(false);
    expect(esFaseConocida("toString")).toBe(false);
  });

  it("una fase conocida no ensucia el registro", () => {
    for (const phase of PHASES) {
      deriveAlertState(phase, false);
    }
    expect(warn).not.toHaveBeenCalled();
  });

  it("una fase desconocida JAMÁS asciende a crisis ni autoriza el reingreso", () => {
    const futura = "evacuacion_v2" as unknown as ServerPhase;
    for (const checkin of [false, true]) {
      const s = deriveAlertState(futura, checkin);
      expect(s).not.toBe("alert_active");
      expect(s).not.toBe("reentry_approved");
    }
  });
});

describe("[T-9.04] faseEnReposo — el ritmo del sondeo", () => {
  it("idle y el bloqueo persistente sondean en reposo (duran días)", () => {
    expect(faseEnReposo("idle")).toBe(true);
    expect(faseEnReposo("reentry_blocked")).toBe(true);
  });

  it("lo sísmico vivo, el reingreso autorizado y la alarma del inmueble, no", () => {
    for (const phase of [
      "alert_active",
      "shaking_concluded",
      "reentry_approved",
      "building_alarm",
    ] as const) {
      expect(faseEnReposo(phase)).toBe(false);
    }
  });

  it("una fase desconocida sondea DEPRISA: ante la duda, se pregunta más", () => {
    expect(faseEnReposo("fase_del_futuro" as unknown as ServerPhase)).toBe(false);
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
