// [T-8.03 · D-38] LA SESIÓN DE LA CONSOLA, EN UN NAVEGADOR DE VERDAD.
//
// Hasta D-38 la consola cerraba la sesión a los ~60 min aunque la renovación
// silenciosa ya tuviera un token nuevo: el servidor cierra el canal live con
// 4401 al vencer el `exp` del token del handshake y el cliente lo trataba como
// fin de sesión (A-004). Ningún test unitario lo veía, porque el cierre lo hace
// el SERVIDOR sobre un socket de verdad. Estos tres casos lo ejercen contra
// `make soc-local`, acortando los plazos con `/dev/token`:
//
//   1. un token que vence a los 60 s y la consola abierta 90 s ⇒ sigue dentro
//      (el socket renovó y reconectó, y el REST también);
//   2. a 30 min del tope de su rol ⇒ el aviso «SU SESIÓN TERMINA A LAS hh:mm»;
//   3. pasado el tope ⇒ la pantalla de entrada lo dice con su causa, no un login mudo.
import { expect, test, type Page } from "@playwright/test";

const TENANT_DEV = "d0000000-0000-0000-0000-000000000001";
const SUB_FIJO = "00000000-0000-0000-0000-00000000e2e8";

/** Siembra una sesión dev como la guarda `devToken.ts` y abre la consola. */
async function entrarConToken(
  page: Page,
  opts: { expires_in?: number; auth_age_s?: number; role?: string },
): Promise<void> {
  const request = {
    role: opts.role ?? "soc_operator",
    tenant_id: TENANT_DEV,
    sub: SUB_FIJO,
    ...(opts.expires_in !== undefined ? { expires_in: opts.expires_in } : {}),
  };
  const resp = await page.request.post("/api/dev/token", {
    data: { ...request, auth_age_s: opts.auth_age_s ?? 0 },
  });
  expect(resp.ok(), "POST /api/dev/token falló: ¿corre `make soc-local`?").toBeTruthy();
  const body = (await resp.json()) as { id_token: string; expires_in: number };
  const session = {
    idToken: body.id_token,
    expiresAt: Date.now() + body.expires_in * 1000,
    request,
    authTimeMs: Date.now() - (opts.auth_age_s ?? 0) * 1000,
  };
  await page.addInitScript((s) => {
    window.sessionStorage.setItem("takab.dev.session", s);
  }, JSON.stringify(session));
  await page.goto("/console");
}

test.describe("sesión de la consola (D-38)", () => {
  test.skip(
    ({ viewport }) => viewport?.width !== 1440,
    "la sesión no depende del viewport: corre solo en laptop-1440x900",
  );

  test("un token que vence a los 60 s no saca al operador a los 90 s", async ({ page }) => {
    test.setTimeout(180_000);
    let cierres4401 = 0;
    page.on("websocket", (ws) => {
      ws.on("close", () => {
        cierres4401 += 1;
      });
    });
    await entrarConToken(page, { expires_in: 60 });
    await expect(page.locator('[data-screen-label="01 Monitoreo en Vivo"]')).toBeVisible();
    await page.waitForTimeout(90_000);
    await expect(
      page.locator('[data-screen-label="01 Monitoreo en Vivo"]'),
      "la consola salió de la sesión al vencer el token: el 4401 del canal live no renovó",
    ).toBeVisible();
    await expect(page.getByText("LOGIN DEV", { exact: false })).toHaveCount(0);
    // El servidor sí cerró el canal al vencer el token: si no hubo cierre, la
    // prueba no ejerció nada.
    expect(cierres4401, "el canal live nunca se cerró: el token no llegó a vencer").toBeGreaterThan(
      0,
    );
  });

  test("a 30 min del tope, la barra avisa la hora del corte", async ({ page }) => {
    await entrarConToken(page, { auth_age_s: 86_400 - 30 * 60 });
    await expect(page.locator('[data-screen-label="01 Monitoreo en Vivo"]')).toBeVisible();
    await expect(page.getByTestId("session-expiry-banner")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("session-expiry-banner")).toContainText(
      /SU SESIÓN TERMINA A LAS \d\d:\d\d/,
    );
    await expect(page.getByRole("button", { name: "RENOVAR AHORA" })).toBeVisible();
  });

  test("pasado el tope de 24 h, la entrada dice por qué se cerró", async ({ page }) => {
    await entrarConToken(page, { auth_age_s: 86_401 });
    await expect(
      page.getByText(/SU SESIÓN( DE 24 H)? TERMINÓ/),
      "la sesión caducada por tope no terminó en la entrada con su causa",
    ).toBeVisible({ timeout: 20_000 });
  });
});
