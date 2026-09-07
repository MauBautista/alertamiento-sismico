// [T-6.04] Un nombre de sitio lleva su cinta DEMO si —y sólo si— el sitio es simulado.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SiteLabel from "./SiteLabel";

describe("SiteLabel", () => {
  it("un sitio del seed simulado sale con la cinta, con su explicación en el title", () => {
    render(<SiteLabel name="Sitio Sim 001 Puebla" code="site-sim-001" />);
    expect(screen.getByText("Sitio Sim 001 Puebla")).toBeInTheDocument();
    const cinta = screen.getByTestId("site-demo");
    expect(cinta).toHaveTextContent("DEMO");
    expect(cinta).toHaveAttribute("title", "Dato de demostración: este sitio no existe");
  });

  it("un sitio real sale SIN cinta: rotular de demo un edificio con gente dentro es peor", () => {
    render(<SiteLabel name="Planta Cholula" code="site-cholula-a" />);
    expect(screen.getByText("Planta Cholula")).toBeInTheDocument();
    expect(screen.queryByTestId("site-demo")).toBeNull();
  });

  it("sin código no inventa marca en ningún sentido", () => {
    render(<SiteLabel name="SITIO abcdef12" code={null} />);
    expect(screen.queryByTestId("site-demo")).toBeNull();
  });

  it("el serial de un gabinete simulado también marca (gw-sim-0001)", () => {
    render(<SiteLabel name="Torre" code="site-real" serial="gw-sim-0001" />);
    expect(screen.getByTestId("site-demo")).toBeInTheDocument();
  });

  it("acepta la clase del dueño y la conserva junto a la suya", () => {
    const { container } = render(
      <SiteLabel name="Torre" code="site-sim-002" className="inspection__site" />,
    );
    const el = container.querySelector(".site-label");
    expect(el).not.toBeNull();
    expect(el).toHaveClass("inspection__site");
  });
});
