import { describe, expect, it } from "vitest";

import { MIN_SCALE, clippingXs, pathOf, scaleOf, timeTicks, yOf } from "./svgScale";
import type { Box } from "./svgScale";

const BOX: Box = { width: 100, height: 50, top: 0, bottom: 50 };

describe("scaleOf", () => {
  it("nunca baja del piso: un micro-tremor no debe verse como un sismo", () => {
    expect(scaleOf([0.001, 0.002])).toBe(MIN_SCALE);
  });

  it("usa el máximo real cuando supera el piso", () => {
    expect(scaleOf([0.01, 0.3, 0.2])).toBe(0.3);
  });

  it("ignora los huecos", () => {
    expect(scaleOf([null, 0.2, null])).toBe(0.2);
    expect(scaleOf([null, null])).toBe(MIN_SCALE);
  });
});

describe("yOf", () => {
  it("cero va a la base y el máximo al techo", () => {
    expect(yOf(0, 1, BOX)).toBe(50);
    expect(yOf(1, 1, BOX)).toBe(0);
  });

  it("un hueco se ancla a la base, no al techo", () => {
    expect(yOf(null, 1, BOX)).toBe(50);
  });

  it("un valor por encima de la escala se recorta, no se sale de la caja", () => {
    expect(yOf(5, 1, BOX)).toBe(0);
  });
});

describe("pathOf", () => {
  it("con menos de dos puntos no dibuja nada", () => {
    expect(pathOf([], 1, BOX)).toBe("");
    expect(pathOf([0.5], 1, BOX)).toBe("");
  });

  it("reparte los puntos por todo el ancho", () => {
    const d = pathOf([0, 1, 0], 1, BOX);
    expect(d.startsWith("M 0.0")).toBe(true);
    expect(d).toContain("L 50.0 0.0"); // el pico, al centro y arriba
    expect(d.endsWith("L 100.0 50.0")).toBe(true);
  });
});

describe("clippingXs", () => {
  it("marca solo los índices clipeados", () => {
    expect(clippingXs([false, true, false], 100)).toEqual([50]);
  });

  it("sin serie no hay marcas", () => {
    expect(clippingXs([true], 100)).toEqual([]);
  });
});

describe("timeTicks", () => {
  it("sin al menos dos instantes no hay eje", () => {
    expect(timeTicks([], 100)).toEqual([]);
    expect(timeTicks([1000], 100)).toEqual([]);
  });

  it("el último instante siempre se rotula (es el 'ahora' de la traza)", () => {
    const ts = [0, 1, 2, 3, 4, 5, 6];
    const ticks = timeTicks(ts, 600);
    expect(ticks[0].x).toBe(0);
    expect(ticks[ticks.length - 1].ts).toBe(6);
    expect(ticks[ticks.length - 1].x).toBe(600);
  });

  it("no repite el último tick cuando ya cae en el borde", () => {
    const ticks = timeTicks([0, 1, 2, 3, 4], 100, 5);
    expect(ticks.filter((t) => t.ts === 4)).toHaveLength(1);
  });
});
