import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SevTag from "./SevTag";

describe("SevTag", () => {
  it.each([
    ["critical", "CRÍTICO", "soc-sev--red"],
    ["warning", "ADVERTENCIA", "soc-sev--warn"],
    ["watch", "VIGILANCIA", "soc-sev--warn"],
    ["info", "NORMAL", "soc-sev--ok"],
  ])("mapea %s → %s", (severity, label, cls) => {
    const { container } = render(<SevTag severity={severity} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector(`.${cls}`)).not.toBeNull();
  });

  it("una severidad desconocida JAMÁS se muestra como NORMAL", () => {
    const { container } = render(<SevTag severity="mystery" />);
    expect(screen.getByText("MYSTERY")).toBeInTheDocument();
    expect(container.querySelector(".soc-sev--warn")).not.toBeNull();
    expect(screen.queryByText("NORMAL")).toBeNull();
  });
});
