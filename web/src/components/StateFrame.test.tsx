import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { expectFourStates } from "../test-utils/states";
import StateFrame from "./StateFrame";

function frame(over: Partial<Parameters<typeof StateFrame>[0]> = {}) {
  return (
    <StateFrame label="INCIDENTES" loading={false} {...over}>
      <span>contenido-vivo</span>
    </StateFrame>
  );
}

describe("StateFrame", () => {
  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    expectFourStates((state) =>
      frame({
        loading: state === "loading",
        error: state === "error" ? "falló la carga" : null,
        empty: state === "empty",
        staleSince: state === "stale" ? Date.UTC(2026, 6, 8, 10, 41, 30) : null,
      }),
    );
  });

  it("loading oculta el contenido y anuncia el panel", () => {
    render(frame({ loading: true }));
    expect(screen.queryByText("contenido-vivo")).toBeNull();
    expect(screen.getByText(/CARGANDO · INCIDENTES/)).toBeInTheDocument();
  });

  it("error muestra el mensaje con role=alert y reintento", () => {
    const onRetry = vi.fn();
    render(frame({ error: "GET /incidents falló (503)", onRetry }));
    expect(screen.getByRole("alert")).toHaveTextContent("GET /incidents falló (503)");
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("empty usa el texto propio si se da", () => {
    render(frame({ empty: true, emptyText: "SIN INCIDENTES ABIERTOS" }));
    expect(screen.getByText("SIN INCIDENTES ABIERTOS")).toBeInTheDocument();
  });

  it("stale MUESTRA el contenido pero bajo el banner DATOS RETENIDOS con HH:MM:SS", () => {
    render(frame({ staleSince: Date.UTC(2026, 6, 8, 10, 41, 30) }));
    expect(screen.getByText("contenido-vivo")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("DATOS RETENIDOS · 10:41:30 UTC");
  });

  it("fresco: contenido sin banner, data-state=ready", () => {
    const { container } = render(frame());
    expect(screen.getByText("contenido-vivo")).toBeInTheDocument();
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
    expect(container.querySelector('[data-state="ready"]')).not.toBeNull();
  });

  it("la precedencia es loading > error > empty > stale", () => {
    const { container } = render(
      frame({
        loading: true,
        error: "x",
        empty: true,
        staleSince: 0,
      }),
    );
    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
  });
});
