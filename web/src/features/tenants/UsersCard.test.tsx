import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SiteOut, TenantOut, UserOut } from "@takab/sdk";

import { useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES, TENANT_ID } from "../../test-utils/meFixtures";
import { expectFourStates } from "../../test-utils/states";
import UsersCard from "./UsersCard";
import type { UsersData } from "./useUsers";

const mocks = vi.hoisted(() => ({
  useUsers: vi.fn(),
  useCreateUser: vi.fn(),
  useUpdateUser: vi.fn(),
  useDeleteUser: vi.fn(),
  useUserAction: vi.fn(),
}));

vi.mock("./useUsers", () => ({ ...mocks, USERS_STALE_MS: 300_000 }));

const SITE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1";
const SITE_B = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2";

const TENANT: TenantOut = {
  tenant_id: TENANT_ID,
  code: "TKB-001",
  name: "Industrias del Valle",
  isolation_mode: "logical",
  vertical: "Industrial",
  visibility: "private",
  status: "active",
  plan_code: "mvp",
  row_version: "774100",
  created_at: "2026-01-01T00:00:00Z",
};

const SITES = [
  { site_id: SITE_A, tenant_id: TENANT_ID, code: "MTY-01", name: "Torre Norte" },
  { site_id: SITE_B, tenant_id: TENANT_ID, code: "MTY-02", name: "Nave Sur" },
  { site_id: "zzz", tenant_id: "otro", code: "AJENO", name: "De otro cliente" },
] as unknown as SiteOut[];

function user(over: Partial<UserOut> = {}): UserOut {
  return {
    username: "u-1",
    email: "ana@cliente.mx",
    tenant_id: TENANT_ID,
    role: "soc_operator",
    site_scope: "*",
    zone_id: "",
    surface: "web",
    enabled: true,
    status: "CONFIRMED",
    created_at: null,
    updated_at: null,
    ...over,
  };
}

function usersData(over: Partial<UsersData> = {}): UsersData {
  return {
    users: [user()],
    backend: "cognito",
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function mutation(over: Record<string, unknown> = {}) {
  return {
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
    data: undefined,
    ...over,
  };
}

function seed(role: keyof typeof ME_FIXTURES): void {
  useSessionStore.setState({
    status: "authenticated",
    origin: "dev",
    idToken: "tok",
    me: ME_FIXTURES[role],
    error: null,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  seed("tenant_admin");
  mocks.useUsers.mockReturnValue(usersData());
  mocks.useCreateUser.mockReturnValue(mutation());
  mocks.useUpdateUser.mockReturnValue(mutation());
  mocks.useDeleteUser.mockReturnValue(mutation());
  mocks.useUserAction.mockReturnValue(mutation());
});

function renderCard(sites: SiteOut[] | undefined = SITES) {
  return render(<UsersCard tenant={TENANT} sites={sites} />);
}

/** `undefined` explícito: el default del helper NO debe suplantarlo. */
function renderCardWithoutSites() {
  return render(<UsersCard tenant={TENANT} sites={undefined} />);
}

describe("UsersCard · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((state) => {
      mocks.useUsers.mockReturnValue(
        usersData({
          loading: state === "loading",
          error: state === "error" ? "DIRECTORIO NO DISPONIBLE" : null,
          users: state === "empty" ? [] : [user()],
          dataUpdatedAt: state === "stale" ? Date.now() - 600_000 : Date.now(),
        }),
      );
      return <UsersCard tenant={TENANT} sites={SITES} />;
    });
  });
});

describe("UsersCard · nunca hay credenciales", () => {
  it("no existe ningún campo de contraseña en el formulario de alta", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const form = screen.getByTestId("user-create-form");
    expect(form.querySelector('input[type="password"]')).toBeNull();
    expect(within(form).queryByLabelText(/contrase/i)).toBeNull();
  });

  it("dice explícitamente que la clave la envía Cognito", () => {
    renderCard();
    expect(screen.getByText(/la genera y envía Cognito/i)).toBeTruthy();
  });
});

describe("UsersCard · el directorio simulado se ROTULA, no se disfraza", () => {
  it("con backend simulado avisa de que nada se escribe de verdad", () => {
    mocks.useUsers.mockReturnValue(usersData({ backend: "simulated" }));
    renderCard();
    expect(screen.getByTestId("users-backend").textContent).toMatch(/SIMULADO/);
  });

  it("con Cognito real lo dice igual de claro", () => {
    renderCard();
    expect(screen.getByTestId("users-backend").textContent).toBe("DIRECTORIO COGNITO");
  });
});

describe("UsersCard · escalada de privilegios", () => {
  it("un tenant_admin NO ve los roles de plataforma en el selector", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const options = within(screen.getByTestId("user-create-form"))
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).not.toContain("takab_superadmin");
    expect(options).not.toContain("takab_support");
    expect(options).toContain("soc_operator");
  });

  it("un superadmin sí puede otorgarlos", () => {
    seed("takab_superadmin");
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const options = within(screen.getByTestId("user-create-form"))
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).toContain("takab_superadmin");
  });

  it("`occupant` no es asignable desde aquí (vive en otro pool)", () => {
    seed("takab_superadmin");
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const options = within(screen.getByTestId("user-create-form"))
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).not.toContain("occupant");
  });
});

describe("UsersCard · alta", () => {
  it("un rol de tenant NO manda tenant_id: el servidor lo toma de su token", () => {
    const create = mutation();
    mocks.useCreateUser.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "nuevo@cliente.mx" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR E INVITAR" }));
    expect(create.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ email: "nuevo@cliente.mx", tenant_id: null, site_scope: "*" }),
      expect.anything(),
    );
  });

  it("un rol interno SÍ nombra el tenant destino (su RLS no lo detendría)", () => {
    seed("takab_superadmin");
    const create = mutation();
    mocks.useCreateUser.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "x@y.mx" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR E INVITAR" }));
    expect(create.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ tenant_id: TENANT_ID }),
      expect.anything(),
    );
  });

  it("un error del servidor se muestra, no se traga", () => {
    mocks.useCreateUser.mockReturnValue(mutation({ error: new Error("YA EXISTE · ese correo") }));
    renderCard();
    expect(screen.getByTestId("users-error").textContent).toMatch(/YA EXISTE/);
  });
});

describe("UsersCard · alcance por estación (desbloquea la Fase B de T-2.45)", () => {
  it("sólo ofrece las estaciones DE ESTE cliente", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    const editor = screen.getByTestId("user-editor");
    expect(within(editor).getByText(/MTY-01/)).toBeTruthy();
    expect(within(editor).queryByText(/AJENO/)).toBeNull();
  });

  it("marcar estaciones escribe custom:site_scope como CSV", () => {
    const update = mutation();
    mocks.useUpdateUser.mockReturnValue(update);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    fireEvent.click(screen.getByLabelText(/MTY-01/));
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR ALCANCE" }));
    expect(update.mutate).toHaveBeenCalledWith({
      username: "u-1",
      body: { site_scope: SITE_A },
    });
  });

  it("sin ninguna marcada, el alcance vuelve a `*` (no a cero sitios)", () => {
    const update = mutation();
    mocks.useUpdateUser.mockReturnValue(update);
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ site_scope: SITE_A })] }));
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    fireEvent.click(screen.getByLabelText(/MTY-01/)); // desmarca
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR ALCANCE" }));
    expect(update.mutate).toHaveBeenCalledWith({ username: "u-1", body: { site_scope: "*" } });
  });

  it("un alcance sin declarar se rotula así, jamás como 'cero estaciones'", () => {
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ site_scope: "" })] }));
    renderCard();
    expect(screen.getByTestId("user-row").textContent).toMatch(/SIN ALCANCE DECLARADO/);
  });

  it("sin catálogo de sitios cuenta los ids, no inventa nombres", () => {
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ site_scope: SITE_A })] }));
    renderCardWithoutSites();
    expect(screen.getByTestId("user-row").textContent).toMatch(/1 ESTACIÓN\(ES\)/);
  });
});

describe("UsersCard · baja reversible antes que definitiva", () => {
  it("DESHABILITAR manda enabled:false, no borra", () => {
    const update = mutation();
    mocks.useUpdateUser.mockReturnValue(update);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "DESHABILITAR" }));
    expect(update.mutate).toHaveBeenCalledWith({ username: "u-1", body: { enabled: false } });
  });

  it("un usuario deshabilitado se rotula como tal", () => {
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ enabled: false })] }));
    renderCard();
    expect(screen.getByTestId("user-row").textContent).toMatch(/DESHABILITADO/);
    expect(screen.getByRole("button", { name: "HABILITAR" })).toBeTruthy();
  });

  it("el acuse del reset se muestra sin ninguna credencial", () => {
    mocks.useUserAction.mockReturnValue(
      mutation({ data: { username: "u-1", action: "password_reset", detail: "Código enviado." } }),
    );
    renderCard();
    expect(screen.getByTestId("user-action-ack").textContent).toBe("Código enviado.");
  });
});
