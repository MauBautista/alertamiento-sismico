import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GatewayConfigStateOut, RuleSetOut, SiteOut, TenantOut } from "@takab/sdk";

import { useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES, TENANT_ID } from "../../test-utils/meFixtures";
import { expectFourStates } from "../../test-utils/states";
import TenantsPage from "./TenantsPage";
import type { CreateTenantState, TenantsData, TenantSyncData } from "./useTenants";
import type { PublishState } from "./useRuleSetPublish";

const mocks = vi.hoisted(() => ({
  useTenants: vi.fn(),
  useTenantSync: vi.fn(),
  useTenantGateways: vi.fn(),
  useRuleSetPublish: vi.fn(),
  useCreateTenant: vi.fn(),
}));

vi.mock("./useTenants", () => ({
  useTenants: mocks.useTenants,
  useTenantSync: mocks.useTenantSync,
  useTenantGateways: mocks.useTenantGateways,
  useCreateTenant: mocks.useCreateTenant,
  TENANTS_STALE_MS: 120_000,
}));
vi.mock("./useRuleSetPublish", () => ({ useRuleSetPublish: mocks.useRuleSetPublish }));
// Stub: aísla el gating de la tarjeta de su lógica (probada en VisibilityCard.test).
vi.mock("./VisibilityCard", () => ({ default: () => "VISIBILITY_CARD_STUB" }));

const TENANT: TenantOut = {
  tenant_id: TENANT_ID, // el tenant de la sesión: es el único editable
  code: "TKB-001",
  name: "Industrias del Valle",
  isolation_mode: "logical",
  vertical: "Industrial",
  visibility: "private",
  status: "active",
  plan_code: "mvp",
  created_at: "2026-01-01T00:00:00Z",
};

const DEDICATED: TenantOut = {
  ...TENANT,
  tenant_id: "t-2",
  code: "TKB-002",
  name: "Secretaría de Salud",
  isolation_mode: "dedicated",
  vertical: null,
};

const RULE_SET: RuleSetOut = {
  rule_set_id: "rs-1",
  tenant_id: TENANT_ID,
  scope_type: "tenant",
  scope_id: TENANT_ID,
  version: 4,
  is_active: true,
  config: {
    edge: { thresholds: { pga_trip_g: 0.09 }, sample_rate: 100 },
    notifications: { webhook: { url: "https://x/y", secret: "s3cr3t" } },
  },
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
};

/** rule_set del tenant AJENO: existe, pero la sesión no puede escribirlo. */
const RULE_SET_FOREIGN: RuleSetOut = {
  ...RULE_SET,
  rule_set_id: "rs-2",
  tenant_id: "t-2",
  scope_id: "t-2",
};

const SITES: SiteOut[] = [
  {
    site_id: "s-1",
    tenant_id: TENANT_ID,
    code: "CHL",
    name: "Cholula",
    criticality: "high",
    lat: 19,
    lon: -98,
    timezone: "America/Mexico_City",
    status: "active",
    row_version: "1",
    created_at: "2026-01-01T00:00:00Z",
  },
];

function tenantsData(over: Partial<TenantsData> = {}): TenantsData {
  return {
    tenants: [TENANT, DEDICATED],
    ruleSets: [RULE_SET, RULE_SET_FOREIGN],
    sites: SITES,
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ruleSetsError: null,
    ...over,
  };
}

function syncData(over: Partial<TenantSyncData> = {}): TenantSyncData {
  return { states: [], loading: false, error: null, ...over };
}

function publishState(over: Partial<PublishState> = {}): PublishState {
  return {
    apply: vi.fn(),
    pending: false,
    error: null,
    conflict: false,
    publishedVersion: null,
    reset: vi.fn(),
    ...over,
  };
}

function createState(over: Partial<CreateTenantState> = {}): CreateTenantState {
  return { create: vi.fn(), pending: false, error: null, createdId: null, reset: vi.fn(), ...over };
}

function cfg(over: Partial<GatewayConfigStateOut> = {}): GatewayConfigStateOut {
  return {
    gateway_id: "g-1",
    version: 4,
    published_at: "2026-07-08T10:00:00Z",
    sig_fingerprint: "abc",
    in_sync: true,
    has_edge_config: true,
    is_syncable: true,
    ...over,
  };
}

function seedRole(role: keyof typeof ME_FIXTURES): void {
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
  seedRole("tenant_admin");
  mocks.useTenants.mockReturnValue(tenantsData());
  mocks.useTenantSync.mockReturnValue(syncData());
  mocks.useTenantGateways.mockReturnValue({ gatewayIds: [], loading: false, error: null });
  mocks.useRuleSetPublish.mockReturnValue(publishState());
  mocks.useCreateTenant.mockReturnValue(createState());
});

describe("TenantsPage · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((state) => {
      mocks.useTenants.mockReturnValue(
        tenantsData({
          loading: state === "loading",
          error: state === "error" ? "GET /tenants falló (500)" : null,
          tenants: state === "empty" ? [] : [TENANT],
          dataUpdatedAt: state === "stale" ? Date.now() - 200_000 : Date.now(),
        }),
      );
      return <TenantsPage />;
    });
  });
});

describe("TenantsPage · aislamiento visible (dato real, no infra inventada)", () => {
  it("pinta isolation_mode tal cual del CHECK del DDL", () => {
    render(<TenantsPage />);
    expect(screen.getByText("LÓGICO")).toBeTruthy();
    expect(screen.getByText("DEDICADO")).toBeTruthy();
  });

  it("NO afirma cosas de infra que ninguna API respalda", () => {
    render(<TenantsPage />);
    expect(screen.queryByText(/Schema por tenant/i)).toBeNull();
    expect(screen.queryByText(/AES-256/i)).toBeNull();
    expect(screen.queryByText(/Llaves KMS/i)).toBeNull();
  });

  it("tenant_admin (sin manage_tenants) no ve el botón de alta de clientes", () => {
    render(<TenantsPage />); // beforeEach siembra tenant_admin
    expect(screen.queryByRole("button", { name: /NUEVO CLIENTE/ })).toBeNull();
  });

  it("no inventa una cuenta de usuarios (no hay endpoint)", () => {
    render(<TenantsPage />);
    expect(screen.queryByText(/usuarios/i)).toBeNull();
  });

  it("sitios sin cargar ⇒ S/D, nunca 0", () => {
    mocks.useTenants.mockReturnValue(tenantsData({ sites: undefined }));
    render(<TenantsPage />);
    expect(screen.getAllByText(/S\/D/).length).toBeGreaterThan(0);
  });

  it("vertical nulo ⇒ SIN CLASIFICAR", () => {
    render(<TenantsPage />);
    expect(screen.getAllByText(/SIN CLASIFICAR/).length).toBeGreaterThan(0);
  });
});

describe("TenantsPage · alta de clientes (T-1.72, solo manage_tenants)", () => {
  it("el superadmin ve el botón NUEVO CLIENTE y abre el formulario", () => {
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    fireEvent.click(screen.getByRole("button", { name: /NUEVO CLIENTE/ }));
    expect(screen.getByTestId("tenant-create-form")).toBeTruthy();
  });

  it("enviar el formulario crea el cliente con el cuerpo tecleado", () => {
    const create = vi.fn();
    mocks.useCreateTenant.mockReturnValue(createState({ create }));
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    fireEvent.click(screen.getByRole("button", { name: /NUEVO CLIENTE/ }));

    fireEvent.change(screen.getByLabelText(/Código único/), { target: { value: "HOSP-1" } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: "Hospital Uno" } });
    fireEvent.change(screen.getByLabelText(/Vertical/), { target: { value: "salud" } });
    fireEvent.click(screen.getByRole("button", { name: /CREAR CLIENTE/ }));

    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith({
      code: "HOSP-1",
      name: "Hospital Uno",
      vertical: "salud",
      plan_code: "mvp",
      isolation_mode: "logical",
    });
  });

  it("un error del servidor (p.ej. code duplicado) se muestra, no se traga", () => {
    mocks.useCreateTenant.mockReturnValue(
      createState({ error: "ya existe un registro con ese identificador único" }),
    );
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    fireEvent.click(screen.getByRole("button", { name: /NUEVO CLIENTE/ }));
    expect(screen.getByText(/identificador único/)).toBeTruthy();
  });

  it("sin código o nombre el botón CREAR queda deshabilitado", () => {
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    fireEvent.click(screen.getByRole("button", { name: /NUEVO CLIENTE/ }));
    expect(screen.getByRole("button", { name: /CREAR CLIENTE/ }).hasAttribute("disabled")).toBe(
      true,
    );
  });
});

describe("TenantsPage · visibilidad configurable (T-1.73, solo manage_visibility)", () => {
  it("el superadmin ve la tarjeta de visibilidad en el detalle", () => {
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    expect(screen.getByText("VISIBILITY_CARD_STUB")).toBeTruthy();
  });

  it("tenant_admin (sin manage_visibility) NO ve la tarjeta", () => {
    render(<TenantsPage />); // beforeEach siembra tenant_admin
    expect(screen.queryByText("VISIBILITY_CARD_STUB")).toBeNull();
  });
});

describe("TenantsPage · umbrales del edge", () => {
  it("cuatro sliders: cautela y disparo para PGA y PGV (el ThresholdBand real)", () => {
    render(<TenantsPage />);
    expect(screen.getByLabelText(/PGA · banda de cautela/)).toBeTruthy();
    expect(screen.getByLabelText(/PGA · banda de disparo/)).toBeTruthy();
    expect(screen.getByLabelText(/PGV · banda de cautela/)).toBeTruthy();
    expect(screen.getByLabelText(/PGV · banda de disparo/)).toBeTruthy();
  });

  it("un umbral ausente en el config se rotula DEFAULT DEL EDGE", () => {
    render(<TenantsPage />);
    // pga_trip_g SÍ está en el config; pga_watch_g no.
    expect(screen.getByText(/PGA · banda de cautela · DEFAULT DEL EDGE/)).toBeTruthy();
    expect(screen.queryByText(/PGA · banda de disparo · DEFAULT DEL EDGE/)).toBeNull();
  });

  it("sin rule_set activo y SIN edit_thresholds: empty honesto, sin editor (T-1.54)", () => {
    seedRole("takab_support"); // ve /tenants pero no edita umbrales
    mocks.useTenants.mockReturnValue(tenantsData({ ruleSets: [] }));
    render(<TenantsPage />);
    expect(screen.getByText(/NO TIENE RULE_SET ACTIVO/)).toBeTruthy();
    expect(screen.queryByTestId("create-v1-banner")).toBeNull();
  });

  it("sin rule_set activo CON edit_thresholds: editor sembrado con defaults + banner de crear v1 (T-1.54)", () => {
    // tenant_admin del tenant propio: el camino de creación (baseVersion:null)
    // existía pero quedaba enterrado tras el empty.
    mocks.useTenants.mockReturnValue(tenantsData({ ruleSets: [] }));
    render(<TenantsPage />);
    expect(screen.getByTestId("create-v1-banner")).toHaveTextContent("AJUSTA Y PUBLICA v1");
    expect(screen.getByLabelText(/PGA · banda de disparo/)).toBeTruthy(); // editor visible
    expect(screen.getByText(/PGA · banda de disparo · DEFAULT DEL EDGE/)).toBeTruthy();
    expect(
      screen.queryByText(/NO TIENE RULE_SET ACTIVO · EL GABINETE APLICA SUS DEFAULTS$/),
    ).toBeNull();
  });

  it("si /rule-sets falla se reporta como error, no como 'sin umbrales'", () => {
    mocks.useTenants.mockReturnValue(
      tenantsData({ ruleSets: undefined, ruleSetsError: "GET /rule-sets falló (500)" }),
    );
    render(<TenantsPage />);
    expect(screen.queryByText(/NO TIENE RULE_SET ACTIVO/)).toBeNull();
    expect(screen.getByText(/rule-sets falló/)).toBeTruthy();
  });
});

describe("TenantsPage · cascada de notificación", () => {
  it("orden fijo del servidor, con los nombres REALES (webhook, no 'api')", () => {
    render(<TenantsPage />);
    expect(screen.getByTestId("channel-webhook")).toBeTruthy();
    expect(screen.getByTestId("channel-whatsapp")).toBeTruthy();
    expect(screen.getByTestId("channel-sms")).toBeTruthy();
    expect(screen.getByTestId("channel-email")).toBeTruthy();
    expect(screen.getByText(/ORDEN Y TIEMPOS FIJOS/)).toBeTruthy();
  });

  it("el secret del webhook jamás aparece en el DOM", () => {
    const { container } = render(<TenantsPage />);
    expect(container.innerHTML).not.toContain("s3cr3t");
  });

  it("habilitar un canal sin destino lo marca INCOMPLETO y bloquea el aplicar", () => {
    render(<TenantsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Habilitar SMS/ }));
    expect(screen.getByText(/INCOMPLETO · sin destino/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/sms.*omitiría/);
    expect(
      screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("sin ningún canal con destino advierte TENANT DESPROTEGIDO", () => {
    mocks.useTenants.mockReturnValue(
      tenantsData({ ruleSets: [{ ...RULE_SET, config: { notifications: {} } }] }),
    );
    render(<TenantsPage />);
    expect(screen.getByText(/TENANT DESPROTEGIDO/)).toBeTruthy();
  });
});

describe("TenantsPage · sync firmada (nunca se afirma sin evidencia)", () => {
  it("sin config-state todavía ⇒ ESTADO DE SYNC DESCONOCIDO", () => {
    mocks.useTenantSync.mockReturnValue(syncData({ states: undefined }));
    render(<TenantsPage />);
    expect(screen.getByText(/ESTADO DE SYNC DESCONOCIDO/)).toBeTruthy();
    expect(screen.queryByText(/APLICADA EN TODOS LOS GABINETES/)).toBeNull();
  });

  it("in_sync en todos ⇒ CONFIG FIRMADA APLICADA, identificada por su HUELLA", () => {
    mocks.useTenantSync.mockReturnValue(syncData({ states: [cfg({ sig_fingerprint: "abc123" })] }));
    render(<TenantsPage />);
    expect(screen.getByText(/CONFIG FIRMADA APLICADA EN TODOS LOS GABINETES/)).toBeTruthy();
    expect(screen.getByText(/firma abc123/)).toBeTruthy();
  });

  it("no muestra gateway_config_state.version junto a rule_sets.version (contadores distintos)", () => {
    mocks.useTenantSync.mockReturnValue(syncData({ states: [cfg({ version: 3 })] }));
    mocks.useRuleSetPublish.mockReturnValue(publishState({ publishedVersion: 8 }));
    render(<TenantsPage />);
    expect(screen.queryByText(/v3 en el edge/)).toBeNull();
    expect(screen.getByText(/rule_set v8 publicada/)).toBeTruthy();
  });

  it("si el poll de config-state falla, NO se afirma nada del sync", () => {
    mocks.useTenantSync.mockReturnValue(
      syncData({ states: [cfg()], error: "config-state falló (500)" }),
    );
    render(<TenantsPage />);
    expect(screen.queryByText(/APLICADA EN TODOS LOS GABINETES/)).toBeNull();
    expect(screen.getByText(/ESTADO DE SYNC DESCONOCIDO/)).toBeTruthy();
  });

  it("mientras el poll está en vuelo tampoco", () => {
    mocks.useTenantSync.mockReturnValue(syncData({ states: [cfg()], loading: true }));
    render(<TenantsPage />);
    expect(screen.getByText(/ESTADO DE SYNC DESCONOCIDO/)).toBeTruthy();
  });

  it("publicado pero sin llegar ⇒ PENDIENTE DE SYNC (publish sólo registra intención)", () => {
    mocks.useTenantSync.mockReturnValue(syncData({ states: [cfg({ in_sync: false })] }));
    render(<TenantsPage />);
    expect(screen.getByText(/PENDIENTE DE SYNC/)).toBeTruthy();
  });

  it("un gabinete al día y otro no ⇒ SYNC PARCIAL, jamás 'sincronizado'", () => {
    mocks.useTenantSync.mockReturnValue(
      syncData({ states: [cfg(), cfg({ gateway_id: "g-2", in_sync: false })] }),
    );
    render(<TenantsPage />);
    expect(screen.getByText(/SYNC PARCIAL/)).toBeTruthy();
    expect(screen.queryByText(/APLICADA EN TODOS/)).toBeNull();
  });

  it("no promete '≤60s firmado JWT' como el mockup (es HMAC y lo hace el worker)", () => {
    render(<TenantsPage />);
    expect(screen.queryByText(/firmado JWT/i)).toBeNull();
  });
});

describe("TenantsPage · edición gateada por allowed_actions.edit_thresholds", () => {
  it("tenant_admin puede editar y aplicar tras cambiar un umbral", () => {
    const publish = publishState();
    mocks.useRuleSetPublish.mockReturnValue(publish);
    render(<TenantsPage />);

    const apply = screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ });
    expect(apply.hasAttribute("disabled")).toBe(true); // nada sucio aún

    fireEvent.change(screen.getByLabelText(/PGA · banda de disparo/), { target: { value: "0.1" } });
    expect(screen.getByText(/CAMBIOS SIN APLICAR/)).toBeTruthy();
    expect(apply.hasAttribute("disabled")).toBe(false);

    fireEvent.click(apply); // arma
    fireEvent.click(apply); // confirma
    expect(publish.apply).toHaveBeenCalledTimes(1);
    const call = (publish.apply as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(call.tenantId).toBe(TENANT_ID);
    // El PUT preserva lo que la pantalla no toca y escribe en config.edge.thresholds.
    expect(call.config.edge.sample_rate).toBe(100);
    expect(call.config.edge.thresholds.pga_trip_g).toBeCloseTo(0.1);
    // El secret NO viaja: el servidor lo redacta al leer y lo reinyecta al escribir.
    expect(JSON.stringify(call.config)).not.toContain("s3cr3t");
    expect(call.config.notifications.webhook.url).toBe("https://x/y");
    // Y se manda la base sobre la que se editó: sin ella el PUT pisaría a ciegas.
    expect(call.baseVersion).toBe(4);
  });

  it("takab_support (lectura) no edita: sliders y canales deshabilitados", () => {
    seedRole("takab_support");
    render(<TenantsPage />);
    expect(screen.getByLabelText(/PGA · banda de disparo/).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: /Habilitar SMS/ }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(
      screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("una banda de cautela por encima de la de disparo bloquea el aplicar", () => {
    render(<TenantsPage />);
    fireEvent.change(screen.getByLabelText(/PGA · banda de cautela/), { target: { value: "0.2" } });
    expect(screen.getByRole("alert").textContent).toMatch(/cautela no puede superar/);
    expect(
      screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("RESTAURAR descarta el borrador", () => {
    render(<TenantsPage />);
    fireEvent.change(screen.getByLabelText(/PGA · banda de disparo/), { target: { value: "0.1" } });
    fireEvent.click(screen.getByRole("button", { name: /RESTAURAR/ }));
    expect(screen.queryByText(/CAMBIOS SIN APLICAR/)).toBeNull();
  });
});

describe("TenantsPage · un tenant ajeno es SÓLO LECTURA (el servidor lo rechazaría)", () => {
  it("superadmin viendo otro tenant no puede editar, y se le explica por qué", () => {
    seedRole("takab_superadmin"); // tenant de sesión = TENANT_ID
    render(<TenantsPage />);

    // Selecciona el tenant AJENO (t-2).
    fireEvent.click(screen.getByRole("button", { name: /Secretaría de Salud/ }));

    expect(screen.getByText(/SÓLO LECTURA/)).toBeTruthy();
    expect(screen.getByLabelText(/PGA · banda de disparo/).hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("…y sobre su PROPIO tenant sí edita", () => {
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    expect(screen.getByLabelText(/PGA · banda de disparo/).hasAttribute("disabled")).toBe(false);
  });

  it("nunca emite un PUT para un tenant que no es el de la sesión", () => {
    const publish = publishState();
    mocks.useRuleSetPublish.mockReturnValue(publish);
    seedRole("takab_superadmin");
    render(<TenantsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Secretaría de Salud/ }));
    const apply = screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ });
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(publish.apply).not.toHaveBeenCalled();
  });
});

describe("TenantsPage · concurrencia y arrastre de estado entre tenants", () => {
  it("cambiar de tenant OLVIDA la publicación anterior (no dice 'vN publicada' de otro)", () => {
    const publish = publishState({ publishedVersion: 7, reset: vi.fn() });
    mocks.useRuleSetPublish.mockReturnValue(publish);
    seedRole("takab_superadmin");
    render(<TenantsPage />);
    expect(screen.getByText(/rule_set v7 publicada/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Secretaría de Salud/ }));
    expect(publish.reset).toHaveBeenCalled();
  });

  it("un 409 del servidor se explica en vez de perder el trabajo", () => {
    mocks.useRuleSetPublish.mockReturnValue(
      publishState({
        conflict: true,
        error: "El rule_set cambió en el servidor mientras editabas. Recarga y reintenta.",
      }),
    );
    render(<TenantsPage />);
    expect(screen.getByText(/cambió en el servidor mientras editabas/)).toBeTruthy();
  });
});

describe("TenantsPage · una publicación ajena no pisa la edición sin guardar", () => {
  it("avisa y CONSERVA el borrador del operador", () => {
    mocks.useTenants.mockReturnValue(tenantsData());
    const { rerender } = render(<TenantsPage />);

    // El operador edita y NO aplica.
    const slider = screen.getByLabelText(/PGA · banda de disparo/) as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "0.15" } });
    expect(screen.getByText(/CAMBIOS SIN APLICAR/)).toBeTruthy();

    // Otro admin publica: llega un rule_set nuevo (id y versión distintos).
    mocks.useTenants.mockReturnValue(
      tenantsData({
        ruleSets: [
          {
            ...RULE_SET,
            rule_set_id: "rs-nuevo",
            version: 5,
            config: { edge: { thresholds: { pga_trip_g: 0.2 }, sample_rate: 100 } },
          },
          RULE_SET_FOREIGN,
        ],
      }),
    );
    rerender(<TenantsPage />);

    expect(screen.getByText(/OTRO ADMIN PUBLICÓ UNA VERSIÓN NUEVA/)).toBeTruthy();
    // El trabajo del operador sigue ahí: no se lo pisó con el 0.2 del servidor.
    expect((screen.getByLabelText(/PGA · banda de disparo/) as HTMLInputElement).value).toBe(
      "0.15",
    );
  });

  it("sin edición sin guardar, el rule_set nuevo se adopta en silencio", () => {
    mocks.useTenants.mockReturnValue(tenantsData());
    const { rerender } = render(<TenantsPage />);

    mocks.useTenants.mockReturnValue(
      tenantsData({
        ruleSets: [
          {
            ...RULE_SET,
            rule_set_id: "rs-nuevo",
            version: 5,
            config: { edge: { thresholds: { pga_trip_g: 0.2 }, sample_rate: 100 } },
          },
          RULE_SET_FOREIGN,
        ],
      }),
    );
    rerender(<TenantsPage />);

    expect(screen.queryByText(/OTRO ADMIN PUBLICÓ/)).toBeNull();
    expect((screen.getByLabelText(/PGA · banda de disparo/) as HTMLInputElement).value).toBe("0.2");
  });
});
