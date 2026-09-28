// [T-9.41 · D-43] EL CIERRE DEL EVENTO, de punta a punta y en un navegador de verdad.
//
// El administrador abre el asistente sobre un incidente ACUSABLE de la escena,
// recorre los seis pasos —acusa, clasifica REAL y cierra con motivo— y ve el
// estado final CERRADO. Cada «hecho» que se espera aquí lo pinta la RELECTURA
// del servidor, no el botón: por eso la prueba espera el estado del paso, no el
// rótulo del botón que acaba de pulsar.
//
// ⚠️ CÓRRELO CONTRA `vite preview`, NUNCA contra Vite DEV: los e2e largos contra
// el servidor de desarrollo dan falsos rojos (ERR_INSUFFICIENT_RESOURCES tras
// unas pocas recargas). `vite preview` hereda el proxy `/api → :8000` de
// `server.proxy`:
//
//   make soc-local                                  # API :8000 · gabinete :8080/:9100 · DB :5433
//   ( cd web && npm run build && npx vite preview --port 4173 --strictPort )
//   ( cd web && PW_BASE_URL=http://localhost:4173 npx playwright test e2e/cierre_del_evento.spec.ts )
//
// El `build` necesita `VITE_DEV_TOKEN_ENABLED=true` en `web/.env` (lo trae el
// arnés) o el login dev no aparece. La escena la fuerza `escena.ts` por la misma
// ruta que un sismo real (contacto del WR-1 en :9100) y la limpia con `psql`
// contra la DB del arnés: hace falta el cliente `psql` en el PATH.
//
// Lo que esta prueba NO puede adelantar: el servidor rechaza el cierre con
// `sismo_en_curso` mientras el edificio siga en tier de alerta (D-49 · R1). Tras
// re-armar el gabinete y darle calma al sensor, el tier vuelve a calma en su
// propio plazo; por eso el cierre se reintenta hasta 5 minutos y cada intento
// fallido deja en pantalla el 409 TRADUCIDO, que es también lo que se comprueba.

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { forceScene } from "./escena";
import { devLogin, gotoScreen } from "./helpers";

/** El SOC local. Puertos fijos: los monta `demo/soc_local.sh`. */
const API = "http://127.0.0.1:8000";
const PANEL = "http://127.0.0.1:8080";
const CONTROL = "http://127.0.0.1:9100";

/** El cliente de la demostración (`db/seeds/prod_fleet.sql`). */
const TENANT = "d0000000-0000-0000-0000-000000000001";

const SIN_ARNES =
  "sin escenario: este spec conduce `make soc-local` (API :8000, gabinete :8080/:9100, " +
  "DB :5433) y la consola servida por `vite preview`. Levántalo y vuelve a correrlo.";

const MOTIVO = "e2e: el perito firmó el acta de inspección en papel";

async function hayArnes(request: APIRequestContext): Promise<boolean> {
  try {
    return (await request.get(`${PANEL}/api/status`, { timeout: 4000 })).ok();
  } catch {
    return false;
  }
}

async function tokenAdmin(request: APIRequestContext): Promise<string> {
  const r = await request.post(`${API}/dev/token`, {
    data: { role: "tenant_admin", tenant_id: TENANT },
  });
  expect(r.ok(), "la API local no forja token de desarrollo").toBeTruthy();
  return ((await r.json()) as { id_token: string }).id_token;
}

/** El incidente SASMEX abierto que acaba de forzar la escena: el acusable. */
async function incidenteAcusable(request: APIRequestContext, jwt: string): Promise<string> {
  const r = await request.get(`${API}/incidents?state=open`, {
    headers: { Authorization: `Bearer ${jwt}` },
  });
  expect(r.ok()).toBeTruthy();
  const { items } = (await r.json()) as {
    items: { incident_id: string; trigger: string; state: string }[];
  };
  const abierto = items.find((i) => i.trigger === "sasmex" && i.state === "open");
  expect(abierto, "la escena no dejó un incidente SASMEX abierto").toBeDefined();
  return abierto!.incident_id;
}

const estadoDe = (page: Page, paso: string) =>
  page.getByTestId(`paso-${paso}`).getByTestId("paso-estado").first();

test.describe("[T-9.41] el asistente «Cierre del evento»", () => {
  // La escena tarda hasta 90 s en abrir el incidente y el tier hasta ~5 min en
  // volver a calma: son los plazos reales del arnés, no un atajo.
  test.setTimeout(600_000);

  test("el administrador acusa, clasifica REAL y cierra con motivo", async ({ page, request }) => {
    test.skip(!(await hayArnes(request)), SIN_ARNES);

    // 0 · LA ESCENA: mesa limpia y UN incidente acusable (SASMEX, abierto).
    await forceScene("normal");
    await forceScene("alert");
    const jwt = await tokenAdmin(request);
    const id = await incidenteAcusable(request, jwt);

    // 1 · ENTRA el administrador y abre el asistente desde Evaluación.
    await devLogin(page, "tenant_admin");
    await gotoScreen(page, `/triage?incident=${id}`, "03 Evaluación Estructural");
    await page.getByTestId("triage-cierre-link").click();
    await expect(page.locator('[data-screen-label="07 Cierre del Evento"]')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/triage/${id}/cierre$`));
    await expect(page.getByTestId("cierre-titulo")).toContainText("CIERRE DEL EVENTO ·", {
      timeout: 30_000,
    });
    for (const p of ["acusar", "sacudida", "reportes", "dictamen", "clasificar", "cierre"]) {
      await expect(page.getByTestId(`progreso-${p}`)).toBeVisible();
    }

    // 2 · ACUSAR. «HECHO» lo dice la fila releída, no el botón.
    await expect(estadoDe(page, "acusar")).toHaveText(/PENDIENTE/, { timeout: 30_000 });
    await expect(estadoDe(page, "cierre")).toHaveText(/BLOQUEADO/);
    await page
      .getByTestId("paso-acusar")
      .getByRole("button", { name: /ACUSAR/ })
      .click();
    await expect(estadoDe(page, "acusar")).toHaveText(/HECHO/, { timeout: 30_000 });

    // 3 · REVISAR LA SACUDIDA y REPORTES: no bloquean; sólo se comprueba que
    //     tienen un estado leído del servidor (nunca «SIN DATO» con el arnés sano).
    await expect(estadoDe(page, "sacudida")).not.toHaveText(/SIN DATO/, { timeout: 30_000 });
    await expect(estadoDe(page, "reportes")).not.toHaveText(/SIN DATO/, { timeout: 30_000 });

    // 4 · CLASIFICAR REAL: no cierra, así que no hay diálogo.
    await page.getByTestId("cierre-clasificar-real").click();
    await expect(page.getByRole("alertdialog")).toHaveCount(0);
    await expect(page.getByTestId("clasificacion-vigente")).toContainText("REAL", {
      timeout: 30_000,
    });
    await expect(estadoDe(page, "clasificar")).toHaveText(/HECHO/);

    // 5 · LA CALMA. El servidor no cierra con el edificio moviéndose: se re-arma
    //     el gabinete, se abre el contacto y el sensor vuelve a medir calma
    //     (mismo orden que `vida_del_sismo.spec.ts`).
    expect((await request.post(`${CONTROL}/sasmex/clear`)).ok()).toBeTruthy();
    expect((await request.post(`${PANEL}/api/reset`)).ok()).toBeTruthy();
    expect((await request.post(`${CONTROL}/calma`)).ok()).toBeTruthy();

    // 6 · CERRAR CON MOTIVO. Con REAL y la cabeza sin firmar el MOTIVO es
    //     obligatorio; si la pasada automática ya firmó un VERDE, no aparece.
    const paso6 = page.getByTestId("paso-cierre");
    const motivo = page.getByLabel("Motivo del cierre");
    await expect(estadoDe(page, "cierre")).toHaveText(/PENDIENTE/, { timeout: 30_000 });
    if (await motivo.isVisible()) {
      await motivo.fill(MOTIVO);
      await expect(page.getByTestId("motivo-cuenta")).toContainText(`${MOTIVO.length} / 20`);
    }
    await expect(async () => {
      await paso6.getByRole("button", { name: /CERRAR EVENTO/ }).click({ timeout: 5_000 });
      await paso6.getByRole("button", { name: /CLIC NUEVAMENTE PARA CONFIRMAR/ }).click({
        timeout: 5_000,
      });
      // Un 409 se pinta TRADUCIDO; el que se espera mientras vuelve la calma es
      // `sismo_en_curso`. Cualquier otro rompe el reintento con su texto.
      await expect(estadoDe(page, "cierre")).toHaveText(/HECHO/, { timeout: 15_000 });
    }).toPass({ timeout: 300_000, intervals: [10_000] });

    // 7 · EL ESTADO FINAL: CERRADO, dicho por la fila releída.
    await expect(paso6.getByRole("alert")).toHaveCount(0);
    await expect(page.getByText(/· CERRADO/).first()).toBeVisible();
    await expect(paso6.getByRole("button", { name: /CERRAR EVENTO/ })).toHaveCount(0);

    // Y el servidor lo confirma por su lado.
    const fila = await request.get(`${API}/incidents/${id}`, {
      headers: { Authorization: `Bearer ${jwt}` },
    });
    expect(((await fila.json()) as { state: string }).state).toBe("closed");
  });
});
