import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ConfirmButton from "./ConfirmButton";

describe("ConfirmButton (two-step, RBAC §4.3)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("un solo clic NUNCA dispara: arma con countdown de 5 s", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmButton label="CONFIRMAR ACUSE" armedLabel="CLIC DE NUEVO" onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText("CLIC DE NUEVO")).toBeInTheDocument();
    expect(screen.getByText("5s")).toBeInTheDocument();
  });

  it("segundo clic dentro de la ventana confirma exactamente una vez", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="CONFIRMAR ACUSE" onConfirm={onConfirm} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByText("EJECUTADO")).toBeInTheDocument();
    // Tras el flash de éxito vuelve a idle y un clic re-arma (no dispara).
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByText("CONFIRMAR ACUSE")).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("sin segundo clic en 5 s se desarma en silencio", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="REUBICAR" onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button"));
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText("REUBICAR")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("deshabilitado no arma ni dispara (gate allowed_actions)", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="CONFIRMAR ACUSE" disabled onConfirm={onConfirm} />);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
