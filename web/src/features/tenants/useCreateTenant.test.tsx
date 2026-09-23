// [A-225 · T-8.09] El alta de cliente decía «GET /tenants falló (409)» al fallar
// un POST: el verbo equivocado y ni una palabra de POR QUÉ. Un 409 aquí es que el
// código ya existe, y el servidor lo dice; lo que el superadmin tiene delante
// tiene que ser eso, no el síntoma de otra petición.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ createTenantTenantsPost: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { useCreateTenant } from "./useTenants";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useCreateTenant · el error del ALTA habla del alta", () => {
  it("un 409 dice que el cliente ya existe y trae el motivo del servidor", async () => {
    sdk.createTenantTenantsPost.mockResolvedValue({
      data: undefined,
      error: { detail: "code 'HOSP-1' ya existe" },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useCreateTenant(), { wrapper });
    act(() => result.current.create({ code: "HOSP-1", name: "Hospital" } as never));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).not.toMatch(/GET/);
    expect(result.current.error).toMatch(/YA EXISTE/);
    expect(result.current.error).toMatch(/HOSP-1/);
  });

  it("otro fallo nombra el POST, no un GET", async () => {
    sdk.createTenantTenantsPost.mockResolvedValue({
      data: undefined,
      response: { status: 500 },
    });
    const { result } = renderHook(() => useCreateTenant(), { wrapper });
    act(() => result.current.create({ code: "X", name: "X" } as never));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toMatch(/POST \/tenants/);
  });
});
