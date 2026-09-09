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
//
// [T-6.09] Y SE SUBIÓ, con datos: `color-contrast` pasa de adjunto a
// bloqueante. Esa era la promesa de arriba —"ir subiendo la barra"— y una barra
// que no sube nunca es un umbral honesto una sola vez.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type TestInfo } from "@playwright/test";

import { devLogin, gotoScreen, SITE_DEV } from "./helpers";

const SCREENS = [
  { path: "/console", label: "01 Monitoreo en Vivo" },
  { path: "/fleet", label: "02 Flota Edge" },
  { path: "/triage", label: "03 Evaluación Estructural" },
  { path: "/tenants", label: "04 Multi-Tenant" },
  { path: "/audit", label: "05 Auditoría" },
  // [T-6.09] `/building` no es pestaña —se llega por enlace profundo desde la
  // tarjeta de flota y desde triage (T-6.14)— y por eso se había quedado fuera
  // de este barrido. Que no tenga pestaña no la hace menos pantalla: es la que
  // se le enseña al administrador del inmueble.
  { path: `/building/${SITE_DEV}`, label: "06 Dashboard Edificio" },
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
  // [T-6.09] SUBE LA BARRA. `color-contrast` llevaba desde T-2.56 por debajo
  // del umbral —se adjuntaba al reporte y nadie lo miraba— y la medición de la
  // auditoría del 2026-09-06 dijo cuánto costaba eso: 44 nodos en estas seis
  // pantallas con el seed de demostración. 36 eran un solo defecto (el rojo
  // anclado haciendo de tinta) y el resto, tres. Arreglados los cuatro, dejar
  // la regla fuera del umbral sería devolver la deuda al día siguiente.
  //
  // Es la única regla de esta lista que NO es estructural, y entra por lo
  // mismo que ellas: un operador de turno largo frente a un videowall que no
  // puede leer el estado de un edificio no tiene un problema cosmético.
  "color-contrast",
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
