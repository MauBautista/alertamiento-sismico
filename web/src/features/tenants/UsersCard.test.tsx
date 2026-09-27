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
  useAssignableRoles: vi.fn(),
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
    role: "gov_operator",
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
    truncated: false,
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

/**
 * [T-9.20 · D-42] Lo que responde `GET /users/assignable-roles`: los canónicos con
 * su rótulo, SIN los internos para un rol de cliente. La tarjeta pinta esto; ya no
 * tiene lista propia.
 */
const ASIGNABLES_CLIENTE = [
  { role: "tenant_admin", label: "ADMINISTRADOR" },
  { role: "gov_operator", label: "GOBIERNO" },
  { role: "inspector", label: "INSPECTOR" },
  { role: "brigadista", label: "BRIGADISTA" },
];
const ASIGNABLES_INTERNO = [
  { role: "takab_superadmin", label: "SUPERADMIN TAKAB" },
  { role: "takab_support", label: "SOPORTE TAKAB" },
  ...ASIGNABLES_CLIENTE,
];

function asignables(roles = ASIGNABLES_CLIENTE, over: Record<string, unknown> = {}) {
  return { roles, loading: false, error: null, ...over };
}

function seed(role: keyof typeof ME_FIXTURES): void {
  mocks.useAssignableRoles.mockReturnValue(
    asignables(ME_FIXTURES[role].is_internal ? ASIGNABLES_INTERNO : ASIGNABLES_CLIENTE),
  );
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
    expect(options).toContain("gov_operator");
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

// [T-9.20 · D-42] Los roles salen del servidor, con su rótulo; un rol viejo
// guardado en Cognito se pinta con SU rótulo histórico y no rompe el <select>.
describe("UsersCard · roles del servidor (D-42)", () => {
  function opcionesDelAlta(): { value: string; text: string }[] {
    const rol = within(screen.getByTestId("user-create-form")).getByLabelText("Rol");
    return within(rol)
      .getAllByRole("option")
      .map((o) => ({ value: (o as HTMLOptionElement).value, text: o.textContent ?? "" }));
  }

  it("el alta ofrece EXACTAMENTE lo que dice GET /users/assignable-roles, con su rótulo", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const elegibles = opcionesDelAlta().filter((o) => o.value !== "");
    expect(elegibles).toEqual(ASIGNABLES_CLIENTE.map((r) => ({ value: r.role, text: r.label })));
  });

  it("ningún rol retirado se ofrece para asignar aunque el servidor no lo filtrara", () => {
    mocks.useAssignableRoles.mockReturnValue(
      asignables([...ASIGNABLES_CLIENTE, { role: "soc_operator", label: "OPERACIÓN SOC" }]),
    );
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    expect(opcionesDelAlta().map((o) => o.value)).not.toContain("soc_operator");
  });

  it("el alta NO arranca con un rol elegido: no se crea nadie hasta escoger", () => {
    const create = mutation();
    mocks.useCreateUser.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "a@b.mx" } });
    expect(screen.getByRole("button", { name: "CREAR E INVITAR" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "CREAR E INVITAR" }));
    expect(create.mutate).not.toHaveBeenCalled();
  });

  it("si no se pudieron leer los roles, el alta lo DICE y no deja crear", () => {
    mocks.useAssignableRoles.mockReturnValue(
      asignables([], { error: "ROLES NO DISPONIBLES (HTTP 503)" }),
    );
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    expect(screen.getByTestId("assignable-roles-error").textContent).toMatch(/503/);
    expect(screen.getByRole("button", { name: "CREAR E INVITAR" })).toBeDisabled();
  });

  it("con el catálogo leído y VACÍO lo dice, en vez de pedir que elijas de la nada", () => {
    mocks.useAssignableRoles.mockReturnValue(asignables([]));
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    const opciones = opcionesDelAlta();
    expect(opciones).toEqual([{ value: "", text: "SIN ROLES QUE PUEDAS ASIGNAR" }]);
  });

  it("la fila de un usuario con rol viejo lleva su rótulo histórico, no el id ni el del heredero", () => {
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ role: "soc_operator" })] }));
    renderCard();
    const fila = screen.getByTestId("user-row");
    expect(fila.textContent).toMatch(/OPERACIÓN SOC \(ROL RETIRADO\)/);
    expect(fila.textContent).not.toMatch(/soc_operator/);
    expect(fila.textContent).not.toMatch(/ADMINISTRADOR/);
  });

  it("editar a ese usuario no rompe el <select>: su rol viejo está, marcado y no elegible", () => {
    const update = mutation();
    mocks.useUpdateUser.mockReturnValue(update);
    mocks.useUsers.mockReturnValue(usersData({ users: [user({ role: "building_admin" })] }));
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    const select = screen.getByLabelText("Rol") as HTMLSelectElement;
    // Muestra lo que TIENE, no la primera opción de la lista (eso sería mentir).
    expect(select.value).toBe("building_admin");
    const actual = [...select.options].find((o) => o.value === "building_admin");
    expect(actual?.textContent).toBe("ADMINISTRACIÓN DEL INMUEBLE (ROL RETIRADO)");
    expect(actual?.disabled).toBe(true);
    // Y migrarlo a un canónico es el camino normal, con su confirmación.
    fireEvent.change(select, { target: { value: "tenant_admin" } });
    fireEvent.click(screen.getByRole("button", { name: /CAMBIAR ROL A ADMINISTRADOR/ }));
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(update.mutate).toHaveBeenCalledWith({
      username: "u-1",
      body: { role: "tenant_admin" },
    });
  });
});

describe("UsersCard · alta", () => {
  it("un rol de tenant NO manda tenant_id: el servidor lo toma de su token", () => {
    const create = mutation();
    mocks.useCreateUser.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "+ NUEVO USUARIO" }));
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "nuevo@cliente.mx" } });
    fireEvent.change(within(screen.getByTestId("user-create-form")).getByLabelText("Rol"), {
      target: { value: "gov_operator" },
    });
    fireEvent.click(screen.getByRole("button", { name: "CREAR E INVITAR" }));
    expect(create.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "nuevo@cliente.mx",
        role: "gov_operator",
        tenant_id: null,
        site_scope: "*",
      }),
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
    fireEvent.change(within(screen.getByTestId("user-create-form")).getByLabelText("Rol"), {
      target: { value: "takab_support" },
    });
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
    // [A-107] Dos pasos: el primer clic ARMA, el segundo confirma.
    fireEvent.click(screen.getByRole("button", { name: "DESHABILITAR" }));
    expect(update.mutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
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

// [A-018 · T-8.09] `GET /users` sólo acota por tenant a los roles de cliente; a
// un rol interno le devuelve el pool ENTERO. La tarjeta dice «QUIÉN ENTRA A
// {cliente}» y pintaba a los usuarios de TODOS los clientes debajo.
describe("UsersCard · sólo los usuarios DE ESTE cliente", () => {
  it("un superadmin no ve en la ficha de un cliente a los usuarios de otro", () => {
    seed("takab_superadmin");
    mocks.useUsers.mockReturnValue(
      usersData({
        users: [
          user({ username: "u-1", email: "ana@cliente.mx" }),
          user({ username: "u-9", email: "otro@ajeno.mx", tenant_id: "otro-tenant" }),
        ],
      }),
    );
    renderCard();
    const filas = screen.getAllByTestId("user-row");
    expect(filas).toHaveLength(1);
    expect(filas[0].textContent).toMatch(/ana@cliente\.mx/);
    expect(screen.queryByText(/otro@ajeno\.mx/)).toBeNull();
  });

  it("si en el directorio sólo hay usuarios de OTROS clientes, esta ficha está vacía", () => {
    seed("takab_superadmin");
    mocks.useUsers.mockReturnValue(
      usersData({ users: [user({ username: "u-9", tenant_id: "otro-tenant" })] }),
    );
    renderCard();
    expect(screen.getByText("SIN USUARIOS EN ESTE CLIENTE")).toBeInTheDocument();
  });

  // [A-106] Si el directorio se cortó por el tope de páginas, la lista no puede
  // presentarse como completa: «SIN USUARIOS» con usuarios existentes es el cero
  // tranquilizador de siempre.
  it("una lista cortada por el tope de páginas se declara incompleta", () => {
    mocks.useUsers.mockReturnValue(usersData({ truncated: true }));
    renderCard();
    expect(screen.getByTestId("users-truncated").textContent).toMatch(/INCOMPLETA/);
  });

  it("una lista completa no inventa el aviso", () => {
    renderCard();
    expect(screen.queryByTestId("users-truncated")).toBeNull();
  });
});

// [A-107 · T-8.09] DAR DE BAJA (irreversible) y el cambio de rol se ejecutaban
// con un solo clic, sin confirmación.
describe("UsersCard · lo irreversible pide confirmación", () => {
  it("DAR DE BAJA arma en el primer clic y sólo borra en el segundo", () => {
    const remove = mutation();
    mocks.useDeleteUser.mockReturnValue(remove);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    fireEvent.click(screen.getByRole("button", { name: "DAR DE BAJA" }));
    expect(remove.mutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(remove.mutate).toHaveBeenCalledWith("u-1");
  });

  it("elegir otro rol NO lo aplica: hay que confirmarlo", () => {
    const update = mutation();
    mocks.useUpdateUser.mockReturnValue(update);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "inspector" } });
    expect(update.mutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CAMBIAR ROL A INSPECTOR/ }));
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(update.mutate).toHaveBeenCalledWith({ username: "u-1", body: { role: "inspector" } });
  });
});

// [A-108 · T-8.09] Un admin podía deshabilitarse o quitarse su propio rol desde
// su propia fila, y quedarse fuera de la consola a mitad de una demostración.
describe("UsersCard · la propia cuenta no se desarma desde aquí", () => {
  it("en MI fila no se ofrece deshabilitar, cambiar rol ni dar de baja", () => {
    // `sub` de la fixture de tenant_admin: la cuenta en sesión.
    mocks.useUsers.mockReturnValue(
      usersData({
        users: [user({ username: ME_FIXTURES.tenant_admin.sub, role: "tenant_admin" })],
      }),
    );
    renderCard();
    expect(screen.getByRole("button", { name: "DESHABILITAR" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    expect(screen.getByLabelText("Rol")).toBeDisabled();
    expect(screen.getByLabelText("Superficie")).toBeDisabled();
    expect(screen.getByRole("button", { name: "DAR DE BAJA" })).toBeDisabled();
    expect(screen.getByTestId("user-row").textContent).toMatch(/TU CUENTA/);
  });

  it("NO-VACUIDAD: en la fila de otro sí se ofrece", () => {
    renderCard();
    expect(screen.getByRole("button", { name: "DESHABILITAR" })).toBeEnabled();
  });
});
