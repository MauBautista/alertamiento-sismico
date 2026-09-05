// [T-5.16] Volver atrás es un clic, no un dictado.
//
// Hasta aquí, revertir un umbral era teclear los valores viejos de memoria: el
// versionado estaba bien resuelto y el histórico en la base, pero no había forma
// de VOLVER. Y teclearlos perdía además la constancia de que aquello fue una
// reversión y no una edición cualquiera.
//
// La aserción que gobierna el archivo: **volver atrás CREA una versión**. La
// pantalla no puede insinuar en ningún sitio que el histórico se recorta.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useRuleSetRollback: vi.fn() }));
vi.mock("./useRuleSetRollback", async () => ({
  ...(await vi.importActual<typeof import("./useRuleSetRollback")>("./useRuleSetRollback")),
  useRuleSetRollback: mocks.useRuleSetRollback,
}));

import RuleSetHistory from "./RuleSetHistory";

function version(v: number, over: Record<string, unknown> = {}) {
  return {
    rule_set_id: `rs-${v}`,
    tenant_id: "t-1",
    scope_type: "tenant",
    scope_id: "t-1",
    version: v,
    is_active: false,
    config: {},
    created_by: null,
    created_at: `2026-09-0${v}T18:00:00Z`,
    rolled_back_to: null,
    ...over,
  };
}

function estado(over: Record<string, unknown> = {}) {
  return { volver: vi.fn(), pendingId: null, error: null, conflict: false, ...over };
}

const TRES = [version(3, { is_active: true }), version(2), version(1)];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useRuleSetRollback.mockReturnValue(estado());
});

describe("RuleSetHistory", () => {
  it("lista las versiones del alcance, la activa marcada", () => {
    render(<RuleSetHistory versions={TRES} canEdit />);
    expect(screen.getByTestId("rs-row-3")).toHaveTextContent("ACTIVA");
    expect(screen.getByTestId("rs-row-2")).not.toHaveTextContent("ACTIVA");
  });

  it("la activa NO ofrece volver a sí misma", () => {
    render(<RuleSetHistory versions={TRES} canEdit />);
    expect(within(screen.getByTestId("rs-row-3")).queryByRole("button")).toBeNull();
    expect(within(screen.getByTestId("rs-row-2")).getByRole("button")).toBeInTheDocument();
  });

  it("volver manda el id de la versión destino y la ACTIVA como base", () => {
    const e = estado();
    mocks.useRuleSetRollback.mockReturnValue(e);
    render(<RuleSetHistory versions={TRES} canEdit />);
    fireEvent.click(within(screen.getByTestId("rs-row-1")).getByRole("button"));
    expect(e.volver).toHaveBeenCalledWith({ ruleSetId: "rs-1", baseVersion: 3 });
  });

  it("dice que volver CREA una versión, no que recorta el histórico", () => {
    render(<RuleSetHistory versions={TRES} canEdit />);
    const texto = screen.getByTestId("rule-set-history").textContent ?? "";
    expect(texto).toMatch(/CREA UNA VERSIÓN NUEVA/i);
    for (const mentira of ["borra", "elimina", "descarta"]) {
      expect(texto.toLowerCase()).not.toContain(mentira);
    }
  });

  it("una versión nacida de un rollback dice de cuál viene", () => {
    render(
      <RuleSetHistory
        versions={[version(3, { is_active: true, rolled_back_to: "rs-1" }), version(2), version(1)]}
        canEdit
      />,
    );
    expect(screen.getByTestId("rs-row-3")).toHaveTextContent("VUELVE A v1");
  });

  it("quien no edita umbrales ve el histórico pero no el botón", () => {
    render(<RuleSetHistory versions={TRES} canEdit={false} />);
    expect(screen.getByTestId("rs-row-2")).toBeInTheDocument();
    expect(within(screen.getByTestId("rs-row-2")).queryByRole("button")).toBeNull();
  });

  it("mientras vuelve, ese botón queda deshabilitado y lo dice", () => {
    mocks.useRuleSetRollback.mockReturnValue(estado({ pendingId: "rs-1" }));
    render(<RuleSetHistory versions={TRES} canEdit />);
    const b = within(screen.getByTestId("rs-row-1")).getByRole("button");
    expect(b).toBeDisabled();
    expect(b).toHaveTextContent("VOLVIENDO");
  });

  it("el 409 se explica: alguien publicó mientras mirabas", () => {
    mocks.useRuleSetRollback.mockReturnValue(
      estado({ conflict: true, error: "el rule_set cambió en el servidor" }),
    );
    render(<RuleSetHistory versions={TRES} canEdit />);
    expect(screen.getByRole("alert")).toHaveTextContent(/recarga/i);
  });

  it("sin historial previo no ofrece volver a ninguna parte", () => {
    render(<RuleSetHistory versions={[version(1, { is_active: true })]} canEdit />);
    expect(screen.getByTestId("rule-set-history")).toHaveTextContent(/SIN VERSIONES ANTERIORES/i);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
