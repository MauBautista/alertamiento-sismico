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

  test("[T-6.10] NINGUNA transición viva sobrevive a la preferencia", async ({ page }) => {
    // Hasta esta ficha la reducción alcanzaba 2 de 18 transiciones. Se apagan
    // poniendo a cero los TOKENS de duración, así que lo que hay que comprobar
    // en un navegador es que esa anulación llega de verdad al valor computado —
    // que es donde se rompería si alguien moviera el orden de los imports.
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");

    const vivas = await page.evaluate(() => {
      const sospechosos = [...document.querySelectorAll<HTMLElement>("*")];
      return sospechosos
        .map((el) => ({
          sel: el.className?.toString().split(/\s+/)[0] ?? el.tagName,
          dur: getComputedStyle(el).transitionDuration,
        }))
        .filter((x) => x.dur !== "" && !/^0s(,\s*0s)*$/.test(x.dur))
        .slice(0, 12);
    });
    expect(vivas, `siguen animando bajo reducción: ${JSON.stringify(vivas)}`).toEqual([]);
  });

  test("[T-6.10] la barra del UPS SALTA al valor: un dato no llega deslizándose", async ({
    page,
  }) => {
    // Era la única transición sobre un DATO y la que peor se llevaba con la
    // reducción: un porcentaje de batería que se desliza es un número que
    // tarda en ser cierto.
    await devLogin(page);
    await gotoScreen(page, "/fleet", "02 Flota Edge");
    const fill = page.locator(".fleet-ups__fill").first();
    if ((await fill.count()) === 0) return; // seed sin UPS reportado
    expect(await fill.evaluate((el) => getComputedStyle(el).transitionDuration)).toBe("0s");
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

  test("[T-6.10] y las transiciones SÍ duran: el cero de arriba no es que no existan", async ({
    page,
  }) => {
    // El mismo control negativo que el halo, para la mitad nueva del
    // interruptor: sin esto, borrar todas las transiciones de la hoja dejaría
    // el caso de reducción en verde.
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    const tab = page.locator(".soc-nav__tab").first();
    await expect(tab).toBeVisible();
    expect(await tab.evaluate((el) => getComputedStyle(el).transitionDuration)).not.toBe("0s");
  });

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
