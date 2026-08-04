// Utilidades compartidas por los specs de la matriz de viewports (T-2.56).
//
// No es un spec: Playwright solo recoge `*.spec.ts`, así que este archivo no
// aporta tests aunque viva en `testDir`.
import { expect, type Locator, type Page } from "@playwright/test";

/** Sitio real del seed (`db/seeds/prod_fleet.sql`): site-dev · Puebla. */
export const SITE_DEV = "d1000000-0000-0000-0000-000000000000";

/** Roles del panel de login dev (`/dev/token`, solo con VITE_DEV_TOKEN_ENABLED). */
export type DevRole = "takab_superadmin" | "soc_operator" | "tenant_admin";

/**
 * Entra con el login dev y espera a que la primera pantalla monte.
 *
 * El login aterriza en `/console`; navegar antes de que monte tira la sesión
 * (trampa ya documentada en el smoke de T-1.62), así que aquí se espera SIEMPRE
 * al `data-screen-label` antes de devolver el control.
 */
export async function devLogin(page: Page, role: DevRole = "takab_superadmin"): Promise<void> {
  await page.goto("/");
  await expect(
    page.getByText("LOGIN DEV", { exact: false }),
    "No está el panel de login dev: ¿corre `make soc-local` y web/.env tiene VITE_DEV_TOKEN_ENABLED=true?",
  ).toBeVisible();
  await page.getByLabel("ROL").selectOption(role);
  await page.getByRole("button", { name: "ENTRAR COMO ROL" }).click();
  await expect(page.locator("[data-screen-label]").first()).toBeVisible();
}

/** Entra y navega a `path`, esperando su layout. */
export async function gotoScreen(page: Page, path: string, label: string): Promise<void> {
  await page.goto(path);
  await expect(
    page.locator(`[data-screen-label="${label}"]`),
    `${path} no montó su layout`,
  ).toBeVisible();
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Caja de un elemento VISIBLE y con área; `null` si no está o no ocupa nada. */
export async function boxOf(locator: Locator): Promise<Box | null> {
  if ((await locator.count()) === 0) return null;
  if (!(await locator.first().isVisible())) return null;
  const box = await locator.first().boundingBox();
  if (box === null || box.width < 1 || box.height < 1) return null;
  return box;
}

/**
 * Área de intersección en px². Cero = no se tocan.
 *
 * Se compara ÁREA y no "¿se tocan?" porque un borde compartido de sub-píxel
 * (dos cajas pegadas) no es una colisión y haría el test inestable entre
 * viewports con distinto device pixel ratio.
 */
export function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return w > 1 && h > 1 ? w * h : 0;
}

/** El documento no puede desbordar en horizontal: en un SOC no hay scroll lateral. */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return { scroll: el.scrollWidth, client: el.clientWidth };
  });
  expect(
    overflow.scroll,
    `el documento desborda ${overflow.scroll - overflow.client} px en horizontal`,
  ).toBeLessThanOrEqual(overflow.client + 1);
}
