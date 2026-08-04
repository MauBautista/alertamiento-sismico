// [T-2.56] `prefers-reduced-motion` como INTERRUPTOR, no como sugerencia.
//
// La política de T-2.47 se apoya en dos mitades que se escribieron por separado
// y pueden divergir sin que nada falle: `wavefront.ts` apaga los frentes P/S y
// congela el dash del mapa, y `soc.css` neutraliza los keyframes CSS vivos.
// Ninguna de las dos se puede comprobar en jsdom (no computa animaciones y no
// tiene media queries reales), así que esto solo existe en navegador.
//
// Importa de verdad: en una consola de alertamiento sísmico el movimiento no es
// decoración — un halo pulsante y un frente de onda avanzando son SEÑAL. Que se
// apaguen para quien lo pidió es accesibilidad; que se apaguen bien es que
// siguen leyéndose como estado, no que desaparecen.
import { expect, test, type Page } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

/** `animation-name` computado de un pseudo-elemento. */
async function pseudoAnimation(
  page: import("@playwright/test").Page,
  selector: string,
  pseudo: string,
): Promise<string | null> {
  return page.evaluate(
    ([sel, pseudoEl]) => {
      const el = document.querySelector(sel);
      if (el === null) return null;
      return getComputedStyle(el, pseudoEl).animationName;
    },
    [selector, pseudo] as const,
  );
}

/**
 * [T-2.57] Monta un halo de estado y devuelve su selector.
 *
 * `.soc-dot--pulse` solo lo renderiza la app con DATO VIVO FRESCO (`DetailPanel`
 * con un sitio enfocado, o un `LinkPill` OPERATIVO). El seed local no tiene
 * ninguno de los dos, así que estos tests fallaban por AUSENCIA DEL SUJETO, no
 * porque la animación estuviera mal.
 *
 * Lo que estos casos afirman es un contrato de la HOJA DE ESTILOS —que
 * `prefers-reduced-motion` apaga el keyframe y que sin la preferencia sí corre—,
 * y eso se comprueba mejor sobre un elemento montado a propósito que sobre uno
 * que depende de que el gabinete esté vivo en ese instante.
 */
async function mountPulseDot(page: Page): Promise<string> {
  await page.evaluate(() => {
    const el = document.createElement("span");
    el.className = "soc-dot soc-dot--pulse";
    el.dataset.testid = "pulse-probe";
    document.body.appendChild(el);
  });
  return '[data-testid="pulse-probe"]';
}

// En @playwright/test 1.61 `reducedMotion` ya NO es opción de primer nivel de
// `test.use`: viaja dentro de `contextOptions` (es una opción del contexto de
// navegador). Escrito como `test.use({ reducedMotion })` NO da error en tiempo
// de ejecución — simplemente se ignora, y todos los tests de abajo pasarían en
// verde sin haber emulado nada. Solo `tsc` lo caza.
test.describe("con movimiento reducido", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("el halo del punto de estado deja de animarse pero SIGUE siendo un halo", async ({
    page,
  }) => {
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    const sel = await mountPulseDot(page);
    await expect(page.locator(sel)).toBeAttached();

    expect(await pseudoAnimation(page, sel, "::after")).toBe("none");
    // Sin la animación el halo se quedaría congelado a media escala (el
    // keyframe arranca en 0.6): la hoja lo fija en su reposo a propósito.
    const opacity = await page.evaluate((s) => {
      const el = document.querySelector(s);
      return el === null ? null : getComputedStyle(el, "::after").opacity;
    }, sel);
    expect(Number(opacity)).toBeGreaterThan(0);
  });

  test("el mapa DICE que los anillos están estáticos en vez de dejar de dibujarlos", async ({
    page,
  }) => {
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    // La capa de ondas solo se enciende con epicentro localizado y evento
    // reciente; sin sismo sembrado el mapa declara por qué no hay frentes.
    const idle = page.getByTestId("waves-idle");
    const model = page.getByTestId("waves-model");
    const shown = (await idle.count()) > 0 ? idle : model;
    if ((await shown.count()) === 0) return; // capa CAPAS·ONDAS apagada por el operador
    await expect(shown).toBeVisible();
    if (await model.isVisible()) {
      await expect(model).toContainText("ANILLOS ESTÁTICOS (MOVIMIENTO REDUCIDO)");
    }
  });

  test("el botón armado no parpadea (sigue siendo ámbar, que es lo que informa)", async ({
    page,
  }) => {
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    const confirm = page.getByRole("button", { name: /CONFIRMAR ACUSE/ });
    if ((await confirm.count()) === 0 || (await confirm.isDisabled())) return;
    await confirm.click();
    const armed = page.locator(".soc-confirm--armed").first();
    await expect(armed).toBeVisible();
    expect(await armed.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
  });
});

test.describe("sin preferencia declarada", () => {
  test.use({ contextOptions: { reducedMotion: "no-preference" } });

  test("el halo SÍ se anima: el interruptor de arriba no es un placebo", async ({ page }) => {
    // Sin este contraste, los tests de reducción pasarían igual si la animación
    // no hubiera existido nunca — que es la forma más común de verde falso.
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    const sel = await mountPulseDot(page);
    await expect(page.locator(sel)).toBeAttached();
    expect(await pseudoAnimation(page, sel, "::after")).toBe("soc-pulse");
  });
});
