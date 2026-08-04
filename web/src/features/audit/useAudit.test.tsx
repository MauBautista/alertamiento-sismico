import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EMPTY_FILTERS, isFiltering, useAudit } from "./useAudit";

const mocks = vi.hoisted(() => ({ listAuditAuditGet: vi.fn() }));
vi.mock("@takab/sdk", () => mocks);

const PAGE = (items: unknown[], next: string | null = null) => ({
  data: { items, next_cursor: next },
  response: { status: 200 },
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function row(id: number) {
  return {
    audit_id: id,
    ts: "2026-08-04T10:00:00Z",
    tenant_id: null,
    actor: "user:x",
    verb: "ack",
    object: "incident:1",
    meta: {},
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listAuditAuditGet.mockResolvedValue(PAGE([row(1)]));
});

describe("isFiltering", () => {
  it("distingue 'sin filtro' de 'filtro que no devolvió nada'", () => {
    expect(isFiltering(EMPTY_FILTERS)).toBe(false);
    expect(isFiltering({ ...EMPTY_FILTERS, verb: "   " })).toBe(false);
    expect(isFiltering({ ...EMPTY_FILTERS, verb: "ack" })).toBe(true);
  });
});

describe("useAudit · filtros que sí llegan al servidor", () => {
  it("no manda claves vacías: el endpoint las trataría como filtro", async () => {
    const { result } = renderHook(() => useAudit(EMPTY_FILTERS), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(mocks.listAuditAuditGet).toHaveBeenCalledWith({ query: {} });
  });

  it("recorta los valores y usa el alias `object` del prefijo", async () => {
    const { result } = renderHook(
      () => useAudit({ ...EMPTY_FILTERS, actor: " user:ana ", object: " incident: " }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(mocks.listAuditAuditGet).toHaveBeenCalledWith({
      query: { actor: "user:ana", object: "incident:" },
    });
  });

  it("`datetime-local` se manda como UTC EXPLÍCITO, no a merced del navegador", async () => {
    // Sin la Z, dos operadores en husos distintos verían ventanas distintas con
    // el mismo formulario; el servidor asume UTC cuando falta el offset.
    const { result } = renderHook(
      () => useAudit({ ...EMPTY_FILTERS, from: "2026-08-04T10:30", to: "2026-08-04T12:00:30Z" }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(mocks.listAuditAuditGet).toHaveBeenCalledWith({
      query: { from: "2026-08-04T10:30:00Z", to: "2026-08-04T12:00:30Z" },
    });
  });
});

describe("useAudit · keyset", () => {
  it("acumula páginas y usa el cursor devuelto", async () => {
    mocks.listAuditAuditGet.mockResolvedValueOnce(PAGE([row(1)], "cur-1"));
    mocks.listAuditAuditGet.mockResolvedValueOnce(PAGE([row(2)]));
    const { result } = renderHook(() => useAudit(EMPTY_FILTERS), { wrapper });
    await waitFor(() => expect(result.current.hasMore).toBe(true));

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(mocks.listAuditAuditGet).toHaveBeenLastCalledWith({ query: { cursor: "cur-1" } });
    expect(result.current.hasMore).toBe(false);
  });

  it("un 403 se traduce a lenguaje de operador, no a un código pelado", async () => {
    mocks.listAuditAuditGet.mockResolvedValue({ data: undefined, response: { status: 403 } });
    const { result } = renderHook(() => useAudit(EMPTY_FILTERS), { wrapper });
    await waitFor(() => expect(result.current.error).toMatch(/SIN PERMISO/));
  });
});
