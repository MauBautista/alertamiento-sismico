// [A-019 · T-8.09] Después de SILENCIAR SIRENA el panel decía «SIRENA SONANDO ·
// ACUSADA POR EL EDGE» y volvía a ofrecer SILENCIAR: `phaseOf` miraba el STATUS
// del comando y no su ACCIÓN, así que el acuse del silencio se pintaba igual que
// el acuse del arranque. Frente a un cliente, la pantalla afirmaba lo contrario
// de lo que acababa de pasar sobre un actuador de vida.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  issueCommandSitesSiteIdCommandsPost: vi.fn(),
  listCommandsSitesSiteIdCommandsGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { useSirenTest } from "./useSirenTest";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function cmd(id: string, action: "activate" | "deactivate", status: string) {
  return {
    command_id: id,
    tenant_id: "t-1",
    site_id: "s-1",
    gateway_id: "g-1",
    issued_by: "u-1",
    channel: "siren",
    action,
    event_id: null,
    nonce: `${id}-nonce-0123456789`,
    issued_at: "2026-09-23T10:41:00Z",
    expires_at: "2026-09-23T10:41:30Z",
    status,
    ack: null,
    error: null,
  };
}

/** El listado que devolverá el servidor a partir de ahora. */
function listado(...items: ReturnType<typeof cmd>[]) {
  sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
    data: { items },
    response: { status: 200 },
  });
}

async function sirenaSonando() {
  sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValueOnce({
    data: cmd("c-1", "activate", "pending"),
    response: { status: 201 },
  });
  listado(cmd("c-1", "activate", "acked"));
  const hook = renderHook(() => useSirenTest("s-1"), { wrapper });
  act(() => hook.result.current.activate());
  await waitFor(() => expect(hook.result.current.phase).toBe("acked"));
  return hook;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useSirenTest · las fases dependen de la ACCIÓN, no sólo del estado", () => {
  it("el acuse del SILENCIO no se pinta como sirena sonando", async () => {
    const hook = await sirenaSonando();

    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValueOnce({
      data: cmd("c-2", "deactivate", "pending"),
      response: { status: 201 },
    });
    listado(cmd("c-2", "deactivate", "acked"), cmd("c-1", "activate", "acked"));
    act(() => hook.result.current.deactivate());

    await waitFor(() => expect(hook.result.current.phase).toBe("silenced"));
    expect(hook.result.current.phase).not.toBe("acked");
  });

  it("la orden de silencio EN VUELO no dice «esperando» como si fuera un arranque", async () => {
    const hook = await sirenaSonando();

    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValueOnce({
      data: cmd("c-2", "deactivate", "pending"),
      response: { status: 201 },
    });
    listado(cmd("c-2", "deactivate", "pending"), cmd("c-1", "activate", "acked"));
    act(() => hook.result.current.deactivate());

    await waitFor(() => expect(hook.result.current.phase).toBe("silence_issued"));
  });

  it("un silencio que el gabinete NO confirmó no se da por hecho", async () => {
    const hook = await sirenaSonando();

    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValueOnce({
      data: cmd("c-2", "deactivate", "pending"),
      response: { status: 201 },
    });
    listado(cmd("c-2", "deactivate", "expired"), cmd("c-1", "activate", "acked"));
    act(() => hook.result.current.deactivate());

    // La sirena PUEDE seguir sonando: ni «silenciada» ni «en reposo».
    await waitFor(() => expect(hook.result.current.phase).toBe("silence_unconfirmed"));
  });

  it("si la orden de silencio ni siquiera sale, la sirena sigue contando como sonando", async () => {
    const hook = await sirenaSonando();

    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "rate limit" },
      response: { status: 429 },
    });
    act(() => hook.result.current.deactivate());

    await waitFor(() => expect(hook.result.current.phase).toBe("silence_failed"));
    expect(hook.result.current.detail).toMatch(/429/);
  });

  it("NO-VACUIDAD: el arranque sigue siendo el arranque", async () => {
    const hook = await sirenaSonando();
    expect(hook.result.current.phase).toBe("acked");
  });
});
