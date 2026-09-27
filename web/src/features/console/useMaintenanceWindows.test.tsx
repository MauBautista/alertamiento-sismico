// [T-8.09] Quién pide las ventanas de mantenimiento, y quién no.
//
// El recorrido por rol del 2026-09-23 (`e2e/recorrido_por_rol.spec.ts`) midió un
// `GET /maintenance-windows → 403` en CADA página para gov_operator, inspector y
// el entonces administrador de inmueble (retirado por D-42): la franja de escena lo pide siempre, y el servidor solo deja leer
// a `routers/maintenance.py::READ_ROLES`. La pantalla ya lo toleraba (`forbidden`),
// pero una petición condenada en cada página es ruido en la consola del navegador y
// tráfico al servidor. Ahora se decide ANTES de pedir, con la misma regla que el
// servidor (la ancla del lado de la API es
// `tests/api/test_maintenance_windows.py::test_READ_ROLES_es_la_regla_de_la_consola`).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES, WEB_ROLES, type RoleName } from "../../test-utils/meFixtures";
import { puedeLeerVentanas, useMaintenanceWindows } from "./useMaintenanceWindows";

const sdk = vi.hoisted(() => ({ listWindowsMaintenanceWindowsGet: vi.fn() }));
vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  listWindowsMaintenanceWindowsGet: sdk.listWindowsMaintenanceWindowsGet,
}));

/** Lo que `routers/maintenance.py::READ_ROLES` concede hoy (y lo que el test de la API ancla). */
const LEEN: ReadonlySet<RoleName> = new Set(["takab_superadmin", "takab_support", "tenant_admin"]);

function envoltorio() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  resetSessionStoreForTests();
  sdk.listWindowsMaintenanceWindowsGet.mockResolvedValue({
    data: { items: [] },
    response: new Response(null, { status: 200 }),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("puedeLeerVentanas", () => {
  it.each(WEB_ROLES)("%s: la regla del cliente es la del servidor", (rol) => {
    expect(puedeLeerVentanas(ME_FIXTURES[rol])).toBe(LEEN.has(rol));
  });

  it("sin /me todavía no se decide (ni sí ni no)", () => {
    expect(puedeLeerVentanas(null)).toBeNull();
  });
});

describe("useMaintenanceWindows", () => {
  it.each(["gov_operator", "inspector"] as const)(
    "%s: NO pide la ruta que le daría 403, y se declara sin lectura",
    async (rol) => {
      useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES[rol] });
      const { result } = renderHook(() => useMaintenanceWindows(), { wrapper: envoltorio() });
      await waitFor(() => expect(result.current.forbidden).toBe(true));
      expect(sdk.listWindowsMaintenanceWindowsGet).not.toHaveBeenCalled();
      expect(result.current.loading).toBe(false);
    },
  );

  // [T-9.20] Era «soc_operator sí la pide». Ese rol ya no existe (entra como
  // tenant_admin); `takab_support` es ahora el único que la lee SIN poder abrir
  // ventanas, o sea el que ejercita el literal de `READ_ROLES`.
  it("takab_support sí la pide aunque no abre ventanas", async () => {
    expect(ME_FIXTURES.takab_support.allowed_actions.maintenance_window).toBe(false);
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.takab_support });
    const { result } = renderHook(() => useMaintenanceWindows(), { wrapper: envoltorio() });
    await waitFor(() => expect(sdk.listWindowsMaintenanceWindowsGet).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.forbidden).toBe(false);
  });
});
