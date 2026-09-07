// [T-6.03] Alta de un cliente y de su primera estación, de punta a punta y en las
// TRES pantallas: /tenants (crear el cliente) → /fleet (crear la estación y su
// gabinete, escribiendo en ESE cliente) → /console (el mapa lo muestra).
//
// El defecto que vigila (U-06): el alta de estación no tenía campo de cliente y la
// API exige que un rol interno lo NOMBRE; el superadmin recibía un 400 traducido
// como el mensaje del retiro, y el flujo «crear cliente → crear estación» moría en
// su segundo paso sin que nada lo dijera. Un test de componente no ve que las tres
// pantallas encajan: éste sí.
//
// Cada corrida crea un cliente con código único (`E2E-<ts>`): el stack local se
// resiembra en cada `make soc-local`, y mientras tanto los clientes de prueba son
// filas más en un catálogo de demostración.
import { expect, test, type Page } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

interface Onboarded {
  tenantCode: string;
  tenantName: string;
  tenantId: string;
  siteCode: string;
  siteName: string;
}

/** Espera la primera respuesta de `path` que cumpla `pred`, y devuelve su JSON. */
async function nextJson<T>(page: Page, path: string, pred: (body: T) => boolean): Promise<T> {
  const resp = await page.waitForResponse(async (r) => {
    if (!r.url().includes(path) || !r.ok()) return false;
    try {
      return pred((await r.json()) as T);
    } catch {
      return false;
    }
  });
  return (await resp.json()) as T;
}

test("crear cliente → crear estación → gabinete → el mapa lo muestra", async ({ page }) => {
  // El superadmin es el ÚNICO rol que crea clientes (`manage_tenants`), y es
  // además un rol interno: el alta de estación tiene que pedirle el cliente.
  await devLogin(page, "takab_superadmin");
  const stamp = Date.now().toString(36).toUpperCase();
  const o: Onboarded = {
    tenantCode: `E2E-${stamp}`,
    tenantName: `Cliente E2E ${stamp}`,
    tenantId: "",
    siteCode: `E2E-S-${stamp}`,
    siteName: `Torre E2E ${stamp}`,
  };

  // ---- 1 · /tenants: alta del cliente -------------------------------------
  await gotoScreen(page, "/tenants", "04 Multi-Tenant");
  await page.getByRole("button", { name: /NUEVO CLIENTE/ }).click();
  const form = page.getByTestId("tenant-create-form");
  await form.getByLabel(/Código único/).fill(o.tenantCode);
  await form.getByLabel(/^Nombre$/).fill(o.tenantName);
  const created = nextJson<{ tenant_id: string; code: string }>(
    page,
    "/tenants",
    (b) => typeof b === "object" && b !== null && b.code === o.tenantCode,
  );
  await form.getByRole("button", { name: "CREAR CLIENTE" }).click();
  o.tenantId = (await created).tenant_id;
  expect(o.tenantId).toMatch(/^[0-9a-f-]{36}$/);

  // La ficha del cliente nuevo queda seleccionada, con 0 sitios, y ofrece el alta.
  const detail = page.locator(".mt__detail");
  await expect(detail.locator(".mt__detail-name")).toHaveText(o.tenantName);
  await expect(page.getByRole("button", { name: new RegExp(o.tenantName) })).toContainText(
    "0 sitios",
  );
  const link = page.getByTestId("tenant-new-site-link");
  await expect(link).toHaveAttribute("href", `/fleet?tenant=${o.tenantId}&nueva=1`);

  // ---- 2 · /fleet: alta de la estación ESCRIBIENDO EN ese cliente -----------
  await link.click();
  await expect(page.locator('[data-screen-label="02 Flota Edge"]')).toBeVisible();
  const siteForm = page.getByTestId("site-form");
  await expect(siteForm).toBeVisible();
  // El rótulo permanente dice el cliente ANTES de teclear nada; el selector ya
  // viene puesto porque se llegó desde su ficha.
  await expect(siteForm.getByTestId("site-form-target")).toContainText(
    `ESCRIBIENDO EN · ${o.tenantName}`,
  );
  await expect(siteForm.getByTestId("site-form-tenant")).toHaveValue(o.tenantId);

  await siteForm.getByLabel("CÓDIGO").fill(o.siteCode);
  await siteForm.getByLabel("NOMBRE").fill(o.siteName);
  const siteCreated = nextJson<{ site_id: string; tenant_id: string; code: string }>(
    page,
    "/sites",
    (b) => typeof b === "object" && b !== null && b.code === o.siteCode,
  );
  await siteForm.getByRole("button", { name: "CREAR ESTACIÓN" }).click();
  const site = await siteCreated;
  // LO QUE ESTABA ROTO: el sitio aterriza en el cliente nuevo, no en el del operador.
  expect(site.tenant_id).toBe(o.tenantId);

  // La tabla de estaciones lo lista y dice de quién es.
  const row = page.getByTestId(`site-row-${o.siteCode}`);
  await expect(row).toBeVisible();
  await expect(page.getByTestId(`site-tenant-${o.siteCode}`)).toHaveText(o.tenantName);

  // ---- 3 · /fleet: gabinete de la estación (hereda el tenant del sitio) -----
  await row.getByRole("button", { name: "HARDWARE" }).click();
  const hw = page.getByTestId("hardware-form");
  await expect(hw).toBeVisible();
  await hw.getByLabel("SERIAL DEL GABINETE").fill(`E2E-GW-${stamp}`);
  await hw.getByRole("button", { name: "AÑADIR GABINETE" }).click();
  const acuse = page.getByTestId("gateway-acuse");
  await expect(acuse).toBeVisible();
  // El edge.env que se entrega lleva el tenant CORRECTO: es lo que el gabinete
  // firmará en cada latido.
  await expect(acuse).toContainText(o.tenantId);

  // ---- 4 · /console: el mapa lo muestra ------------------------------------
  const mapState = nextJson<{ sites: Array<{ site_id: string; tenant_id: string; code: string }> }>(
    page,
    "/telemetry/map/state",
    (b) => Array.isArray(b?.sites) && b.sites.some((s) => s.site_id === site.site_id),
  );
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  const snapshot = await mapState;
  const pinned = snapshot.sites.find((s) => s.site_id === site.site_id);
  expect(pinned?.tenant_id).toBe(o.tenantId);
  expect(pinned?.code).toBe(o.siteCode);
  // Y el semáforo cuenta la estación nueva entre las del mapa («MOSTRANDO n DE N»).
  await expect(page.getByTestId("kpi-showing")).toContainText(
    new RegExp(`DE ${snapshot.sites.length}(?!\\d)`),
  );
});

test("un rol de cliente ve en qué cliente escribe y NO puede elegir otro", async ({ page }) => {
  // tenant_admin administra su flota, pero el servidor escribe siempre en SU tenant:
  // el formulario lo rotula y no le pinta un selector que la API negaría.
  // (Sin `beforeEach` con otro rol: con sesión viva, `/` ya no muestra el login dev.)
  await devLogin(page, "tenant_admin");
  await gotoScreen(page, "/fleet", "02 Flota Edge");
  await page.getByRole("button", { name: "NUEVA ESTACIÓN" }).click();
  const siteForm = page.getByTestId("site-form");
  await expect(siteForm.getByTestId("site-form-target")).toContainText("ESCRIBIENDO EN · ");
  await expect(siteForm.getByTestId("site-form-target")).not.toContainText("ELIGE UN CLIENTE");
  await expect(siteForm.getByTestId("site-form-tenant")).toHaveCount(0);
});
