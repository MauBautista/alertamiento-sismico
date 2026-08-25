import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Breakpoints del brief. La evidencia (capturas de página completa) se guarda
// en tests/e2e/evidencia/ y se commitea como criterio de aceptación de fase.
const BREAKPOINTS = [
  { w: 360, h: 740 },
  { w: 768, h: 1024 },
  { w: 1280, h: 800 },
  { w: 1920, h: 1080 },
];

// Asienta el estado FINAL antes de cualquier captura de página completa:
// recorre todo el documento (dispara los reveals por IntersectionObserver y la
// carga de imágenes lazy), espera fuentes e imágenes, y vuelve arriba. Sin esto
// la captura muestra papel en blanco donde hay contenido sin revelar — evidencia
// inválida (lo cazó el finish review: disposition recapture).
async function asentar(page: import("@playwright/test").Page): Promise<void> {
  await page.evaluate(async () => {
    // El html lleva scroll-behavior:smooth; sin esto, el scrollTo final queda
    // EN VUELO al capturar (medido: scrollY=218 en vez de 0).
    document.documentElement.style.scrollBehavior = "auto";
    await document.fonts.ready;
    const paso = Math.max(200, Math.floor(window.innerHeight * 0.7));
    const alto = () => document.documentElement.scrollHeight;
    for (let y = 0; y <= alto(); y += paso) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 90));
    }
    window.scrollTo(0, alto());
    await new Promise((r) => setTimeout(r, 250));
    await Promise.all(
      Array.from(document.images).map((img) =>
        img.complete
          ? Promise.resolve()
          : new Promise((res) => {
              img.addEventListener("load", res, { once: true });
              img.addEventListener("error", res, { once: true });
            }),
      ),
    );
    window.scrollTo(0, 0);
    // Congela el estado FINAL para la evidencia: la coreografía ya se reprodujo
    // (verificado con sonda: opacity 1, animaciones finished) pero el re-render
    // del fullPage de Chromium puede re-disparar animaciones con delay y pintar
    // su frame inicial (esquema en blanco a ≥1280 — lo cazó el finish review).
    // Sin la clase de reproducción y sin animaciones vivas, el estado base ES la
    // composición final (los actuadores en reposo «EN ESPERA»), determinista.
    document
      .querySelectorAll("[data-esquema].play")
      .forEach((el) => el.classList.remove("play"));
    document.getAnimations().forEach((a) => a.cancel());
  });
  await page.waitForFunction(() => window.scrollY === 0);
  // Deja terminar las transiciones de revelado (450 ms) antes de capturar.
  await page.waitForTimeout(700);
}

for (const { w, h } of BREAKPOINTS) {
  test(`sin scroll horizontal y captura a ${w}px`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/");
    await asentar(page);
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(
      overflow,
      `overflow horizontal de ${overflow}px a ${w}`,
    ).toBeLessThanOrEqual(0);
    await page.screenshot({
      path: `tests/e2e/evidencia/${w}.png`,
      fullPage: true,
    });
  });
}

test("axe: sin violaciones critical/serious (360 y 1280)", async ({
  browser,
}) => {
  // Con reducedMotion: los colores auditables son los del estado FINAL. Sin
  // esto, axe mide texto a media animación (opacity parcial) y reporta un
  // contraste que ningún usuario ve quieto — flake, no hallazgo.
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  for (const w of [360, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto("/");
    const resultados = await new AxeBuilder({ page }).analyze();
    const graves = resultados.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(graves, graves.map((v) => `${v.id}: ${v.help}`).join("\n")).toEqual(
      [],
    );
  }
  await context.close();
});

test("prefers-reduced-motion: todo visible y estático", async ({ browser }) => {
  const context = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 360, height: 740 },
  });
  const page = await context.newPage();
  await page.goto("/");
  await asentar(page); // también aquí: carga las imágenes lazy del pie
  // El titular y el esquema deben estar visibles sin animación alguna.
  await expect(page.locator("h1")).toBeVisible();
  const esquema = page.locator("[data-esquema] svg").first();
  await esquema.scrollIntoViewIfNeeded();
  await expect(esquema).toBeVisible();
  await page.screenshot({
    path: "tests/e2e/evidencia/reduced-motion-360.png",
    fullPage: true,
  });
  await context.close();
});

test("teclado: el primer Tab llega al salto de contenido; el simulacro responde", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.locator(".salto")).toBeFocused();

  const boton = page.locator("[data-simulacro]");
  await boton.scrollIntoViewIfNeeded();
  await boton.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-simulacro-aviso]")).toContainText(
    "Simulacro ejecutado",
  );
});

test("404 propia con su mensaje anti-espejo", async ({ page }) => {
  await page.goto("/404.html");
  await expect(page.locator("h1")).toHaveText("404");
  await expect(page.locator("main")).toContainText("Esta ruta no existe");
});
