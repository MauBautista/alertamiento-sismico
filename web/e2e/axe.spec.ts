// [T-2.56] Accesibilidad automatizada. Hasta aquí el repo tenía CERO.
//
// Por qué importa en ESTE producto: la consola la operan turnos largos frente a
// un videowall, y buena parte de la información crítica se codifica en color
// (semáforo de sacudida, enlace del gabinete, severidad). Un fallo de contraste
// o un control sin nombre accesible no es cosmético: es un operador que no
// puede leer el estado de un edificio.
//
// UMBRAL HONESTO. La barra arranca en `critical` y en un conjunto de reglas
// estructurales inequívocas, NO en "cero violaciones". Poner cero el primer día
// solo produce una de dos cosas: un job rojo permanente que nadie mira, o un
// `.disableRules()` interminable que lo vacía de sentido. Todo lo que queda por
// debajo del umbral se ADJUNTA al reporte con nombre y recuento, para que la
// deuda sea visible y se pueda ir subiendo la barra con datos.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type TestInfo } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

const SCREENS = [
  { path: "/console", label: "01 Monitoreo en Vivo" },
  { path: "/fleet", label: "02 Flota Edge" },
  { path: "/triage", label: "03 Evaluación Estructural" },
  { path: "/tenants", label: "04 Multi-Tenant" },
  { path: "/audit", label: "05 Auditoría" },
];

/**
 * Reglas que NO admiten discusión ni contexto: si fallan, hay un control que
 * un lector de pantalla no puede nombrar o un formulario que no se puede
 * rellenar. Son exactamente el tipo de defecto que T-2.39 encontró a mano en la
 * tabla de evaluación (`<tr onClick>` sin teclado).
 */
const BLOCKING_RULES = [
  "aria-allowed-attr",
  "aria-required-attr",
  "aria-required-children",
  "aria-required-parent",
  "aria-valid-attr-value",
  "button-name",
  "image-alt",
  "input-button-name",
  "label",
  "link-name",
  "select-name",
];

function summarize(violations: { id: string; impact?: string | null; nodes: unknown[] }[]): string {
  return violations
    .map((v) => `${v.impact ?? "sin impacto"} · ${v.id} · ${v.nodes.length} nodo(s)`)
    .sort()
    .join("\n");
}

async function attach(info: TestInfo, name: string, body: string): Promise<void> {
  await info.attach(name, { body, contentType: "text/plain" });
}

for (const screen of SCREENS) {
  test(`a11y · ${screen.path}`, async ({ page }, testInfo) => {
    await devLogin(page);
    await gotoScreen(page, screen.path, screen.label);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      // El canvas de MapLibre es contenido de terceros dibujado por WebGL: axe
      // no puede razonar sobre él y sus hallazgos no son accionables desde aquí.
      // La información que el mapa transporta está DUPLICADA en texto (leyendas,
      // cola de incidentes, panel de detalle), que es lo que sí se audita.
      .exclude(".maplibregl-canvas-container")
      .analyze();

    await attach(
      testInfo,
      `axe-${screen.path.replace(/\W+/g, "-")}.txt`,
      results.violations.length === 0 ? "sin violaciones" : summarize(results.violations),
    );

    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || BLOCKING_RULES.includes(v.id),
    );
    expect(
      blocking.map((v) => `${v.id} (${v.nodes.length})`),
      `violaciones bloqueantes en ${screen.path}:\n${summarize(blocking)}`,
    ).toEqual([]);
  });
}

test("la topbar y la navegación son operables con teclado", async ({ page }) => {
  // Un SOC se maneja con las manos ocupadas. Que la navegación principal se
  // alcance con Tab no lo comprueba ninguna regla de axe: es de flujo.
  await devLogin(page);
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");

  const tabs = page.locator(".soc-nav__tab");
  await expect(tabs.first()).toBeVisible();
  await tabs.first().focus();
  const focused = await page.evaluate(() => document.activeElement?.className ?? "");
  expect(focused).toContain("soc-nav__tab");

  await page.keyboard.press("Enter");
  await expect(page.locator("[data-screen-label]").first()).toBeVisible();
});
