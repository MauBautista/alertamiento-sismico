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

  it("[T-6.02] `title` llega al botón: un apagado puede decir por qué", () => {
    render(<ConfirmButton label="FIRMAR" disabled title="Tu rol no firma" />);
    expect(screen.getByRole("button")).toHaveAttribute("title", "Tu rol no firma");
  });

  it("[T-8.07] `ariaLabel` nombra el botón EN REPOSO; armado, lo nombra la advertencia", () => {
    // Una lista de plantillas con un BORRAR por fila necesita decir CUÁL borra;
    // armado, lo que hay que oír es que el siguiente clic lo ejecuta.
    render(<ConfirmButton label="BORRAR" ariaLabel="BORRAR Trimestral" armedLabel="OTRA VEZ" />);
    fireEvent.click(screen.getByRole("button", { name: "BORRAR Trimestral" }));
    expect(screen.getByRole("button", { name: /OTRA VEZ/ })).toBeInTheDocument();
  });
});

// [A-163 · A-011 · T-8.07] «EJECUTADO» en verde ANTES de que respondiera el
// servidor. El botón pintaba el éxito en cuanto se confirmaba: con un 403, un 409
// o la red caída el operador leía «EJECUTADO» sobre un acuse que no entró. Un
// `onConfirm` que devuelve la promesa de la petición le da al botón lo único que
// le faltaba para no mentir: esperar.
describe("ConfirmButton · la confirmación espera al servidor (A-163)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function deferred(): {
    promise: Promise<void>;
    resolve: () => void;
    reject: (e: Error) => void;
  } {
    let resolve!: () => void;
    let reject!: (e: Error) => void;
    const promise = new Promise<void>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  it("mientras la promesa no resuelve dice ENVIANDO…, neutro y sin poder reenviarse", async () => {
    const d = deferred();
    const onConfirm = vi.fn(() => d.promise);
    render(<ConfirmButton label="CONFIRMAR ACUSE" onConfirm={onConfirm} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    // Ni el verde del éxito ni el texto que lo afirma.
    expect(screen.queryByText("EJECUTADO")).toBeNull();
    expect(screen.queryByText("HECHO")).toBeNull();
    expect(screen.getByText("ENVIANDO…")).toBeInTheDocument();
    expect(btn.className).not.toContain("soc-confirm--done");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
    // Sin doble envío: el tercer clic no llega a ningún sitio.
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await act(async () => {
      d.resolve();
      await d.promise;
    });
    expect(screen.getByText("HECHO")).toBeInTheDocument();
    expect(btn.className).toContain("soc-confirm--done");
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByText("CONFIRMAR ACUSE")).toBeInTheDocument();
  });

  it("el rótulo del éxito se puede nombrar (ACUSADO): dice lo que pasó", async () => {
    render(
      <ConfirmButton
        label="CONFIRMAR ACUSE"
        doneLabel="ACUSADO"
        onConfirm={() => Promise.resolve()}
      />,
    );
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    await act(async () => {
      fireEvent.click(btn);
      await Promise.resolve();
    });
    expect(screen.getByText("ACUSADO")).toBeInTheDocument();
  });

  it("si la promesa se rechaza vuelve a REPOSO: no pinta éxito y el llamador pinta el error", async () => {
    const d = deferred();
    const onConfirm = vi.fn(() => d.promise);
    render(<ConfirmButton label="CONFIRMAR ACUSE" onConfirm={onConfirm} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    fireEvent.click(btn);
    await act(async () => {
      d.reject(new Error("409"));
      await d.promise.catch(() => undefined);
    });
    expect(screen.queryByText("HECHO")).toBeNull();
    expect(screen.queryByText("EJECUTADO")).toBeNull();
    expect(screen.getByText("CONFIRMAR ACUSE")).toBeInTheDocument();
    expect(btn).toBeEnabled();
    expect(btn.className).not.toContain("soc-confirm--done");
    // Y se puede volver a intentar: un clic ARMA otra vez (no dispara).
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByText("CLIC NUEVAMENTE PARA CONFIRMAR")).toBeInTheDocument();
  });

  it("desmontarse con la petición en vuelo no deja un setState colgando", async () => {
    const d = deferred();
    const errores = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = render(<ConfirmButton label="X" onConfirm={() => d.promise} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    fireEvent.click(btn);
    unmount();
    await act(async () => {
      d.resolve();
      await d.promise;
      vi.advanceTimersByTime(2000);
    });
    expect(errores).not.toHaveBeenCalled();
    errores.mockRestore();
  });
});
