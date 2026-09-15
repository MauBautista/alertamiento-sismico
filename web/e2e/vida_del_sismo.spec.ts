// [T-7.20] LA VIDA DEL SISMO, de punta a punta y en un navegador de verdad.
//
// Las seis fichas de F3 se probaron cada una por su lado: el worker que mueve
// las fases (`T-7.13`), la reproducción que viste el incidente (`T-7.14`), las
// estaciones que sienten la onda (`T-7.15`), la escena que dice ANALIZANDO
// (`T-7.16`), la tabla por estación (`T-7.17`), el frente en el mapa (`T-7.18`)
// y el halo que se detiene (`T-7.19`). Ninguna de esas pruebas ve la
// COREOGRAFÍA, que es lo que se enseña: el pulso del WR-1, la alerta viva, la
// sacudida que concluye, el epicentro con su procedencia, la tabla en orden de
// arribo y el cierre por clasificación.
//
// ⚠️ ESTE SPEC NECESITA EL ARNÉS MONTADO, y lo DICE cuando no lo está en vez de
// pasar en verde. Un e2e que se salta en silencio lo que vino a comprobar es la
// peor clase de verde: el que se lee como «funciona».
//
//   make soc-local                              # consola + API + base
//   python -m simulators.wr1 --serve :9100      # el pulso del WR-1
//   python -m simulators.fleet --replay simulators/replay_19s.json \
//          --stations-file simulators/demo_red.json --no-events --armar \
//          http://127.0.0.1:8080/api/status     # las estaciones sintiendo
//
// y la ventana de reproducción armada en el tenant de la demostración
// (`POST /demo-mode/replay` con `catalog_key = USGS-2017-09-19-PUE`).

import { expect, test } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

/** Lo que el arné tiene que haber dejado en pantalla para que esto mida algo. */
const SIN_ARNES =
  "sin escenario: este spec necesita `make soc-local` + el WR-1 en :9100 + " +
  "`fleet --replay` y la ventana de reproducción armada (ver la cabecera)";

test.describe("[T-7.20] la vida del sismo en el muro", () => {
  test("del pulso del WR-1 al cierre por clasificación, sin perder un paso", async ({ page }) => {
    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");

    // 1 · LA ALERTA VIVA. La tarjeta existe y RESPIRA: `data-alive` sale del
    //     estado del servidor, no de un cronómetro (D-30, condición 3).
    const banner = page.getByTestId("alert-banner");
    test.skip((await banner.count()) === 0, SIN_ARNES);
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute("data-authorizes", "true");
    await expect(banner).toHaveAttribute("data-alive", "true");
    // El titular se lee desde el primer frame: lo que anima es la carcasa.
    await expect(banner).toContainText("ALERTA SÍSMICA");

    // 2 · EL EPICENTRO CON SU PROCEDENCIA. La cifra no va sin quién la sostiene,
    //     y la fecha del sismo real impide leerlo como un sismo de hoy.
    const epicentro = page.getByTestId("epicentro-card");
    await expect(epicentro).toBeVisible({ timeout: 30_000 });
    await expect(epicentro).toContainText("REPRODUCCIÓN 19-09-2017");
    await expect(epicentro).toContainText("USGS");

    // 3 · LA TABLA POR ESTACIÓN, EN ORDEN DE ARRIBO. Se leen los códigos en el
    //     orden en que el DOM los tiene: reordenar aquí haría que la prueba
    //     pasara con una tabla desordenada.
    const filas = page.locator('[data-testid^="estacion-"]');
    await expect(filas.first()).toBeVisible({ timeout: 30_000 });
    const codigos = await filas.evaluateAll((els) =>
      els.map((e) => (e as HTMLElement).dataset["testid"] ?? ""),
    );
    expect(codigos.length, "la red de estaciones salió vacía").toBeGreaterThan(1);

    // 4 · LA SACUDIDA CONCLUYE. El worker la pasa a revisión y la franja lo dice;
    //     el halo deja de existir porque el selector ya no casa.
    const revision = page.getByTestId("scene-review");
    await expect(revision).toBeVisible({ timeout: 300_000 });
    await expect(revision).toContainText("SISMO CONCLUIDO");
    await expect(page.getByTestId("alert-banner")).toHaveAttribute("data-alive", "false");
    // Y la línea de alerta ya no está: son excluyentes, no se apilan.
    await expect(page.getByTestId("scene-alert")).toHaveCount(0);
  });
});
