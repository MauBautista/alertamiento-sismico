import { describe, expect, it } from "vitest";

import { secondsSince, utcClock } from "./time";

describe("utcClock", () => {
  it("formatea epoch ms como HH:MM:SS UTC", () => {
    expect(utcClock(0)).toBe("00:00:00");
    expect(utcClock(Date.UTC(2026, 6, 8, 10, 41, 30))).toBe("10:41:30");
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
