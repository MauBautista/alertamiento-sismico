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
import { expect, test } from "@playwright/test";

import { boxOf, devLogin, expectNoHorizontalOverflow, gotoScreen, overlapArea } from "./helpers";

test.beforeEach(async ({ page }) => {
  await devLogin(page);
});

test("los sobrepuestos del escenario no se pisan entre sí", async ({ page }) => {
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  await expect(page.locator(".soc-stage")).toBeVisible();

  // Se miden TODOS los que estén visibles. Los condicionales (alerta sísmica,
  // badge de mapa degradado) pueden no estar según el estado del stack local:
  // `boxOf` devuelve null y quedan fuera. Lo que este test garantiza es que NO
  // PUEDEN chocar los que sí estén — no que estén todos.
  const named: [string, ReturnType<typeof page.locator>][] = [
    ["pila de alertas (arriba-derecha)", page.locator(".soc-stage__overlays")],
    ["estado del mapa (arriba-izquierda)", page.locator(".soc-map__degraded")],
    ["leyendas (abajo-derecha)", page.locator(".soc-map__legends")],
    ["atribución (abajo-izquierda)", page.locator(".soc-map__attribution")],
    ["datos retenidos", page.locator(".soc-wall > .soc-stateframe__stale")],
    // [T-2.59] El control NATIVO de MapLibre no estaba en esta lista, y por eso
    // se coló: se ancla abajo-DERECHA, que es la esquina de las leyendas, y las
    // pisaba 2853 px² (357×8) en los tres viewports. Hoy va desactivado
    // (`attributionControl: false`) porque duplicaba unos créditos que este
    // panel ya pinta; si alguien lo reactiva, que choque aquí y no en el muro.
    [
      "atribución nativa de MapLibre (abajo-derecha)",
      page.locator(".maplibregl-ctrl-bottom-right"),
    ],
  ];

  const boxes: [string, Awaited<ReturnType<typeof boxOf>>][] = [];
  for (const [label, locator] of named) boxes.push([label, await boxOf(locator)]);
  const present = boxes.filter((entry): entry is [string, NonNullable<(typeof entry)[1]>] => {
    return entry[1] !== null;
  });

  for (let i = 0; i < present.length; i += 1) {
    for (let j = i + 1; j < present.length; j += 1) {
      const [labelA, a] = present[i];
      const [labelB, b] = present[j];
      expect(
        overlapArea(a, b),
        `"${labelA}" y "${labelB}" se solapan: se resuelve REUBICANDO uno, no subiendo su z-index`,
      ).toBe(0);
    }
  }

  // Las dos pilas superiores están acotadas al 46 % cada una: la no-colisión es
  // aritmética. Se comprueba el ancho real por si alguien quita el tope.
  const stage = await boxOf(page.locator(".soc-stage"));
  const overlays = await boxOf(page.locator(".soc-stage__overlays"));
  if (stage !== null && overlays !== null) {
    expect(overlays.width).toBeLessThanOrEqual(stage.width * 0.47 + 1);
  }
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
  const SCREENS = [
    { path: "/console", label: "01 Monitoreo en Vivo" },
    { path: "/fleet", label: "02 Flota Edge" },
    { path: "/triage", label: "03 Evaluación Estructural" },
    { path: "/tenants", label: "04 Multi-Tenant" },
    // OJO: `/audit` y `/building/:id` comparten el prefijo "05" en su
    // `data-screen-label` (AuditPage.tsx:66 y BuildingPage.tsx:67). No se
    // renumera aquí para no arrastrar tests ajenos; queda anotado.
    { path: "/audit", label: "05 Auditoría" },
  ];

  for (const screen of SCREENS) {
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
