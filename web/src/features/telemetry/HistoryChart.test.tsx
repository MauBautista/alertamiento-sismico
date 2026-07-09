import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HistoryChart from "./HistoryChart";
import { bucketFor } from "./useSiteMetrics";
import type { HistoryPoint } from "./useSiteMetrics";

const T0 = Date.parse("2026-07-08T10:00:00Z");

const POINTS: HistoryPoint[] = [
  { ts: T0, maxPga: 0.02, maxPgv: 0.2 },
  { ts: T0 + 60_000, maxPga: 0.31, maxPgv: 3.1 },
  { ts: T0 + 120_000, maxPga: 0.05, maxPgv: 0.5 },
];

function renderChart(over: Partial<Parameters<typeof HistoryChart>[0]> = {}) {
  const onPreset = vi.fn();
  render(
    <HistoryChart
      points={POINTS}
      bucket="1m"
      calibrated={true}
      preset="1h"
      onPreset={onPreset}
      {...over}
    />,
  );
  return { onPreset };
}

describe("bucketFor", () => {
  it("hasta 24 h se lee el cagg de 1 minuto", () => {
    expect(bucketFor("1h")).toBe("1m");
    expect(bucketFor("6h")).toBe("1m");
    expect(bucketFor("24h")).toBe("1m");
  });

  it("a 7 días se conmuta a 1 hora (10.080 puntos no caben en 600 px)", () => {
    expect(bucketFor("7d")).toBe("1h");
  });
});

describe("HistoryChart", () => {
  it("dibuja una barra por bucket, no una línea interpolada", () => {
    renderChart();
    const chart = screen.getByTestId("history-chart");
    expect(chart.querySelectorAll("rect")).toHaveLength(POINTS.length);
    expect(chart.querySelector("path")).toBeNull();
  });

  it("rotula el bucket vigente y el máximo del rango", () => {
    renderChart();
    expect(screen.getByText(/BUCKET 1M/)).toBeInTheDocument();
    expect(screen.getByText(/máx 0\.310 g/)).toBeInTheDocument();
  });

  it("el preset activo se marca y al pulsar otro se notifica", () => {
    const { onPreset } = renderChart();
    expect(screen.getByRole("button", { name: "1H" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "7D" }));
    expect(onPreset).toHaveBeenCalledWith("7d");
  });

  it("sin calibrar avisa y usa unidades relativas", () => {
    renderChart({ calibrated: false });
    expect(screen.getByTestId("not-calibrated-badge")).toBeInTheDocument();
    expect(screen.getByText(/máx 0\.310 rel\./)).toBeInTheDocument();
  });

  it("sin puntos no inventa extremos temporales", () => {
    renderChart({ points: [] });
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByTestId("history-chart").querySelectorAll("rect")).toHaveLength(0);
  });
});
