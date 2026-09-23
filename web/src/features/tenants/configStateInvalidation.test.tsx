// [A-224 · T-8.09] Publicar umbrales o VOLVER A vN invalidaba `['config-state']`,
// una clave que NO existe: el estado del sync firmado se lee de
// `['fleet', 'config-state']`. El pie «PENDIENTE / SINCRONIZADO» seguía con el
// dato de antes hasta el siguiente poll (≤30 s), justo después del clic que lo
// cambia — en una demo, el momento en que alguien lo está mirando.
//
// Se mide contra la consulta REAL sembrada en caché, no contra la cadena: si la
// clave del lector cambia, este test sigue sabiendo si la invalidación llega.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  putRuleSetRuleSetsPut: vi.fn(),
  publishRuleSetRuleSetsRuleSetIdPublishPost: vi.fn(),
  rollbackRuleSetRuleSetsRuleSetIdRollbackPost: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { useRuleSetPublish } from "./useRuleSetPublish";
import { useRuleSetRollback } from "./useRuleSetRollback";

/** La clave que LEEN la flota y la matriz de clientes (`useFleetSyncStates`). */
const CONFIG_STATE = ["fleet", "config-state"];

let client: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(CONFIG_STATE, []);
});

describe("tras cambiar umbrales se relee el estado REAL del sync", () => {
  it("publicar invalida el config-state que la pantalla lee", async () => {
    sdk.putRuleSetRuleSetsPut.mockResolvedValue({
      data: { rule_set_id: "rs-9", version: 9 },
      response: { status: 200 },
    });
    sdk.publishRuleSetRuleSetsRuleSetIdPublishPost.mockResolvedValue({
      data: { rule_set_id: "rs-9", status: "pending_sync" },
      response: { status: 202 },
    });
    const { result } = renderHook(() => useRuleSetPublish(), { wrapper });
    act(() => result.current.apply({ tenantId: "t-1", config: {}, baseVersion: 8 }));
    await waitFor(() => expect(client.getQueryState(CONFIG_STATE)?.isInvalidated).toBe(true));
  });

  it("volver a una versión anterior también", async () => {
    sdk.rollbackRuleSetRuleSetsRuleSetIdRollbackPost.mockResolvedValue({
      data: { rule_set_id: "rs-10", version: 10 },
      response: { status: 201 },
    });
    const { result } = renderHook(() => useRuleSetRollback(), { wrapper });
    act(() => result.current.volver({ ruleSetId: "rs-1", baseVersion: 9 }));
    await waitFor(() => expect(client.getQueryState(CONFIG_STATE)?.isInvalidated).toBe(true));
  });
});
