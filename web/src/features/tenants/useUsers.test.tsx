// [A-106 · T-8.09] `GET /users` pagina con el `PaginationToken` de Cognito y la
// consola pedía SOLO la primera página: el directorio se truncaba a 50, y como
// Cognito no filtra por atributos custom, un cliente cuyos usuarios cayeran en
// la segunda página veía «SIN USUARIOS» con usuarios existentes.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  createUserUsersPost: vi.fn(),
  deleteUserUsersUsernameDelete: vi.fn(),
  listUsersUsersGet: vi.fn(),
  resendInvitationUsersUsernameResendInvitationPost: vi.fn(),
  resetPasswordUsersUsernameResetPasswordPost: vi.fn(),
  updateUserUsersUsernamePatch: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { USERS_MAX_PAGES, userErrorMessage, useUsers } from "./useUsers";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function u(username: string) {
  return {
    username,
    email: `${username}@x.mx`,
    tenant_id: "t-1",
    role: "soc_operator",
    site_scope: "*",
    zone_id: "",
    surface: "web",
    enabled: true,
    status: "CONFIRMED",
  };
}

beforeEach(() => vi.clearAllMocks());

describe("useUsers · sigue el cursor hasta el final", () => {
  it("junta TODAS las páginas, no sólo la primera", async () => {
    sdk.listUsersUsersGet
      .mockResolvedValueOnce({
        data: { items: [u("a")], next_cursor: "p2", backend: "cognito" },
        response: { status: 200 },
      })
      .mockResolvedValueOnce({
        data: { items: [], next_cursor: "p3", backend: "cognito" },
        response: { status: 200 },
      })
      .mockResolvedValueOnce({
        data: { items: [u("b")], next_cursor: null, backend: "cognito" },
        response: { status: 200 },
      });
    const { result } = renderHook(() => useUsers(true), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.users.map((x) => x.username)).toEqual(["a", "b"]);
    expect(result.current.truncated).toBe(false);
    // El cursor de cada página viaja en la siguiente petición.
    expect(sdk.listUsersUsersGet.mock.calls[1][0].query.cursor).toBe("p2");
    expect(sdk.listUsersUsersGet.mock.calls[2][0].query.cursor).toBe("p3");
  });

  it("con un directorio sin fin se detiene en el tope y lo DECLARA", async () => {
    sdk.listUsersUsersGet.mockResolvedValue({
      data: { items: [u("a")], next_cursor: "otra", backend: "cognito" },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useUsers(true), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(sdk.listUsersUsersGet).toHaveBeenCalledTimes(USERS_MAX_PAGES);
    expect(result.current.truncated).toBe(true);
  });
});

// [A-108] El 409 de «no puedes darte de baja a ti mismo» se leía «YA EXISTE ·
// ese correo ya tiene una cuenta», que es el 409 del ALTA.
describe("userErrorMessage · el 409 depende de la operación", () => {
  it("en el alta, YA EXISTE", () => {
    expect(userErrorMessage(409, "create")).toMatch(/YA EXISTE/);
  });

  it("en la baja NO dice YA EXISTE, y lleva lo que dijo el servidor", () => {
    const m = userErrorMessage(409, "delete", "no puedes darte de baja a ti mismo");
    expect(m).not.toMatch(/YA EXISTE/);
    expect(m).toMatch(/no puedes darte de baja a ti mismo/);
  });
});
