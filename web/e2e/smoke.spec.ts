// Smoke de navegador (M-7): login dev + las 5 pantallas montan su layout real.
// Prerrequisito: `make soc-local` corriendo (ver playwright.config.ts).
//
// Asserta el `data-screen-label` de cada página — el mismo marcador que usan los
// mockups del design system — porque sobrevive a cambios de copy y de datos.
import { expect, test } from "@playwright/test";

/** Sitio real del seed (`db/seeds/prod_fleet.sql`): site-dev · Puebla. */
const SITE_DEV = "d1000000-0000-0000-0000-000000000000";

const SCREENS = [
  { path: "/console", label: "01 Consola C4I · Live Wall" },
  { path: "/fleet", label: "02 Flota Edge" },
  { path: "/triage", label: "03 Triage Estructural" },
  { path: "/tenants", label: "04 Multi-Tenant" },
  { path: `/building/${SITE_DEV}`, label: "05 Dashboard Edificio" },
];

test("login dev y las 5 pantallas cargan", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByText("LOGIN DEV", { exact: false }),
    "No está el panel de login dev: ¿corre `make soc-local` y web/.env tiene VITE_DEV_TOKEN_ENABLED=true?",
  ).toBeVisible();

  // superadmin ve las 5 rutas; la matriz real la sirve /me (RouteGuard).
  await page.getByLabel("ROL").selectOption("takab_superadmin");
  await page.getByRole("button", { name: "ENTRAR COMO ROL" }).click();
  await expect(page.locator("[data-screen-label]").first()).toBeVisible();

  for (const screen of SCREENS) {
    await page.goto(screen.path);
    await expect(
      page.locator(`[data-screen-label="${screen.label}"]`),
      `${screen.path} no montó su layout`,
    ).toBeVisible();
  }
});
