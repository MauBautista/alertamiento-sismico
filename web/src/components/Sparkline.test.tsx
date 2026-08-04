import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Sparkline, { segmentsOf } from "./Sparkline";

describe("Sparkline · el hueco se ve, no se interpola [T-2.38]", () => {
  it("una serie continua es un solo trazo", () => {
    expect(segmentsOf([1, 2, 3, 4], 60, 18)).toHaveLength(1);
  });

  // Lo que hace cualquier librería de charts: unir los extremos del hueco con una
  // recta. Esa recta se lee como "todo estuvo bien" justo donde no hubo dato.
  it("un null PARTE la serie en dos trazos", () => {
    const paths = segmentsOf([1, 2, null, 4, 5], 60, 18);
    expect(paths).toHaveLength(2);
    expect(paths.every((p) => p.startsWith("M"))).toBe(true);
  });

  it("un punto suelto entre huecos no dibuja nada (no hay tendencia de uno)", () => {
    expect(segmentsOf([null, 3, null], 60, 18)).toEqual([]);
  });

  it("una serie constante no produce NaN", () => {
    const [path] = segmentsOf([5, 5, 5], 60, 18);
    expect(path).not.toMatch(/NaN/);
  });

  it("con menos de dos puntos pinta S/D, jamás una línea plana", () => {
    render(<Sparkline values={[null, null]} label="RTT" />);
    expect(screen.queryByTestId("sparkline")).not.toBeInTheDocument();
    expect(screen.getByText("S/D")).toBeInTheDocument();
  });

  it("serie vacía también es S/D", () => {
    render(<Sparkline values={[]} label="RTT" />);
    expect(screen.getByText("S/D")).toBeInTheDocument();
  });

  it("lleva nombre accesible: es información, no decoración", () => {
    render(<Sparkline values={[1, 2, 3]} label="RTT MQTT p95 de Torre Norte" />);
    expect(screen.getByRole("img", { name: /RTT MQTT p95 de Torre Norte/ })).toBeInTheDocument();
  });
});
