// [T-2.32] Resumen puro del burst de actuación del quórum de red.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CommandOut } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES, WEB_ROLES, type RoleName } from "../../test-utils/meFixtures";
import {
  QUORUM_ACTOR_UUID,
  puedeLeerComandos,
  summarizeQuorumCommands,
  useQuorumCommands,
  useQuorumCommandsView,
} from "./useQuorumCommands";

const sdk = vi.hoisted(() => ({ listCommandsSitesSiteIdCommandsGet: vi.fn() }));
vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  listCommandsSitesSiteIdCommandsGet: sdk.listCommandsSitesSiteIdCommandsGet,
}));

function cmd(over: Partial<CommandOut> = {}): CommandOut {
  return {
    ack: null,
    action: "activate",
    channel: "siren",
    command_id: "c-1",
    error: null,
    event_id: "EVT-1",
    expires_at: "2026-08-03T12:01:00Z",
    gateway_id: "g-1",
    issued_at: "2026-08-03T12:00:00Z",
    issued_by: QUORUM_ACTOR_UUID,
    nonce: "n-1",
    site_id: "s-1",
    status: "pending",
    tenant_id: "t-1",
    ...over,
  };
}

describe("summarizeQuorumCommands", () => {
  it("filtra por actor quórum + evento, dedupe canales ordenados y cuenta acks", () => {
    const commands = [
      cmd({ channel: "siren", status: "acked" }),
      cmd({ channel: "strobe", command_id: "c-2", nonce: "n-2" }),
      cmd({ channel: "siren", command_id: "c-3", nonce: "n-3", gateway_id: "g-2" }),
      // comando MANUAL de un operador: jamás se rotula como quórum
      cmd({ channel: "gas_valve", command_id: "c-4", nonce: "n-4", issued_by: "user-uuid" }),
      // otro evento: fuera del resumen
      cmd({ channel: "elevator", command_id: "c-5", nonce: "n-5", event_id: "EVT-2" }),
    ];
    expect(summarizeQuorumCommands(commands, "EVT-1")).toEqual({
      channels: ["siren", "strobe"],
      acked: 1,
      total: 3,
    });
  });

  it("null sin evento enfocado, sin datos o sin burst del actor", () => {
    expect(summarizeQuorumCommands(undefined, "EVT-1")).toBeNull();
    expect(summarizeQuorumCommands([cmd()], null)).toBeNull();
    expect(summarizeQuorumCommands([cmd({ issued_by: "user-x" })], "EVT-1")).toBeNull();
  });
});

// [T-8.08 · A-090 / A-130] EL 403 CADA 15 s.
//
// `GET /sites/{id}/commands` lo guarda `COMMAND_ROLES` (routers/commands.py):
// los roles con ALGUNA acción de comando —siren_test, self_test, manual_activate
// o siren_silence—. `soc_operator`, `gov_operator` y `takab_support` no tienen
// ninguna, y el hook pedía igual cada 15 s mientras hubiera un incidente con
// evento en foco: 403 tras 403 en la pestaña de red, y un resumen `null` que se
// leía como «no hubo actuación de la red». No se amplía el permiso: se deja de
// pedir lo que el rol no tiene, y se DICE por qué no hay lectura.

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return createElement(QueryClientProvider, { client }, children);
}

function como(role: RoleName): void {
  useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES[role] });
}

describe("useQuorumCommands · sólo pide lo que el rol puede leer [A-090]", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
      data: { items: [cmd({ status: "acked" })] },
      response: { status: 200 },
    });
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it.each(["soc_operator", "gov_operator", "takab_support"] as const)(
    "%s: NO dispara la petición condenada y declara `sin-permiso`",
    async (role) => {
      como(role);
      const { result } = renderHook(() => useQuorumCommandsView("s-1", "EVT-1"), { wrapper });
      expect(result.current).toEqual({ kind: "sin-permiso" });
      // Un tick para que una query mal gateada tuviera ocasión de salir.
      await new Promise((r) => setTimeout(r, 0));
      expect(sdk.listCommandsSitesSiteIdCommandsGet).not.toHaveBeenCalled();
    },
  );

  it("tenant_admin sí lo lee, y el resumen llega", async () => {
    como("tenant_admin");
    const { result } = renderHook(() => useQuorumCommandsView("s-1", "EVT-1"), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("listo"));
    expect(sdk.listCommandsSitesSiteIdCommandsGet).toHaveBeenCalledWith({
      path: { site_id: "s-1" },
    });
    expect(result.current).toEqual({
      kind: "listo",
      summary: { channels: ["siren"], acked: 1, total: 1 },
    });
  });

  it("sin evento en foco no hay nada que buscar: ni se pide, ni se confunde con «sin permiso»", () => {
    como("tenant_admin");
    const { result } = renderHook(() => useQuorumCommandsView("s-1", null), { wrapper });
    expect(result.current).toEqual({ kind: "sin-evento" });
    expect(sdk.listCommandsSitesSiteIdCommandsGet).not.toHaveBeenCalled();
  });

  it("un fallo de lectura es `error`, no un «no hubo actuación»", async () => {
    como("tenant_admin");
    sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
      data: undefined,
      response: { status: 500 },
    });
    const { result } = renderHook(() => useQuorumCommandsView("s-1", "EVT-1"), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("error"));
    expect(result.current).toEqual({
      kind: "error",
      error: "GET /sites/{id}/commands falló (500)",
    });
  });

  it("el envoltorio de siempre sigue devolviendo el resumen o null", async () => {
    como("soc_operator");
    const { result } = renderHook(() => useQuorumCommands("s-1", "EVT-1"), { wrapper });
    expect(result.current).toBeNull();
    expect(sdk.listCommandsSitesSiteIdCommandsGet).not.toHaveBeenCalled();
  });

  it("la puerta cuadra con `COMMAND_ROLES` para los roles web (medido en la auditoría)", () => {
    const leen = WEB_ROLES.filter((r) => puedeLeerComandos(ME_FIXTURES[r].allowed_actions)).sort();
    expect(leen).toEqual(["building_admin", "inspector", "takab_superadmin", "tenant_admin"]);
    // Sin sesión no hay lectura: default-deny.
    expect(puedeLeerComandos(null)).toBe(false);
  });
});
