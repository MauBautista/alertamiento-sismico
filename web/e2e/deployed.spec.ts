// [T-2.57] Verificación de navegador contra el entorno DESPLEGADO.
//
// Los otros seis specs entran con el panel de login dev, y ese panel **no existe
// en producción**: `main.create_app` no monta `/dev/token` cuando el JWKS es
// remoto (comprobado contra el despliegue: `GET /api/dev/token` ⇒ 404). Eso no es
// una carencia de los tests, es la protección funcionando — un endpoint que
// firma tokens de cualquier rol no puede vivir en una consola de alertamiento.
//
// Lo que SÍ se puede afirmar sin sesión es todo lo que se sirve al visitante: que
// el bundle carga de verdad en un navegador (no solo un 200 de curl), que la
// página de entrada no desborda en ninguno de los tres viewports, y que no trae
// violaciones de accesibilidad bloqueantes. Es poco comparado con la suite
// completa, y por eso este archivo dice explícitamente qué NO cubre.
//
//   PW_BASE_URL=https://<host> npx playwright test deployed.spec.ts
//
// Sin `PW_BASE_URL` apunta a localhost y estos mismos casos valen igual contra
// el stack local.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type TestInfo } from "@playwright/test";

import { expectNoHorizontalOverflow } from "./helpers";

/** Mismo criterio que `axe.spec.ts`: la barra arranca en `critical`, no en cero. */
const BLOCKING_RULES = [
  "aria-allowed-attr",
  "aria-required-attr",
  "aria-valid-attr-value",
  "button-name",
  "html-has-lang",
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

test("la consola desplegada carga en un navegador real", async ({ page }) => {
  // Un 200 de curl solo dice que el HTML existe. Esto dice que el bundle se
  // descargó, ejecutó y montó algo — que es lo que rompe un deploy a medias.
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  const response = await page.goto("/");
  expect(response?.status(), "la raíz no respondió 200").toBe(200);
  await expect(page.locator("#app, #root, body > div").first()).toBeVisible();
  expect(errors, `errores de JavaScript al cargar:\n${errors.join("\n")}`).toEqual([]);
});

test("la pantalla de entrada no desborda en horizontal", async ({ page }) => {
  // En un SOC no hay scroll lateral. Se comprueba en los tres viewports de la
  // matriz porque el corte de 1280 es donde T-2.55 encontró los solapes.
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("la pantalla de entrada no trae violaciones de a11y bloqueantes", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  await attach(
    testInfo,
    "axe-entrada.txt",
    results.violations.length === 0 ? "sin violaciones" : summarize(results.violations),
  );

  const blocking = results.violations.filter(
    (v) => v.impact === "critical" || BLOCKING_RULES.includes(v.id),
  );
  expect(
    blocking.map((v) => `${v.id} (${v.nodes.length})`),
    `violaciones bloqueantes en la entrada:\n${summarize(blocking)}`,
  ).toEqual([]);
});

test("producción NO sirve el login dev", async ({ page, baseURL }) => {
  // Es una comprobación de SEGURIDAD, no de layout: `/dev/token` firma tokens de
  // cualquier rol sin credenciales. Si algún día apareciera en el entorno
  // desplegado, este test tiene que gritar. Contra un stack local se omite,
  // porque allí el panel debe existir.
  test.skip(
    (baseURL ?? "").includes("localhost"),
    "solo aplica al entorno desplegado (en local el login dev SÍ debe estar)",
  );
  const res = await page.request.get("/api/dev/token");
  expect(res.status(), "/api/dev/token está expuesto en el entorno desplegado").toBe(404);
});
