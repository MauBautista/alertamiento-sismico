import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SirenTestPanel from "./SirenTestPanel";
import type { SirenPhase, SirenTestData } from "./useSirenTest";

const COMMAND = {
  command_id: "c-1",
  tenant_id: "t-1",
  site_id: "s-1",
  gateway_id: "g-1",
  issued_by: "u-1",
  channel: "siren",
  action: "activate",
  event_id: null,
  nonce: "abcdef1234567890",
  issued_at: "2026-07-08T10:41:00Z",
  expires_at: "2026-07-08T10:41:30Z",
  status: "pending",
  ack: null,
  error: null,
};

function siren(phase: SirenPhase, over: Partial<SirenTestData> = {}): SirenTestData {
  return {
    phase,
    command:
      phase === "idle" ? null : { ...COMMAND, status: phase === "acked" ? "acked" : "pending" },
    detail: null,
    activate: vi.fn(),
    deactivate: vi.fn(),
    reset: vi.fn(),
    pending: false,
    ...over,
  };
}

/** Dos clics: ConfirmButton arma en el primero y dispara en el segundo (RBAC §4.3). */
function confirm(name: RegExp) {
  const button = screen.getByRole("button", { name });
  fireEvent.click(button);
  fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
}

describe("SirenTestPanel", () => {
  it("sin la acción siren_test el panel no existe", () => {
    render(<SirenTestPanel siren={siren("idle")} canTest={false} />);
    expect(screen.queryByTestId("siren-panel")).toBeNull();
  });

  it("emitir un comando NO afirma que la sirena suena", () => {
    // Regla de oro 8: un 201 dice "el comando salió", no "el actuador se movió".
    render(<SirenTestPanel siren={siren("issued")} canTest={true} />);
    const phase = screen.getByTestId("siren-phase");
    expect(phase).toHaveTextContent("ESPERANDO ACUSE DEL GABINETE");
    expect(phase).not.toHaveTextContent("SONANDO");
  });

  it("solo con el ack del edge se dice que la sirena suena", () => {
    render(<SirenTestPanel siren={siren("acked")} canTest={true} />);
    expect(screen.getByTestId("siren-phase")).toHaveTextContent(
      "SIRENA SONANDO · ACUSADA POR EL EDGE",
    );
  });

  it("sin acuse en el TTL se dice que NO se activó, no 'activada'", () => {
    render(<SirenTestPanel siren={siren("expired")} canTest={true} />);
    const phase = screen.getByTestId("siren-phase");
    expect(phase).toHaveTextContent("SIN RESPUESTA DEL GABINETE");
    expect(phase).toHaveTextContent("LA SIRENA NO SE ACTIVÓ");
  });

  it("activar exige confirmación en dos pasos", () => {
    const activate = vi.fn();
    render(<SirenTestPanel siren={siren("idle", { activate })} canTest={true} />);

    // Un solo clic arma, no dispara.
    fireEvent.click(screen.getByRole("button", { name: /PROBAR SIRENA/ }));
    expect(activate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(activate).toHaveBeenCalledTimes(1);
  });

  it("con la sirena acusada, el control ofrece silenciarla", () => {
    const deactivate = vi.fn();
    render(<SirenTestPanel siren={siren("acked", { deactivate })} canTest={true} />);
    confirm(/SILENCIAR SIRENA/);
    expect(deactivate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /PROBAR SIRENA/ })).toBeNull();
  });

  it("mientras el comando está en vuelo no se puede reemitir", () => {
    render(<SirenTestPanel siren={siren("issued")} canTest={true} />);
    expect(screen.getByRole("button", { name: /PROBAR SIRENA/ })).toBeDisabled();
  });

  it("un rechazo muestra el motivo del gabinete y se puede descartar", () => {
    const reset = vi.fn();
    render(
      <SirenTestPanel
        siren={siren("rejected", { detail: "nonce ya usado", reset })}
        canTest={true}
      />,
    );
    expect(screen.getByTestId("siren-detail")).toHaveTextContent("nonce ya usado");
    fireEvent.click(screen.getByRole("button", { name: "DESCARTAR" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
