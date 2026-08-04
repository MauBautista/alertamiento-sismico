import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditRowOut } from "@takab/sdk";

import { expectFourStates } from "../../test-utils/states";
import AuditPage from "./AuditPage";
import type { AuditData } from "./useAudit";

const mocks = vi.hoisted(() => ({ useAudit: vi.fn() }));

vi.mock("./useAudit", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./useAudit")>();
  return { ...actual, useAudit: mocks.useAudit };
});

function row(over: Partial<AuditRowOut> = {}): AuditRowOut {
  return {
    audit_id: 1,
    ts: "2026-08-04T10:15:00Z",
    tenant_id: "11111111-1111-1111-1111-111111111111",
    actor: "user:ana",
    verb: "siren_test",
    object: "site:S-001",
    meta: { channel: "siren" },
    ...over,
  };
}

function auditData(over: Partial<AuditData> = {}): AuditData {
  return {
    rows: [row()],
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    hasMore: false,
    loadingMore: false,
    loadMore: vi.fn(),
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useAudit.mockReturnValue(auditData());
});

describe("AuditPage · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((state) => {
      mocks.useAudit.mockReturnValue(
        auditData({
          loading: state === "loading",
          error: state === "error" ? "GET /audit falló (500)" : null,
          rows: state === "empty" ? [] : [row()],
          dataUpdatedAt: state === "stale" ? Date.now() - 400_000 : Date.now(),
        }),
      );
      return <AuditPage />;
    });
  });
});

describe("AuditPage · la bitácora se lee, no se toca", () => {
  it("pinta la fila con su sello UTC, actor, verbo, objeto y meta", () => {
    render(<AuditPage />);
    const cells = screen.getByTestId("audit-row");
    expect(cells.textContent).toContain("2026-08-04 · 10:15");
    expect(cells.textContent).toContain("user:ana");
    expect(cells.textContent).toContain("siren_test");
    expect(cells.textContent).toContain("site:S-001");
    expect(cells.textContent).toContain("channel=siren");
  });

  it("meta vacío NO se pinta como '{}' decorativo", () => {
    mocks.useAudit.mockReturnValue(auditData({ rows: [row({ meta: {} })] }));
    render(<AuditPage />);
    expect(screen.getByTestId("audit-row").textContent).not.toContain("{}");
  });

  it("no ofrece ningún control de escritura sobre una tabla append-only", () => {
    render(<AuditPage />);
    const labels = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(labels.some((l) => /BORRAR|ELIMINAR|EDITAR|NUEVO/i.test(l))).toBe(false);
  });

  it("no inventa un total: la paginación es keyset, no hay COUNT", () => {
    render(<AuditPage />);
    expect(screen.getByText(/1 REGISTRO\(S\) CARGADO\(S\)/)).toBeTruthy();
    expect(screen.getByText("FIN DE LA BITÁCORA VISIBLE")).toBeTruthy();
  });
});

describe("AuditPage · filtros y paginación", () => {
  it("los filtros NO se aplican al teclear: se aplican al enviar", () => {
    render(<AuditPage />);
    fireEvent.change(screen.getByLabelText("Verbo"), { target: { value: "ack" } });
    // Aún no: la última llamada sigue con el filtro vacío.
    expect(mocks.useAudit).toHaveBeenLastCalledWith(expect.objectContaining({ verb: "" }));
    fireEvent.click(screen.getByRole("button", { name: "APLICAR" }));
    expect(mocks.useAudit).toHaveBeenLastCalledWith(expect.objectContaining({ verb: "ack" }));
  });

  it("LIMPIAR devuelve el formulario y la consulta al estado sin filtro", () => {
    render(<AuditPage />);
    fireEvent.change(screen.getByLabelText("Actor"), { target: { value: "user:ana" } });
    fireEvent.click(screen.getByRole("button", { name: "APLICAR" }));
    fireEvent.click(screen.getByRole("button", { name: "LIMPIAR" }));
    expect(mocks.useAudit).toHaveBeenLastCalledWith(
      expect.objectContaining({ actor: "", verb: "", object: "", from: "", to: "" }),
    );
  });

  it("el empty distingue 'no hay nada' de 'nada para este filtro'", () => {
    mocks.useAudit.mockReturnValue(auditData({ rows: [] }));
    const { rerender } = render(<AuditPage />);
    expect(screen.getByText("SIN REGISTROS VISIBLES PARA ESTE ROL")).toBeTruthy();

    rerender(<AuditPage />);
    fireEvent.change(screen.getByLabelText("Verbo"), { target: { value: "ack" } });
    fireEvent.click(screen.getByRole("button", { name: "APLICAR" }));
    expect(screen.getByText("SIN REGISTROS PARA EL FILTRO")).toBeTruthy();
  });

  it("CARGAR MÁS pide la siguiente página del keyset", () => {
    const loadMore = vi.fn();
    mocks.useAudit.mockReturnValue(auditData({ hasMore: true, loadMore }));
    render(<AuditPage />);
    fireEvent.click(screen.getByRole("button", { name: "CARGAR MÁS" }));
    expect(loadMore).toHaveBeenCalledTimes(1);
  });
});
