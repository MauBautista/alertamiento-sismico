// [T-2.56] Layout REAL medido en un navegador, en los tres viewports.
//
// Todo lo de aquí es invisible para jsdom, que no hace layout: no mide, no
// scrollea y no sabe qué es un elemento inalcanzable. Cada test de este archivo
// corresponde a un defecto que ya ocurrió en producción:
//
//   · tres sobrepuestos anclados a la misma banda superior (T-2.55)
//   · `.mt__list` sin scroll bajo `body { overflow: hidden }` ⇒ los últimos
//     clientes FÍSICAMENTE inalcanzables (T-2.51)
//   · el control de simulacro robándole el alto al mapa (T-1.62)
//
// [T-7.04] Y la ESCENA se fuerza. Hasta esta ficha el test de los sobrepuestos
// decía que la alerta «puede no estar» y medía los que estuvieran: con el stack
// en reposo pasaba en verde sin haber visto jamás la tarjeta roja, que es la que
// se va a enseñar. Ahora el barrido corre dos veces —escena `normal` y escena
// `alert` forzada por el WR-1 simulado (`escena.ts`)— sobre las seis pantallas,
// y en `alert` exige la alerta ANTES de medir (control positivo). El criterio
// también cambia de «estos seis selectores» a «todo texto visible y todo
// control»: un solape nuevo entre dos elementos que nadie nombró aquí falla
// igual. La escena `review` se declara pendiente con su razón, no se finge.
import { expect, test } from "@playwright/test";

import { PENDING_SCENES, expectScene, forceScene, type ForcedScene } from "./escena";
import {
  MATRIX_SCREENS,
  boxOf,
  devLogin,
  expectNoHorizontalOverflow,
  formatOverlap,
  gotoScreen,
  overlapArea,
  settle,
  textOverlaps,
  type AllowedOverlap,
} from "./helpers";

/**
 * Parejas que PUEDEN pisarse, cada una con su razón. Vacía a propósito: hoy no
 * hay ningún solape deliberado entre dos elementos con texto. Si aparece uno
 * (un distintivo que va encima de otro rótulo por diseño), se añade aquí con
 * los dos selectores y el porqué — nunca subiendo un z-index en la hoja para
 * que «gane» uno de los dos.
 */
const ALLOWED_OVERLAPS: readonly AllowedOverlap[] = [];

/** Escenas que el arnés fuerza hoy, en el orden en que se barren. */
const SCENES: readonly ForcedScene[] = ["normal", "alert"];

test.beforeEach(async ({ page }) => {
  await devLogin(page);
});

test.describe("[T-7.04] nada se encima, con la escena PUESTA", () => {
  for (const scene of SCENES) {
    test.describe(`escena ${scene}`, () => {
      let forced = "";

      test.beforeAll(async () => {
        // El camino real tarda: contacto → edge → bridge → motor → incidente.
        test.setTimeout(150_000);
        forced = await forceScene(scene);
      });

      // Sin `afterAll` que devuelva el reposo: tras un test fallido Playwright
      // RENUEVA el worker y el `afterAll` del viejo (cerrar incidentes) corre en
      // carrera con el `beforeAll` del nuevo (forzar alerta). El reposo se
      // restaura en el último test del barrido, que además lo VERIFICA.
      if (scene === "alert") {
        test("los sobrepuestos del escenario no se pisan entre sí (con la alerta PRESENTE)", async ({
          page,
        }) => {
          await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
          await expect(page.locator(".soc-stage")).toBeVisible();
          await settle(page);
          await expectScene(page, "alert", "/console");

          // [T-7.04] Antes: «los condicionales pueden no estar». Ahora la pila
          // de alertas ES la razón del test y se exige; siguen siendo
          // condicionales sólo los que dependen de la red (mapa degradado) o del
          // reloj (datos retenidos).
          const required: [string, ReturnType<typeof page.locator>][] = [
            ["pila de alertas (arriba-derecha)", page.locator(".soc-stage__overlays")],
            ["tarjeta de alerta", page.locator(".soc-stage__overlays .soc-alert")],
            ["leyendas (abajo-derecha)", page.locator(".soc-map__legends")],
            ["atribución (abajo-izquierda)", page.locator(".soc-map__attribution")],
          ];
          const optional: [string, ReturnType<typeof page.locator>][] = [
            ["estado del mapa (arriba-izquierda)", page.locator(".soc-map__degraded")],
            ["datos retenidos", page.locator(".soc-wall > .soc-stateframe__stale")],
            // [T-2.59] El control NATIVO de MapLibre se ancla abajo-DERECHA, la
            // esquina de las leyendas, y las pisaba 2853 px² (357×8). Hoy va
            // desactivado (`attributionControl: false`); si alguien lo
            // reactiva, que choque aquí y no en el muro.
            [
              "atribución nativa de MapLibre (abajo-derecha)",
              page.locator(".maplibregl-ctrl-bottom-right"),
            ],
          ];

          const present: [string, NonNullable<Awaited<ReturnType<typeof boxOf>>>][] = [];
          for (const [label, locator] of required) {
            const box = await boxOf(locator);
            expect(
              box,
              `bajo escena alert falta «${label}»: el test no mide lo que promete`,
            ).not.toBeNull();
            present.push([label, box!]);
          }
          for (const [label, locator] of optional) {
            const box = await boxOf(locator);
            if (box !== null) present.push([label, box]);
          }

          for (let i = 0; i < present.length; i += 1) {
            for (let j = i + 1; j < present.length; j += 1) {
              const [labelA, a] = present[i];
              const [labelB, b] = present[j];
              // La tarjeta vive DENTRO de la pila: ancestro y descendiente no chocan.
              if (labelA.startsWith("pila") && labelB.startsWith("tarjeta")) continue;
              expect(
                overlapArea(a, b),
                `"${labelA}" y "${labelB}" se solapan: se resuelve REUBICANDO uno, no subiendo su z-index`,
              ).toBe(0);
            }
          }

          // Las dos pilas superiores están acotadas al 46 % cada una: la
          // no-colisión es aritmética. Se comprueba el ancho real por si alguien
          // quita el tope.
          const stage = await boxOf(page.locator(".soc-stage"));
          const overlays = await boxOf(page.locator(".soc-stage__overlays"));
          expect(stage).not.toBeNull();
          expect(overlays).not.toBeNull();
          expect(overlays!.width).toBeLessThanOrEqual(stage!.width * 0.47 + 1);
        });
      }

      for (const screen of MATRIX_SCREENS) {
        test(`${screen.path} · ningún texto visible pisa a otro`, async ({ page }, testInfo) => {
          await gotoScreen(page, screen.path, screen.label);
          await settle(page);
          await expectScene(page, scene, screen.path);

          const pairs = await textOverlaps(page, ALLOWED_OVERLAPS);
          await testInfo.attach(`solapes-${scene}-${screen.path.replace(/\W+/g, "-")}.json`, {
            body: JSON.stringify(
              { scene, forced, viewport: page.viewportSize(), path: screen.path, pairs },
              null,
              2,
            ),
            contentType: "application/json",
          });
          expect(
            pairs.map(formatOverlap),
            `${pairs.length} pareja(s) de texto/controles encimados en ${screen.path} bajo escena ${scene}`,
          ).toEqual([]);
        });
      }
    });
  }

  test.describe("escena review", () => {
    // Declarada, no fingida: cuando T-7.16 la traiga, `ForcedScene` la admite,
    // `forceScene` aprende a producirla y estos seis dejan de ser fixme.
    for (const screen of MATRIX_SCREENS) {
      test.fixme(
        `${screen.path} · ningún texto visible pisa a otro`,
        { annotation: { type: "pendiente", description: PENDING_SCENES.review } },
        async () => {
          throw new Error(PENDING_SCENES.review);
        },
      );
    }
  });

  test.describe("de vuelta al reposo", () => {
    test("cerrada la alerta, la consola vuelve a `normal` (y el stack queda en reposo)", async ({
      page,
    }) => {
      // Cierre + re-armado + control positivo del reposo: la franja tiene que
      // DEJAR de decir alerta cuando el incidente se cierra, en el mismo
      // sondeo con el que la anunció. Y quien corra un spec después de éste
      // (drill.spec asume que ninguna alerta real aborta simulacros) encuentra
      // el stack como lo dejó `make soc-local`.
      test.setTimeout(90_000);
      await forceScene("normal");
      await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
      await settle(page);
      await expectScene(page, "normal", "/console");
      await expect(page.getByTestId("alert-banner")).toHaveCount(0);
    });
  });
});

test("el mapa conserva su alto: nadie se lo roba", async ({ page }) => {
  // Regresión de T-1.62 (el simulacro se tragaba el sobrante) ampliada a la
  // matriz: en 1280×800 el recorte de paddings de `@media (max-height: 800px)`
  // es lo único que impide que el escenario caiga a su piso de 280 px.
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  // [T-2.57] `gotoScreen` espera al `data-screen-label`, que monta ANTES de que
  // el StateFrame del wall reciba `/telemetry/map/state`: hasta entonces el wall
  // pinta su estado de carga y `.soc-stage` no existe. Medir ahí daba un fallo
  // que parecía del layout y era una carrera del test.
  await expect(page.locator(".soc-stage")).toBeVisible();
  const stage = await boxOf(page.locator(".soc-stage"));
  expect(stage, "no se encontró `.soc-stage` visible").not.toBeNull();
  expect(
    stage!.height,
    "el escenario está en su piso de 280 px: algo por encima le comió el alto",
  ).toBeGreaterThan(400);

  const drill = page.getByTestId("drill-idle");
  if (await drill.isVisible()) {
    const box = await drill.boundingBox();
    expect(box!.height, "el control de simulacro en reposo debe ser una TIRA").toBeLessThan(60);
  }
});

// [D3] El banner de privacidad, TERCERA vez que un hermano nuevo se come el alto
// del mapa (T-1.62 el simulacro, T-2.57 la tira de KPIs). Aquí se mide de verdad.
//
// El banner solo se pinta si el operador tiene el consentimiento pendiente, y el
// estado de la base del stack local no es un contrato del test: para que la
// medida sea DETERMINISTA se inyecta una franja con la clase real
// (`.privacy-banner`) como primer hijo del <main> del shell. Es exactamente lo
// que renderiza `PrivacyConsentBanner` desde el punto de vista de la reja, y la
// forma del árbol —que el banner sea ese hijo y lleve esa clase— la vigila
// `src/shell/AppShell.layout.test.tsx`.
//
// OJO: esto NO es el gate. `e2e.yml` es workflow_dispatch + continue-on-error;
// lo que bloquea es `src/styles/layoutInvariants.test.ts` en vitest. Aquí se
// mide lo que jsdom no puede medir.
test("el banner de privacidad es una FRANJA: no le roba el alto al mapa", async ({ page }) => {
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  await expect(page.locator(".soc-stage")).toBeVisible();
  const sinBanner = await boxOf(page.locator(".soc-stage"));
  expect(sinBanner, "no se encontró `.soc-stage` visible").not.toBeNull();

  const inyectado = await page.evaluate(() => {
    const main = document.querySelector(".soc-app > main.soc-main");
    if (main === null) return false;
    if (main.querySelector(":scope > .privacy-banner") !== null) return true;
    const franja = document.createElement("div");
    franja.className = "privacy-banner";
    franja.dataset.testid = "privacy-banner-probe";
    franja.textContent = "SONDA · ACEPTE EL AVISO DE PRIVACIDAD";
    main.prepend(franja);
    return true;
  });
  expect(inyectado, "no hay `.soc-app > main.soc-main`: la sonda no mide nada").toBe(true);

  const banner = await boxOf(page.locator(".privacy-banner"));
  expect(banner, "la franja inyectada no se renderizó").not.toBeNull();
  expect(
    banner!.height,
    "el banner de privacidad se quedó con el alto libre de la ventana en vez de " +
      "ser una franja: la fila elástica de `.soc-main` volvió al primer hijo",
  ).toBeLessThan(200);

  const conBanner = await boxOf(page.locator(".soc-stage"));
  expect(conBanner, "el escenario desapareció al aparecer el banner").not.toBeNull();
  expect(
    conBanner!.height,
    "el escenario está en su piso de 280 px con el banner presente: se lo comió él",
  ).toBeGreaterThan(400);
  // El mapa cede lo que ocupa la franja y ni un píxel más: si cede de más es que
  // la fila elástica se movió de sitio otra vez.
  expect(sinBanner!.height - conBanner!.height).toBeLessThanOrEqual(banner!.height + 20);
});

test("el último cliente de la lista es visible Y clicable", async ({ page }) => {
  // El bug real: `body { overflow: hidden }` + `.mt__list` sin scroll propio.
  // "Visible" no basta — el elemento existía en el DOM y `getByText` lo
  // encontraba; lo que fallaba era poder LLEGAR a él y pulsarlo.
  await gotoScreen(page, "/tenants", "04 Multi-Tenant");
  const tenants = page.locator(".mt-tenant");
  await expect(tenants.first()).toBeVisible();

  const last = tenants.last();
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeVisible();
  await expect(
    last,
    "el último cliente no es alcanzable: ¿`.mt__list` perdió su overflow-y?",
  ).toBeInViewport();

  await last.click();
  await expect(last).toHaveClass(/is-selected/);
  await expect(page.locator(".mt__detail")).toBeVisible();
});

test.describe("sin desborde horizontal en ninguna pantalla", () => {
  for (const screen of MATRIX_SCREENS) {
    test(screen.path, async ({ page }) => {
      await gotoScreen(page, screen.path, screen.label);
      await expectNoHorizontalOverflow(page);
    });
  }
});

// [T-2.59] Quitar el control nativo de MapLibre quitó un DUPLICADO, no el
// crédito: OpenFreeMap y OpenStreetMap exigen que la atribución se vea, y esa
// obligación no se cumple con un comentario en el código. Si alguien borra
// `.soc-map__attribution` creyendo que sobra, este test lo para.
test("los créditos del mapa siguen visibles sin el control nativo", async ({ page }) => {
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  const attribution = page.locator(".soc-map__attribution");
  await expect(attribution, "el panel se quedó sin atribución propia").toBeVisible();
  await expect(attribution).toContainText("OpenFreeMap");
  await expect(attribution).toContainText("OpenStreetMap");
});
