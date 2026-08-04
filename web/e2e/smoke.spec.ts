// Smoke de navegador (M-7): login dev + las 5 pantallas montan su layout real.
// Prerrequisito: `make soc-local` corriendo (ver playwright.config.ts).
//
// Asserta el `data-screen-label` de cada página — el mismo marcador que usan los
// mockups del design system — porque sobrevive a cambios de copy y de datos.
//
// [T-2.56] Corre en los TRES viewports de la matriz: el smoke era el único e2e
// y fijaba su propio tamaño, así que el shell nunca se montó por debajo de 1440.
import { expect, test } from "@playwright/test";

import { SITE_DEV } from "./helpers";

const SCREENS = [
  { path: "/console", label: "01 Monitoreo en Vivo" },
  { path: "/fleet", label: "02 Flota Edge" },
  { path: "/triage", label: "03 Evaluación Estructural" },
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

// [T-1.62] Regresión de layout que jsdom NO puede ver (no calcula alturas): el
// control de simulacro de T-1.60 caía en la fila elástica de .soc-main y dejaba
// el mapa clavado en su piso de 280 px. Solo un navegador real lo caza.
// [T-2.56] Ya NO fija el viewport: lo pone el project de la matriz, así que la
// misma regresión se vigila en 1280×800, 1440×900 y 1920×1080. La versión
// exhaustiva de esta medida vive en `layout.spec.ts`.
test("el mapa se queda el alto: el simulacro es una tira, no un panel", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("ROL").selectOption("takab_superadmin"); // tiene drill_start
  await page.getByRole("button", { name: "ENTRAR COMO ROL" }).click();
  // El login ya aterriza en /console; navegar antes de que monte tira la sesión.
  await expect(page.locator('[data-screen-label="01 Monitoreo en Vivo"]')).toBeVisible();

  const drill = page.getByTestId("drill-idle");
  await expect(drill).toBeVisible();
  const drillBox = await drill.boundingBox();
  const stageBox = await page.locator(".soc-stage").boundingBox();

  expect(drillBox!.height, "el control en reposo debe ser una tira").toBeLessThan(60);
  expect(
    stageBox!.height,
    "el mapa está en su piso de 280 px: algo le robó el alto",
  ).toBeGreaterThan(400);
});
