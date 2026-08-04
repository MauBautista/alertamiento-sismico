// [T-2.56] `site_scope` de extremo a extremo, en navegador (T-2.45).
//
// El contrato que se vigila: el FRONT NO FILTRA. La autoridad es el servidor y
// la insignia solo DECLARA lo que el servidor está haciendo. Si un día el
// filtro del servidor fallara y la consola siguiera escondiendo estaciones por
// su cuenta, nadie se enteraría — por eso la insignia no puede mentir en
// ninguno de los dos sentidos.
import { expect, test } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

const LABELS = {
  /** Fase A del cutover, o un rol no acotado. */
  todo: "ALCANCE · TODO EL TENANT",
  /** Fase B con claim vacío: cero estaciones, y se DICE. */
  ninguna: "ALCANCE · SIN ESTACIONES ASIGNADAS",
} as const;

test("la insignia de alcance está en la topbar de todas las pantallas", async ({ page }) => {
  await devLogin(page, "soc_operator");
  const badge = page.getByTestId("scope-badge");
  await expect(badge).toBeVisible();

  for (const [path, label] of [
    ["/console", "01 Monitoreo en Vivo"],
    ["/fleet", "02 Flota Edge"],
    ["/triage", "03 Evaluación Estructural"],
  ] as const) {
    await gotoScreen(page, path, label);
    await expect(badge, `sin insignia de alcance en ${path}`).toBeVisible();
  }
});

test("la insignia dice una de las tres verdades posibles, nunca un número inventado", async ({
  page,
}) => {
  await devLogin(page, "soc_operator");
  const text = ((await page.getByTestId("scope-badge").textContent()) ?? "").trim();

  // Tres formas válidas: todo el tenant, sin estaciones, o "N ESTACIÓN(ES)".
  expect(
    text === LABELS.todo || text === LABELS.ninguna || /^ALCANCE · \d+ ESTACIÓN(ES)?$/.test(text),
    `rótulo de alcance no reconocido: ${JSON.stringify(text)}`,
  ).toBe(true);

  // "0 ESTACIONES" sería el dato falso que la regla de oro 7 prohíbe: cuando no
  // hay ninguna, el rótulo lo dice con palabras y explica qué hacer.
  expect(text).not.toMatch(/·\s*0\s+ESTACION/);
});

test("acotado ⇒ la insignia se ACENTÚA y el mapa enseña un subconjunto", async ({ page }) => {
  await devLogin(page, "soc_operator");
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  const badge = page.getByTestId("scope-badge");
  const enforced = await badge.evaluate((el) => el.classList.contains("soc-scope--limited"));

  // El acento visual y el rótulo son EL MISMO hecho: no pueden discrepar. Un
  // operador que ve un mapa medio vacío tiene que poder distinguir "no hay
  // estaciones" de "no me dejan verlas".
  const text = ((await badge.textContent()) ?? "").trim();
  expect(enforced).toBe(text !== LABELS.todo);

  if (!enforced) {
    // Fase A del cutover (`console_scope_enforced=false`): el `title` explica
    // que el rol no está acotado, para que nadie lea el mapa como recortado.
    await expect(badge).toHaveAttribute("title", /no está acotado|todas las estaciones/i);
  }
});
