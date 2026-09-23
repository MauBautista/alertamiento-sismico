// [A-112 bis · T-8.09] El mismo defecto que A-112 cerró en /building, en /tenants.
//
// El marco MULTI-TENANT (envuelve la rejilla entera) rotula «DATOS RETENIDOS» a
// los 2 min (`TENANTS_STALE_MS`); «Usuarios del cliente» y «Etiquetas de
// cumplimiento», a los 5. Ninguna de las tres consultas tenía cadencia, y
// `lib/queryClient` fija `refetchOnWindowFocus: false`: con la página abierta NO
// se releían nunca, y el rótulo saltaba con el sistema sano. Un rótulo de
// retención que salta sin motivo entrena a ignorarlo, y entonces no se lee el
// día que es verdad (regla de oro 7, en las dos direcciones).
//
// Por eso cada caso tiene su CONTROL: con la relectura fallando, el dato SÍ
// envejece y el umbral lo delata. Una cadencia que ocultara el fallo sería el
// defecto contrario.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  listTenantsTenantsGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
  listSitesSitesGet: vi.fn(),
  listUsersUsersGet: vi.fn(),
  get: vi.fn(),
}));
vi.mock("@takab/sdk", () => ({
  ...sdk,
  client: { get: (...a: unknown[]) => sdk.get(...a) },
}));

import {
  COMPLIANCE_REFRESH_MS,
  COMPLIANCE_STALE_MS,
  useComplianceLabels,
} from "./useComplianceLabels";
import { TENANTS_REFRESH_MS, TENANTS_STALE_MS, useTenants } from "./useTenants";
import { USERS_REFRESH_MS, USERS_STALE_MS, useUsers } from "./useUsers";

const OK = (data: unknown) => ({ data, response: { status: 200 } });
const FALLO = { data: undefined, response: { status: 503 } };

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Avanza el reloj falso DENTRO de `act`: las relecturas actualizan estado. */
async function avanza(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  sdk.listTenantsTenantsGet.mockResolvedValue(
    OK([{ tenant_id: "t-1", code: "A", name: "A", isolation_mode: "logical" }]),
  );
  sdk.listRuleSetsRuleSetsGet.mockResolvedValue(OK({ items: [] }));
  sdk.listSitesSitesGet.mockResolvedValue(OK([]));
  sdk.listUsersUsersGet.mockResolvedValue(
    OK({ items: [], next_cursor: null, backend: "simulated" }),
  );
  sdk.get.mockResolvedValue(
    OK({
      tenant_id: "t-1",
      provenance: "declared_by_tenant",
      notice: "",
      items: [],
      notes: [],
      unreadable: null,
      updated_at: null,
      updated_by: null,
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

describe("/tenants · umbral y cadencia viajan juntos", () => {
  it.each([
    ["tenants", TENANTS_REFRESH_MS, TENANTS_STALE_MS],
    ["usuarios", USERS_REFRESH_MS, USERS_STALE_MS],
    ["cumplimiento", COMPLIANCE_REFRESH_MS, COMPLIANCE_STALE_MS],
  ])("%s: la relectura cabe DOS veces antes del umbral", (_n, cadencia, umbral) => {
    // Dos oportunidades: una relectura fallida suelta no rotula; dos seguidas, sí.
    expect(cadencia * 2).toBeLessThan(umbral);
  });
});

describe("useTenants · el catálogo se relee", () => {
  it("con el servidor sano, el marco MULTI-TENANT nunca llega a RETENIDO", async () => {
    const { result } = renderHook(() => useTenants(), { wrapper });
    await avanza(10);
    expect(sdk.listTenantsTenantsGet).toHaveBeenCalledTimes(1);

    await avanza(TENANTS_STALE_MS * 3);
    expect(sdk.listTenantsTenantsGet.mock.calls.length).toBeGreaterThan(3);
    expect(Date.now() - result.current.dataUpdatedAt).toBeLessThanOrEqual(TENANTS_REFRESH_MS);
  });

  it("CONTROL: si la relectura falla, el dato SÍ envejece y el umbral lo delata", async () => {
    const { result } = renderHook(() => useTenants(), { wrapper });
    await avanza(10);
    const primera = result.current.dataUpdatedAt;
    sdk.listTenantsTenantsGet.mockResolvedValue(FALLO);

    await avanza(TENANTS_STALE_MS + 1_000);
    expect(result.current.dataUpdatedAt).toBe(primera);
    expect(Date.now() - result.current.dataUpdatedAt).toBeGreaterThan(TENANTS_STALE_MS);
    // Y el catálogo viejo NO se tira: se enseña rotulado, no se sustituye por error.
    expect(result.current.tenants).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });
});

describe("useUsers · el directorio se relee", () => {
  it("con el servidor sano, «Usuarios del cliente» nunca llega a RETENIDO", async () => {
    const { result } = renderHook(() => useUsers(true), { wrapper });
    await avanza(10);
    expect(sdk.listUsersUsersGet).toHaveBeenCalledTimes(1);

    await avanza(USERS_STALE_MS * 2);
    expect(sdk.listUsersUsersGet.mock.calls.length).toBeGreaterThan(2);
    expect(Date.now() - result.current.dataUpdatedAt).toBeLessThanOrEqual(USERS_REFRESH_MS);
  });

  it("CONTROL: si la relectura falla, el dato SÍ envejece", async () => {
    const { result } = renderHook(() => useUsers(true), { wrapper });
    await avanza(10);
    sdk.listUsersUsersGet.mockResolvedValue(FALLO);

    await avanza(USERS_STALE_MS + 1_000);
    expect(Date.now() - result.current.dataUpdatedAt).toBeGreaterThan(USERS_STALE_MS);
  });

  it("sin la acción no pregunta NUNCA, ni siquiera por la cadencia", async () => {
    renderHook(() => useUsers(false), { wrapper });
    await avanza(USERS_STALE_MS * 2);
    expect(sdk.listUsersUsersGet).not.toHaveBeenCalled();
  });
});

describe("useComplianceLabels · el marco declarado se relee", () => {
  it("con el servidor sano, «Etiquetas de cumplimiento» nunca llega a RETENIDO", async () => {
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await avanza(10);
    expect(sdk.get).toHaveBeenCalledTimes(1);

    await avanza(COMPLIANCE_STALE_MS * 2);
    expect(sdk.get.mock.calls.length).toBeGreaterThan(2);
    expect(result.current.staleSince).toBeNull();
  });

  it("CONTROL: si la relectura falla, `staleSince` se enciende con la hora del último dato", async () => {
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await avanza(10);
    const primera = Date.now();
    sdk.get.mockResolvedValue(FALLO);

    await avanza(COMPLIANCE_STALE_MS + 1_000);
    expect(result.current.staleSince).not.toBeNull();
    expect(result.current.staleSince).toBeLessThanOrEqual(primera);
  });
});
