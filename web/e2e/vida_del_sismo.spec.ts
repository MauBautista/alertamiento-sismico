// [T-7.20] LA VIDA DEL SISMO, de punta a punta y en un navegador de verdad.
//
// Las seis fichas de F3 se probaron cada una por su lado: el worker que mueve
// las fases (`T-7.13`), la reproducción que viste el incidente (`T-7.14`), las
// estaciones que sienten la onda (`T-7.15`), la escena que dice ANALIZANDO
// (`T-7.16`), la tabla por estación (`T-7.17`), el frente en el mapa (`T-7.18`)
// y el halo que se detiene (`T-7.19`). Ninguna de esas pruebas ve la
// COREOGRAFÍA, que es lo que se enseña: el pulso del WR-1, la alerta viva, el
// epicentro con su procedencia, la tabla en orden de arribo, la sacudida que
// concluye y el cierre por clasificación.
//
// ⚠️ ESTE SPEC CONDUCE EL ARNÉS, no lo espera puesto. La primera versión se
// limitaba a mirar la consola y a saltarse el caso si no encontraba la alerta,
// y eso resultó ser **lo mismo que no medir nada**: sin nadie que tocara el
// radio, el caso se saltó en las tres resoluciones sin haber probado una sola
// de las siete fichas. Ahora los estímulos los da la propia prueba, contra los
// mismos puertos que el operador usaría, y lo único que se salta —con su
// motivo— es la ausencia del arnés:
//
//   make soc-local        # consola :5173 · API :8000 · gabinete :8080 y :9100
//
// Lo que la prueba hace por su cuenta: arma la ventana de reproducción, cierra
// el contacto del WR-1, re-arma el gabinete y le da calma al sensor.
//
// **Lo que esta prueba NO conduce, y cómo se añade.** El arribo MEDIDO de cada
// estación sale de la flota sintiendo la onda, que ya se puede correr contra el
// SOC local (`--mode spool`, T-7.20) pero necesita la red de demostración
// sembrada — `make demo-db` no la aplica, porque `demo_red.sql` se pone y se
// quita a mano:
//
//   psql … -f db/seeds/demo_red.sql
//   ( cd edge && uv run python -m simulators.fleet --mode spool \
//       --spool-dir ../.local-soc/cola/gw-sim-0001 \
//       --stations-file simulators/demo_red.json \
//       --replay simulators/replay_19s.json --no-events --t0 now )
//
// Sin eso la tabla enseña el arribo TEÓRICO, que es lo que esta prueba fija; la
// comparación medido↔esperado la cubre `EstacionesTable.test.tsx`.

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { devLogin, gotoScreen } from "./helpers";

/** El SOC local. Puertos fijos: los monta `demo/soc_local.sh`. */
const API = "http://127.0.0.1:8000";
const PANEL = "http://127.0.0.1:8080";
const CONTROL = "http://127.0.0.1:9100";

/** El cliente de la demostración (`db/seeds/prod_fleet.sql`). */
const TENANT = "d0000000-0000-0000-0000-000000000001";

/** El sismo del 19-S: el que más cerca pasó de las cuatro estaciones. */
const CATALOGO = "USGS-2017-09-19-PUE";

const SIN_ARNES =
  "sin escenario: este spec conduce `make soc-local` (consola :5173, API :8000 y " +
  "el gabinete en :8080/:9100). Levántalo y vuelve a correrlo.";

/** Un token de `/dev/token`; superadmin porque armar una reproducción lo exige. */
async function tokenSuperadmin(request: APIRequestContext): Promise<string> {
  const r = await request.post(`${API}/dev/token`, {
    data: { role: "takab_superadmin", tenant_id: TENANT },
  });
  expect(r.ok(), "la API local no forja token de desarrollo").toBeTruthy();
  return ((await r.json()) as { id_token: string }).id_token;
}

/** El incidente más reciente del cliente, que es el que acaba de abrir el pulso. */
async function ultimoIncidente(request: APIRequestContext, jwt: string) {
  const r = await request.get(`${API}/incidents?limit=1`, {
    headers: { Authorization: `Bearer ${jwt}` },
  });
  expect(r.ok()).toBeTruthy();
  const { items } = (await r.json()) as { items: { incident_id: string; state: string }[] };
  return items[0] ?? null;
}

/**
 * Deja la mesa vacía antes de empezar.
 *
 * La prueba mide UNA coreografía y la reconoce por «el incidente que hay en
 * pantalla». Con un incidente vivo de una corrida anterior habría dos, y el
 * clic caería sobre la fila equivocada — un falso rojo que se lee como un
 * defecto del producto.
 *
 * Cierra CLASIFICANDO (`reproduccion`), que es la vía que `D-33` define, y no
 * con un `UPDATE`: así lo que queda en la base es un cierre legítimo con su
 * autor y su causa, no un incidente mutilado. Y sólo puede tocar el SOC local:
 * las tres direcciones de arriba son `127.0.0.1` literales.
 */
async function limpiarLaMesa(request: APIRequestContext, jwt: string): Promise<void> {
  const r = await request.get(`${API}/incidents?live=true`, {
    headers: { Authorization: `Bearer ${jwt}` },
  });
  const { items } = (await r.json()) as { items: { incident_id: string }[] };
  for (const { incident_id } of items) {
    await request.post(`${API}/incidents/${incident_id}/classification`, {
      headers: { Authorization: `Bearer ${jwt}` },
      data: { classification: "reproduccion", note: "cierre previo a vida_del_sismo.spec" },
    });
  }
}

/** ¿Está el arnés en pie? Se pregunta al gabinete, que es lo último en arrancar. */
async function hayArnes(request: APIRequestContext): Promise<boolean> {
  try {
    return (await request.get(`${PANEL}/api/status`, { timeout: 4000 })).ok();
  } catch {
    return false;
  }
}

async function filaDelIncidente(page: Page) {
  return page.locator("tbody tr").first();
}

test.describe("[T-7.20] la vida del sismo en el muro", () => {
  // El episodio se cierra con el reloj de PARED del gabinete
  // (`episode_quiet_s`, 90 s) más el retén de la alerta (`alert_hold_min_s`,
  // 180 s desde que abrió). No hay atajo: son los plazos reales.
  test.setTimeout(480_000);

  test("del pulso del WR-1 al cierre por clasificación, sin perder un paso", async ({
    page,
    request,
  }) => {
    test.skip(!(await hayArnes(request)), SIN_ARNES);

    const jwt = await tokenSuperadmin(request);
    await limpiarLaMesa(request, jwt);

    // 0 · LA VENTANA DE REPRODUCCIÓN. Sin ella el incidente que abra el pulso
    //     es un incidente cualquiera: nadie le pone epicentro ni procedencia.
    const armado = await request.post(`${API}/demo-mode/replay`, {
      headers: { Authorization: `Bearer ${jwt}` },
      data: { catalog_key: CATALOGO, note: "e2e vida_del_sismo" },
    });
    expect(armado.status(), await armado.text()).toBe(201);

    await devLogin(page);
    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");

    // 1 · EL PULSO DEL WR-1. El contacto seco se cierra y el reflejo dispara la
    //     sirena en el gabinete ANTES de que la nube se entere (regla de oro 1).
    const pulso = await request.post(`${CONTROL}/sasmex`);
    expect(pulso.ok(), await pulso.text()).toBeTruthy();
    expect((await pulso.json()).siren_sounding, "el reflejo no sonó").toBe(true);

    // 2 · LA ALERTA VIVA. La tarjeta aparece y RESPIRA: `data-alive` sale del
    //     estado del servidor, no de un cronómetro (`D-30`, condición 3).
    const banner = page.getByTestId("alert-banner");
    await expect(banner).toBeVisible({ timeout: 60_000 });
    await expect(banner).toHaveAttribute("data-authorizes", "true");
    await expect(banner).toHaveAttribute("data-alive", "true");
    // El titular se lee desde el primer frame: lo que anima es la carcasa.
    await expect(banner).toContainText("ALERTA SÍSMICA");

    const incidente = await ultimoIncidente(request, jwt);
    expect(incidente, "el pulso no abrió incidente").not.toBeNull();

    // 3 · EL EXPEDIENTE DEL INMUEBLE. El epicentro y la tabla por estación no
    //     viven en el muro desnudo: los abre el operador al pinchar la fila del
    //     incidente, que es el gesto que ya existía. Pedirlos sin ese clic era
    //     el defecto de la primera versión de este spec.
    await (await filaDelIncidente(page)).click();
    await expect(page.getByTestId("detail-panel")).toBeVisible();

    // 4 · EL EPICENTRO CON SU PROCEDENCIA. La cifra no va sin quién la sostiene,
    //     y la fecha del sismo real impide leerlo como un sismo de hoy.
    const epicentro = page.getByTestId("epicentro-card");
    await expect(epicentro).toBeVisible({ timeout: 30_000 });
    await expect(epicentro).toContainText("REPRODUCCIÓN 19-09-2017");
    await expect(epicentro).toContainText("M7.1");
    await expect(epicentro).toContainText("USGS");

    // 5 · LA TABLA POR ESTACIÓN, EN ORDEN DE ARRIBO. Se leen los códigos en el
    //     orden en que el DOM los tiene: reordenar aquí haría que la prueba
    //     pasara con una tabla desordenada.
    const filas = page.locator('[data-testid^="estacion-"]');
    await expect(filas.first()).toBeVisible({ timeout: 30_000 });
    const codigos = await filas.evaluateAll((els) =>
      els.map((e) => (e as HTMLElement).dataset["testid"] ?? ""),
    );
    expect(codigos.length, "la red de estaciones salió vacía").toBeGreaterThan(1);

    // Y ese orden es EL DEL SERVIDOR, que es el del arribo. Se comprueba contra
    // el endpoint y no contra una lista escrita a mano: qué estaciones haya
    // depende de qué semillas estén puestas —la nube no lleva `sim_fleet.sql`—,
    // pero la propiedad es la misma en las dos. Las dos mitades: el DOM no
    // reordena, y lo que el servidor manda va de menos a más arribo.
    const red = await request.get(`${API}/incidents/${incidente!.incident_id}/estaciones`, {
      headers: { Authorization: `Bearer ${jwt}` },
    });
    const items = (
      (await red.json()) as { items: { site_code: string; t_arribo_teorico_s: number | null }[] }
    ).items;
    expect(codigos).toEqual(items.map((i) => `estacion-${i.site_code}`));
    const arribos = items.map((i) => i.t_arribo_teorico_s).filter((t): t is number => t !== null);
    expect(arribos.length, "ninguna estación tiene arribo esperado").toBeGreaterThan(1);
    expect(arribos, "la tabla no va en orden de arribo").toEqual(
      [...arribos].sort((a, b) => a - b),
    );

    // 6 · LA SACUDIDA CONCLUYE. Dos gestos, en este orden y no en otro: el
    //     operador RE-ARMA el gabinete —la apertura del contacto no desenclava
    //     nada, por diseño— y el sensor vuelve a medir calma. Con el enclavado
    //     puesto el reloj del silencio ni empieza (`EpisodeTracker`), así que
    //     invertirlos deja la alerta puesta para siempre.
    const rearme = await request.post(`${PANEL}/api/reset`);
    expect(rearme.ok(), await rearme.text()).toBeTruthy();
    const calma = await request.post(`${CONTROL}/calma`);
    expect(calma.ok(), await calma.text()).toBeTruthy();

    //     EN EL MURO la revisión la dice LA TARJETA, no la franja: `SceneStrip`
    //     no pinta su línea en `/console` (allí la alerta ya tiene tarjeta
    //     anclada al escenario). Esta prueba pedía `scene-review` en el muro y
    //     por eso destapó lo que faltaba: el videowall seguía gritando «ALERTA
    //     SÍSMICA · PROTÉJASE» con el sismo terminado, y lo único que cambiaba
    //     era que el halo se paraba (`T-7.20`, arreglado en `AlertBanner`).
    const tarjeta = page.getByTestId("alert-banner");
    await expect(tarjeta).toHaveAttribute("data-kind", "review", { timeout: 300_000 });
    await expect(tarjeta).toHaveAttribute("data-alive", "false");
    await expect(tarjeta).toContainText("SISMO CONCLUIDO");
    await expect(tarjeta).not.toContainText("ALERTA SÍSMICA");
    await expect(tarjeta).not.toContainText("PROTÉJASE");

    //     Y EN LAS OTRAS CINCO RUTAS lo dice la franja, con las mismas palabras.
    //     Las dos superficies salen de `alertKind` y de `revision.ts`; que
    //     coincidan en un navegador es lo que impide que vuelvan a divergir.
    await gotoScreen(page, "/fleet", "02 Flota Edge");
    const franja = page.getByTestId("scene-review");
    await expect(franja).toBeVisible({ timeout: 60_000 });
    await expect(franja).toContainText("SISMO CONCLUIDO · ANALIZANDO");
    // La línea de alerta ya no está: son excluyentes, no se apilan.
    await expect(page.getByTestId("scene-alert")).toHaveCount(0);

    // 7 · EL CIERRE POR CLASIFICACIÓN (`D-33`). La vía normal de cierre es que
    //     alguien DIGA qué fue; el TTL es solo la red de seguridad. Y tiene que
    //     notarse en el acto: si el banner siguiera puesto hasta la siguiente
    //     pasada del worker, el operador volvería a pulsar.
    await gotoScreen(
      page,
      `/triage?incident=${incidente!.incident_id}`,
      "03 Evaluación Estructural",
    );
    await page.getByTestId("classify-reproduccion").click();
    await expect(page.getByTestId("classification-current")).toContainText(/REPRODUCCIÓN/i);

    await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
    await expect(page.getByTestId("alert-banner")).toHaveCount(0, { timeout: 60_000 });
    await expect(page.getByTestId("scene-review")).toHaveCount(0);
  });
});
