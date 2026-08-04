// [T-2.56] Simulacro institucional en navegador (T-2.48).
//
// Lo que se vigila NO es que el simulacro suene —eso lo prueba el edge— sino
// las dos propiedades que un test de componente no ve:
//
//   1. El control en reposo es una TIRA. Si crece, le roba el alto al mapa: es
//      exactamente la regresión de T-1.62 ("el botón de simulacro ocupa 3/4 de
//      pantalla") y vuelve sola cada vez que alguien mete un estado nuevo.
//   2. El simulacro NUNCA se confunde con una alerta real: cian cuando está
//      armado, ámbar cuando suena, y ejecutar sigue siendo UN CLIC HUMANO
//      (regla de oro 8). No hay ejecutor automático y no debe aparecer.
import { expect, test } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

test.beforeEach(async ({ page }) => {
  // superadmin trae `drill_start`; con un rol sin la acción el botón no existe
  // (default-deny server-driven) y el spec no tendría nada que abrir.
  await devLogin(page, "takab_superadmin");
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
});

test("en reposo el simulacro es una tira, no un panel", async ({ page }) => {
  const idle = page.getByTestId("drill-idle");
  await expect(idle).toBeVisible();
  const box = await idle.boundingBox();
  expect(box!.height, "la tira de simulacro creció y le come el alto al mapa").toBeLessThan(60);
});

test("el modal declara los cuatro estados de su lista de sitios", async ({ page }) => {
  await page.getByRole("button", { name: "INICIAR SIMULACRO" }).click();
  const modal = page.getByTestId("drill-modal");
  await expect(modal).toBeVisible();

  // El descargo va SIEMPRE y en el modal, no en un tooltip: quien programa un
  // simulacro tiene que leer "CERO RELÉS" antes de pulsar nada.
  await expect(modal).toContainText("CERO RELÉS");
  await expect(modal).toContainText("UNA ALERTA REAL LO ABORTA");

  // La lista de sitios pasa por StateFrame: sea cual sea el estado del stack
  // local, el marco declara UNO de los cuatro — jamás un hueco mudo.
  const frame = modal.locator("[data-state]").first();
  await expect(frame).toHaveAttribute("data-state", /loading|error|empty|stale|ready/);
});

test("PROGRAMAR pide fecha y AHORA no: el modo no se adivina", async ({ page }) => {
  await page.getByRole("button", { name: "INICIAR SIMULACRO" }).click();
  const modal = page.getByTestId("drill-modal");
  await expect(modal).toBeVisible();

  await modal.getByRole("radio", { name: "PROGRAMAR" }).check();
  await expect(modal.locator('input[type="datetime-local"]')).toBeVisible();

  await modal.getByRole("radio", { name: "AHORA" }).check();
  await expect(modal.locator('input[type="datetime-local"]')).toHaveCount(0);
});

test("el historial abre y declara su estado (no desaparece en silencio)", async ({ page }) => {
  // El defecto que cerró T-2.48: si `/drills/active` fallaba con un simulacro
  // vivo, el banner simplemente NO SE PINTABA. Un panel que se esfuma es peor
  // que uno que dice que falló.
  await page.getByRole("button", { name: "HISTORIAL" }).click();
  const history = page.getByTestId("drill-history");
  await expect(history).toBeVisible();
  await expect(history.locator("[data-state]").first()).toHaveAttribute(
    "data-state",
    /loading|error|empty|stale|ready/,
  );
});

test("no existe ningún ejecutor automático de simulacros", async ({ page }) => {
  // Regla de oro 8: ejecutar es un clic humano con sesión MFA viva. Si algún día
  // aparece un "EJECUTAR AHORA" sin banner armado, este test lo caza.
  const armed = page.getByTestId("drill-armed");
  if ((await armed.count()) > 0 && (await armed.isVisible())) {
    await expect(armed.getByRole("button", { name: /EJECUTAR AHORA/ })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: /EJECUTAR AHORA/ })).toHaveCount(0);
  }
});
