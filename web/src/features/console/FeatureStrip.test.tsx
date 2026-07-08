import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeatureStrip from "./FeatureStrip";
import type { FeaturePoint } from "./useSiteFeatures";

function point(ts: number, pga: number | null, clipping = false): FeaturePoint {
  return { ts, pga, pgv: null, stalta: null, clipping };
}

describe("FeatureStrip", () => {
  it("traza un path con los puntos y marca el clipping", () => {
    render(
      <FeatureStrip points={[point(1000, 0.01), point(2000, 0.2, true), point(3000, 0.05)]} />,
    );
    const svg = screen.getByTestId("feature-strip");
    expect(svg.querySelector("path")).not.toBeNull();
    expect(screen.getAllByTestId("clipping-tick")).toHaveLength(1);
  });

  it("sin puntos renderiza la retícula sin path (el empty lo maneja StateFrame)", () => {
    render(<FeatureStrip points={[]} />);
    expect(screen.getByTestId("feature-strip").querySelector("path")).toBeNull();
  });
});
