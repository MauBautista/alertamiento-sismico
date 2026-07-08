import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import UpsGauge from "./UpsGauge";

describe("UpsGauge", () => {
  it("line ⇒ RED ELÉCTRICA con % y fill ok", () => {
    const { container } = render(<UpsGauge powerStatus="line" batteryPct={100} />);
    expect(screen.getByText("RED ELÉCTRICA")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(container.querySelector(".fleet-ups__fill--ok")).not.toBeNull();
  });

  it("battery ⇒ EN BATERÍA; nivel medio pinta warn", () => {
    const { container } = render(<UpsGauge powerStatus="battery" batteryPct={72} />);
    expect(screen.getByText("EN BATERÍA")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(container.querySelector(".fleet-ups__fill--warn")).not.toBeNull();
  });

  it("nivel crítico (<40) pinta crit", () => {
    const { container } = render(<UpsGauge powerStatus="battery" batteryPct={34} />);
    expect(container.querySelector(".fleet-ups__fill--crit")).not.toBeNull();
  });

  it("estado desconocido o sin dato ⇒ UPS · S/D y — (no finge 0%)", () => {
    render(<UpsGauge powerStatus={null} batteryPct={null} />);
    expect(screen.getByText("UPS · S/D")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("clampa el porcentaje a [0,100]", () => {
    render(<UpsGauge powerStatus="line" batteryPct={140} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });
});
