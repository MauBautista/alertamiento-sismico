import { describe, expect, it } from "vitest";

import { ageLabel, secondsSince, utcClock, utcStamp } from "./time";

describe("utcClock", () => {
  it("formatea epoch ms como HH:MM:SS UTC", () => {
    expect(utcClock(0)).toBe("00:00:00");
    expect(utcClock(Date.UTC(2026, 6, 8, 10, 41, 30))).toBe("10:41:30");
  });
});

describe("utcStamp", () => {
  it("formatea epoch ms como YYYY-MM-DD · HH:MM UTC", () => {
    expect(utcStamp(Date.UTC(2026, 6, 8, 10, 41, 30))).toBe("2026-07-08 · 10:41");
  });

  it("no aplica la zona local: el 1 de enero a las 00:30 UTC sigue siendo día 1", () => {
    expect(utcStamp(Date.UTC(2026, 0, 1, 0, 30, 0))).toBe("2026-01-01 · 00:30");
  });
});

describe("secondsSince", () => {
  it("devuelve segundos enteros transcurridos", () => {
    const t0 = Date.UTC(2026, 6, 8, 10, 0, 0);
    expect(secondsSince(t0, t0 + 2500)).toBe(2);
  });

  it("nunca es negativo (reloj adelantado del dato)", () => {
    expect(secondsSince(1000, 0)).toBe(0);
  });
});

describe("ageLabel", () => {
  it("da la EDAD del dato, no su hora: segundos, minutos, horas y días", () => {
    expect(ageLabel(0)).toBe("0 s");
    expect(ageLabel(59)).toBe("59 s");
    expect(ageLabel(60)).toBe("1 min");
    expect(ageLabel(3599)).toBe("59 min");
    expect(ageLabel(3600)).toBe("1 h");
    expect(ageLabel(86_399)).toBe("23 h");
    expect(ageLabel(86_400)).toBe("1 d");
    expect(ageLabel(21 * 86_400)).toBe("21 d");
  });

  it("sin dato es S/D, jamás 0 s (un cero se lee como 'recién visto')", () => {
    expect(ageLabel(null)).toBe("S/D");
    expect(ageLabel(undefined)).toBe("S/D");
  });

  it("un reloj adelantado no produce edades negativas", () => {
    expect(ageLabel(-5)).toBe("0 s");
  });

  it("no enumera umbrales: cualquier magnitud cae en su unidad", () => {
    // Derivado, no una lista de casos: 1 000 días siguen siendo días.
    expect(ageLabel(1000 * 86_400)).toBe("1000 d");
  });
});
