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

/**
 * [T-6.05] Las TRES huellas del panel LOGIN DEV en el DOM de la entrada. Van en una
 * constante porque las usan dos tests con signo contrario: el de producción exige
 * que NO estén y el local exige que SÍ. Si un día el panel cambia de texto, el local
 * se pone rojo — y sin él, el de producción pasaría en verde por vacuidad.
 */
const DEV_PANEL = {
  texto: "LOGIN DEV",
  selectorDeRol: "ROL",
  boton: "ENTRAR COMO ROL",
} as const;

function esLocal(baseURL: string | undefined): boolean {
  return /localhost/.test(baseURL ?? "");
}

test("producción NO sirve el login dev: ni en el DOM ni en el endpoint", async ({
  page,
  baseURL,
}) => {
  // Es una comprobación de SEGURIDAD, no de layout: `/dev/token` firma tokens de
  // cualquier rol sin credenciales. Si algún día apareciera en el entorno
  // desplegado, este test tiene que gritar. Contra un stack local se omite,
  // porque allí el panel debe existir.
  test.skip(
    esLocal(baseURL),
    "solo aplica al entorno desplegado (en local el login dev SÍ debe estar)",
  );

  // [T-6.05] PRIMERO el DOM, que es lo que U-16 encontró sin defender: el servidor
  // ya tenía gate (sin JWKS inline no monta `/dev/token`), el cliente dependía de
  // una línea del Dockerfile que nadie leía. Antes se exige que la entrada MONTÓ
  // (su título): una página en blanco también carece de panel, y el silencio no
  // es éxito.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "CONSOLA SOC" })).toBeVisible();
  await expect(page.getByText(DEV_PANEL.texto, { exact: false })).toHaveCount(0);
  await expect(page.getByLabel(DEV_PANEL.selectorDeRol)).toHaveCount(0);
  await expect(page.getByRole("button", { name: DEV_PANEL.boton })).toHaveCount(0);
  // Y la puerta que SÍ debe existir en producción: sin Cognito la consola desplegada
  // no tendría ninguna forma de entrar.
  await expect(page.getByRole("button", { name: "ENTRAR CON COGNITO" })).toBeVisible();

  const res = await page.request.get("/api/dev/token");
  expect(res.status(), "/api/dev/token está expuesto en el entorno desplegado").toBe(404);
});

test("en local el panel LOGIN DEV SÍ está: las huellas que busca el test de arriba existen", async ({
  page,
  baseURL,
}) => {
  // El espejo del anterior. Sin esto, un cambio de copy en `DevLoginPanel` dejaría al
  // test de producción buscando un texto que ya no existe y pasando en verde por
  // vacuidad — el modo de fallo exacto que este fichero no puede permitirse.
  test.skip(!esLocal(baseURL), "solo contra el stack local (en producción el panel NO debe estar)");
  await page.goto("/");
  await expect(page.getByText(DEV_PANEL.texto, { exact: false })).toBeVisible();
  await expect(page.getByLabel(DEV_PANEL.selectorDeRol)).toBeVisible();
  await expect(page.getByRole("button", { name: DEV_PANEL.boton })).toBeVisible();
});
