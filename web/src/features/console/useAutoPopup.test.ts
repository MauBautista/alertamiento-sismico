import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { staltaSustained, useAutoPopup } from "./useAutoPopup";
import type { FeaturePoint } from "./useSiteFeatures";

function point(ts: number, stalta: number | null): FeaturePoint {
  return { ts, pga: null, pgv: null, stalta, clipping: false };
}

describe("staltaSustained (puro)", () => {
  it("exige el umbral en las 2 muestras consecutivas (criterio #4)", () => {
    expect(staltaSustained([point(1, 4.0)])).toBe(false); // 1 muestra no basta
    expect(staltaSustained([point(1, 4.0), point(2, 3.4)])).toBe(false);
    expect(staltaSustained([point(1, 3.4), point(2, 4.0), point(3, 3.6)])).toBe(true);
    expect(staltaSustained([point(1, null), point(2, 4.0)])).toBe(false);
  });
});

describe("useAutoPopup", () => {
  it("dispara UNA vez por episodio y se rearma al bajar del umbral", () => {
    const onOpen = vi.fn();
    const { rerender } = renderHook(
      ({ points }: { points: FeaturePoint[] }) => useAutoPopup("s-1", points, onOpen),
      { initialProps: { points: [point(1, 1.0)] } },
    );
    expect(onOpen).not.toHaveBeenCalled();

    rerender({ points: [point(1, 1.0), point(2, 4.0)] });
    expect(onOpen).not.toHaveBeenCalled(); // solo 1 muestra sobre umbral

    rerender({ points: [point(1, 1.0), point(2, 4.0), point(3, 4.2)] });
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith("s-1");

    rerender({ points: [point(2, 4.0), point(3, 4.2), point(4, 4.5)] });
    expect(onOpen).toHaveBeenCalledTimes(1); // latcheado: no re-dispara

    rerender({ points: [point(3, 4.2), point(4, 4.5), point(5, 1.0)] });
    rerender({ points: [point(4, 4.5), point(5, 1.0), point(6, 4.0)] });
    rerender({ points: [point(5, 1.0), point(6, 4.0), point(7, 4.1)] });
    expect(onOpen).toHaveBeenCalledTimes(2); // episodio nuevo tras el rearme
  });

  it("sin sitio enfocado no dispara", () => {
    const onOpen = vi.fn();
    renderHook(() => useAutoPopup(null, [point(1, 9.0), point(2, 9.0)], onOpen));
    expect(onOpen).not.toHaveBeenCalled();
  });
});
