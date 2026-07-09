import { describe, expect, it } from "vitest";

import { secondsSince, utcClock, utcStamp } from "./time";

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
