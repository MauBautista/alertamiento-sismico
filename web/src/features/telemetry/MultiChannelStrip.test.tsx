import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MultiChannelStrip from "./MultiChannelStrip";
import type { ChannelTrace } from "./useSiteChannels";

const T0 = Date.parse("2026-07-08T10:00:00Z");

function trace(channel: string, over: Partial<ChannelTrace> = {}): ChannelTrace {
  return {
    channel,
    ts: [T0, T0 + 1000, T0 + 2000],
    pga: [0.01, 0.2, 0.05],
    pgv: [0.1, 2.0, 0.5],
    clipping: [false, false, false],
    ...over,
  };
}

describe("MultiChannelStrip", () => {
  it("pinta una traza por canal", () => {
    render(
      <MultiChannelStrip
        channels={[trace("EHZ"), trace("ENE"), trace("ENN"), trace("ENZ")]}
        calibrated={true}
      />,
    );
    for (const ch of ["EHZ", "ENE", "ENN", "ENZ"]) {
      expect(screen.getByTestId(`trace-${ch}`)).toBeInTheDocument();
    }
  });

  it("un canal ausente no se pinta plano: su ausencia es la información", () => {
    render(<MultiChannelStrip channels={[trace("EHZ")]} calibrated={true} />);
    expect(screen.getByTestId("trace-EHZ")).toBeInTheDocument();
    expect(screen.queryByTestId("trace-ENZ")).toBeNull();
  });

  it("EHZ es velocidad y EN* aceleración: cada uno con su unidad", () => {
    render(<MultiChannelStrip channels={[trace("EHZ"), trace("ENZ")]} calibrated={true} />);
    // El geófono rotula su escala en cm/s; el acelerómetro, en g.
    expect(screen.getByTestId("trace-EHZ")).toHaveTextContent("cm/s");
    expect(screen.getByTestId("trace-ENZ")).toHaveTextContent("g");
  });

  it("sin calibrar, ninguna traza promete unidades físicas", () => {
    render(<MultiChannelStrip channels={[trace("EHZ"), trace("ENZ")]} calibrated={false} />);
    expect(screen.getByTestId("trace-EHZ")).toHaveTextContent("rel.");
    expect(screen.getByTestId("trace-ENZ")).toHaveTextContent("rel.");
    expect(screen.getByTestId("trace-EHZ")).not.toHaveTextContent("cm/s");
  });

  it("marca el clipping en su canal", () => {
    render(
      <MultiChannelStrip
        channels={[trace("ENZ", { clipping: [false, true, false] })]}
        calibrated={true}
      />,
    );
    expect(screen.getAllByTestId("clipping-tick")).toHaveLength(1);
  });

  it("sin canales no hay eje temporal que dibujar", () => {
    render(<MultiChannelStrip channels={[]} calibrated={undefined} />);
    expect(screen.queryByTestId("time-axis")).toBeNull();
  });

  it("con datos hay eje temporal en UTC", () => {
    render(<MultiChannelStrip channels={[trace("EHZ")]} calibrated={true} />);
    expect(screen.getByTestId("time-axis")).toHaveTextContent("10:00:00");
  });
});
