// [T-8.06] RECORRIDO DE LA CONSOLA ROL POR ROL, CONTROL POR CONTROL.
//
// La auditoría del 2026-09-22 (AUDITORIA-PRESENTACION-2026-09.md) encontró por
// LECTURA botones que no hacían nada (DESCARGAR CLIP), paneles que pedían al
// servidor lo que el rol no tiene (CCTV, huella, cuórum: 403/404 cada 15 s) y
// avisos rojos permanentes para un rol concreto. Ninguno lo veía un test, porque
// los e2e existentes entran con tres roles y ejercen flujos, no controles.
//
// Este spec entra con CADA UNO de los 10 roles, visita cada ruta que el SERVIDOR
// le concede (`/me.allowed_routes`, más la ficha del edificio) y, en cada una:
//   - recoge errores de página, `console.error` y TODA respuesta HTTP ≥ 400. No hay
//     lista de «esperados» por defecto: un 403 significa que la pantalla pidió algo
//     que el rol no puede tener — eso ES el defecto (regla de oro 7: lo que falla
//     siempre no se pinta). Las excepciones razonadas van en `ESPERADOS`, con razón;
//   - enumera los controles (botones, desplegables, pestañas, menús, enlaces);
//   - pulsa cada control NO MUTANTE y comprueba que haga algo: cambia la URL, abre
//     un diálogo, cambia `aria-expanded/selected/pressed`, lanza una petición, o
//     muta el DOM fuera de lo que ya muta solo (el reloj). Si nada de eso pasa, es
//     un `control_sin_efecto`;
//   - un desplegable sin opciones tiene que declarar su vacío;
//   - los controles MUTANTES (acusar, firmar, ejecutar, borrar…) NO se pulsan aquí:
//     se censan con su rol y los ejercen las specs de flujo (drill, vida_del_sismo…).
//
// Salida: `takab-docs/auditoria/recorrido-web.json` (local) o
// `recorrido-web-nube.json` (con `PW_BASE_URL`), más capturas por rol y ruta en
// `test-results/recorrido/`. El Goal de F2 exige 10 roles y cero inesperados.
//
// NUBE: sin login dev. Cada rol entra con un `storageState` guardado a mano
// (Mauricio entra una vez con contraseña y código):
//   npx playwright open --save-storage=$RECORRIDO_SESIONES/<rol>.json <PW_BASE_URL>
// y se corre con RECORRIDO_SESIONES=<dir>. Los ficheros NO se comitean: son
// sesiones vivas de hasta 30 días (D-38).
import { mkdirSync, readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { SITE_DEV } from "./helpers";

const ROLES = [
  "takab_superadmin",
  "takab_support",
  "tenant_admin",
  "soc_operator",
  "gov_operator",
  "inspector",
  "building_admin",
  "brigadista",
  "security_guard",
  "occupant",
] as const;
type Rol = (typeof ROLES)[number];

/** Roles sin superficie web: deben ver «SIN SUPERFICIE WEB» y nada más (RBAC §2). */
const SOLO_MOVIL: ReadonlySet<string> = new Set(["brigadista", "security_guard", "occupant"]);

/**
 * Rótulos de acciones que CAMBIAN el sistema. No se pulsan en el barrido genérico.
 * Se prefiere pecar de prudente: un control de solo lectura que cae aquí se censa
 * como «mutante no pulsado» y lo cubre una spec de flujo; uno mutante que se
 * escapara ensuciaría la base de las corridas siguientes.
 */
const MUTANTE =
  /ACUS|FIRM|EJECUT|INICIAR|BORR|ELIMIN|SILENCI|PROBAR|DAR DE BAJA|BAJA|DESHABILIT|HABILIT|PUBLICAR|VOLVER A V|RESTAUR|RETIR|GUARDAR|CREAR|AÑADIR|APLICAR|ENVIAR|SALIR|CERRAR SESI|CONFIRMAR|CLASIFIC|REGISTRAR|ROTAR|ABRIR VENTANA|CERRAR VENTANA|AUTODIAGN|GENERAR|DESCARGAR|EXPORTAR|INVITAR|RESET|CONCEDER|REVOCAR|ARMAR|DESARMAR|ACTIVAR|CANCELAR SIMUL|ABORTAR|RENOVAR|ENTRAR|SOLICITAR|DICTAMEN PDF|EJECUTIVO/i;

/** Respuestas ≥ 400 que se aceptan, SIEMPRE con su razón. Vacío a propósito. */
const ESPERADOS: ReadonlyArray<{ rol: string | "*"; metodo: string; ruta: RegExp; razon: string }> =
  [];

interface Hallazgo {
  tipo:
    | "pageerror"
    | "console_error"
    | "http_inesperado"
    | "peticion_fallida"
    | "control_sin_efecto"
    | "select_vacio_sin_estado"
    | "dialogo_no_cierra"
    | "ruta_no_monta"
    | "solo_movil_con_superficie";
  rol: string;
  ruta: string;
  detalle: string;
}

interface Control {
  ruta: string;
  tipo: string;
  rotulo: string;
  resultado:
    | "efecto"
    | "sin_efecto"
    | "mutante_no_pulsado"
    | "deshabilitado"
    | "deshabilitado_sin_causa"
    | "no_visible"
    | "navega";
  detalle?: string;
}

interface InformeRol {
  rol: string;
  rutas: string[];
  controles: Control[];
  hallazgos: Hallazgo[];
}

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const EN_NUBE =
  Boolean(process.env.PW_BASE_URL) && !/localhost|127\.0\.0\.1/.test(process.env.PW_BASE_URL ?? "");
const SALIDA = path.join(
  REPO,
  "takab-docs",
  "auditoria",
  EN_NUBE ? "recorrido-web-nube.json" : "recorrido-web.json",
);
const CAPTURAS = path.join(REPO, "web", "test-results", "recorrido");
const PARCIALES = path.join(CAPTURAS, "_parciales");

// ------------------------------------------------------------------ entrada

/**
 * Entra con el rol y devuelve el `/me` que la PROPIA consola pidió al arrancar.
 * Se escucha la respuesta en vez de reconstruir el token del almacenamiento: dónde
 * guarda la sesión la consola es un detalle que cambia (D-38 la movió a
 * localStorage) y este recorrido no debe depender de él.
 */
async function entrar(page: Page, rol: Rol): Promise<{ allowed_routes: string[] } | null> {
  const meResp = page
    .waitForResponse(
      (r) => r.request().method() === "GET" && /\/me$/.test(new URL(r.url()).pathname),
      { timeout: 20_000 },
    )
    .catch(() => null);
  await page.goto("/");
  if (!EN_NUBE) {
    await expect(
      page.getByText("LOGIN DEV", { exact: false }),
      "No está el panel de login dev: ¿corre `make soc-local` con VITE_DEV_TOKEN_ENABLED=true?",
    ).toBeVisible();
    await page.getByLabel("ROL").selectOption(rol);
    await page.getByRole("button", { name: "ENTRAR COMO ROL" }).click();
  }
  const r = await meResp;
  await page.waitForLoadState("networkidle").catch(() => undefined);
  if (r === null || !r.ok()) return null;
  return (await r.json()) as { allowed_routes: string[] };
}

async function asentar(page: Page): Promise<void> {
  const limite = Date.now() + 12_000;
  while (Date.now() < limite) {
    if ((await page.locator('[data-state="loading"]').count()) === 0) break;
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(600);
}

// --------------------------------------------------- observador de efectos
//
// La consola muta el DOM SOLA (reloj UTC/CST cada segundo, edades del dato,
// latidos). Un «¿mutó algo?» ingenuo daría efecto a cualquier botón. Por eso se
// mide una ventana en reposo, se anotan los nodos que mutan solos, y tras el clic
// solo cuentan las mutaciones de nodos que NO estaban en esa lista.

async function armarObservador(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as {
      __tk_obs?: MutationObserver;
      __tk_muts: Node[];
      __tk_red: number;
    };
    w.__tk_obs?.disconnect();
    w.__tk_muts = [];
    const obs = new MutationObserver((recs) => {
      for (const r of recs) w.__tk_muts.push(r.target);
    });
    obs.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      characterData: true,
    });
    w.__tk_obs = obs;
  });
}

async function nodosQueMutanSolos(page: Page, ms: number): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __tk_muts: Node[] }).__tk_muts = [];
  });
  await page.waitForTimeout(ms);
  await page.evaluate(() => {
    const w = window as unknown as { __tk_muts: Node[]; __tk_solos: Set<Node> };
    w.__tk_solos = new Set(w.__tk_muts);
    w.__tk_muts = [];
  });
}

async function mutacionesNuevas(page: Page): Promise<number> {
  return page.evaluate(() => {
    const w = window as unknown as { __tk_muts: Node[]; __tk_solos?: Set<Node> };
    const solos = w.__tk_solos ?? new Set<Node>();
    const n = w.__tk_muts.filter((m) => !solos.has(m)).length;
    w.__tk_muts = [];
    return n;
  });
}

// ------------------------------------------------------------ el barrido

const SELECTOR_CONTROLES = [
  "button",
  "[role=button]",
  "[role=tab]",
  "[role=menuitem]",
  "[aria-haspopup]",
  "summary",
  "select",
].join(",");

async function barrerRuta(
  page: Page,
  rol: string,
  ruta: string,
  informe: InformeRol,
): Promise<void> {
  const controles = page.locator(SELECTOR_CONTROLES);
  const total = await controles.count();
  const vistos = new Set<string>();

  for (let i = 0; i < total; i++) {
    const c = controles.nth(i);
    if (!(await c.isVisible().catch(() => false))) continue;
    const tag = await c.evaluate((el) => el.tagName.toLowerCase()).catch(() => "?");
    const rotulo = (
      (await c.getAttribute("aria-label")) ??
      (await c.innerText().catch(() => "")) ??
      ""
    )
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 80);
    const clave = `${tag}:${rotulo}`;
    if (vistos.has(clave)) continue; // filas repetidas de una tabla: basta una
    vistos.add(clave);

    if (tag === "select") {
      const opciones = await c.locator("option").count();
      if (opciones === 0) {
        informe.hallazgos.push({
          tipo: "select_vacio_sin_estado",
          rol,
          ruta,
          detalle: rotulo || "(sin rótulo)",
        });
      }
      informe.controles.push({
        ruta,
        tipo: "select",
        rotulo,
        resultado: opciones > 0 ? "efecto" : "sin_efecto",
        detalle: `${opciones} opciones`,
      });
      continue;
    }

    const deshabilitado = await c.isDisabled().catch(() => false);
    if (deshabilitado) {
      const causa = (await c.getAttribute("title")) ?? (await c.getAttribute("aria-describedby"));
      informe.controles.push({
        ruta,
        tipo: tag,
        rotulo,
        resultado: causa ? "deshabilitado" : "deshabilitado_sin_causa",
      });
      continue;
    }
    if (MUTANTE.test(rotulo)) {
      informe.controles.push({ ruta, tipo: tag, rotulo, resultado: "mutante_no_pulsado" });
      continue;
    }

    const url0 = page.url();
    const dialogos0 = await page.locator("[role=dialog], dialog[open]").count();
    const aria0 = await c
      .evaluate((el) =>
        ["aria-expanded", "aria-selected", "aria-pressed"].map((a) => el.getAttribute(a)).join("|"),
      )
      .catch(() => "");
    let peticiones = 0;
    const contar = () => {
      peticiones += 1;
    };
    await nodosQueMutanSolos(page, 1_200);
    page.on("request", contar);
    try {
      await c.click({ timeout: 2_000 });
    } catch (e) {
      page.off("request", contar);
      informe.controles.push({
        ruta,
        tipo: tag,
        rotulo,
        resultado: "no_visible",
        detalle: String(e).slice(0, 120),
      });
      continue;
    }
    await page.waitForTimeout(700);
    page.off("request", contar);
    const mutaciones = await mutacionesNuevas(page);
    const url1 = page.url();
    const dialogos1 = await page.locator("[role=dialog], dialog[open]").count();
    const aria1 = await c
      .evaluate((el) =>
        ["aria-expanded", "aria-selected", "aria-pressed"].map((a) => el.getAttribute(a)).join("|"),
      )
      .catch(() => aria0);

    if (url1 !== url0) {
      informe.controles.push({
        ruta,
        tipo: tag,
        rotulo,
        resultado: "navega",
        detalle: new URL(url1).pathname,
      });
      await page.goto(ruta);
      await asentar(page);
      await armarObservador(page);
      continue;
    }
    if (dialogos1 > dialogos0) {
      informe.controles.push({
        ruta,
        tipo: tag,
        rotulo,
        resultado: "efecto",
        detalle: "abre diálogo",
      });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      if ((await page.locator("[role=dialog], dialog[open]").count()) > dialogos0) {
        informe.hallazgos.push({
          tipo: "dialogo_no_cierra",
          rol,
          ruta,
          detalle: `«${rotulo}» no se cierra con Esc`,
        });
        await page.goto(ruta);
        await asentar(page);
        await armarObservador(page);
      }
      continue;
    }
    const efecto = aria1 !== aria0 || peticiones > 0 || mutaciones > 0;
    informe.controles.push({
      ruta,
      tipo: tag,
      rotulo,
      resultado: efecto ? "efecto" : "sin_efecto",
      detalle: `aria ${aria0}→${aria1} · ${peticiones} peticiones · ${mutaciones} mutaciones`,
    });
    if (!efecto) {
      informe.hallazgos.push({
        tipo: "control_sin_efecto",
        rol,
        ruta,
        detalle: `${tag} «${rotulo}»`,
      });
    }
    // Deshacer lo abierto (menús, desplegables) sin navegar.
    if (aria1 !== aria0 && aria1.startsWith("true")) {
      await page.keyboard.press("Escape").catch(() => undefined);
    }
  }
}

function esperado(rol: string, metodo: string, url: string): string | null {
  const p = new URL(url).pathname;
  const hit = ESPERADOS.find(
    (e) => (e.rol === "*" || e.rol === rol) && e.metodo === metodo && e.ruta.test(p),
  );
  return hit ? hit.razon : null;
}

// ------------------------------------------------------------------ tests

test.describe.configure({ mode: "serial" });

const rolesDelRecorrido: Rol[] = EN_NUBE
  ? ROLES.filter((r) =>
      existsSync(path.join(process.env.RECORRIDO_SESIONES ?? "/nonexistent", `${r}.json`)),
    )
  : [...ROLES];

for (const rol of rolesDelRecorrido) {
  test.describe(`recorrido · ${rol}`, () => {
    if (EN_NUBE) {
      test.use({ storageState: path.join(process.env.RECORRIDO_SESIONES ?? "", `${rol}.json`) });
    }

    test(`${rol}: cada ruta monta y cada control no mutante hace algo`, async ({
      page,
    }, testInfo) => {
      test.skip(
        testInfo.project.name !== "laptop-1440x900",
        "el recorrido corre en un solo viewport",
      );
      test.setTimeout(12 * 60_000);

      const informe: InformeRol = { rol, rutas: [], controles: [], hallazgos: [] };
      let rutaActual = "/";
      page.on("pageerror", (e) =>
        informe.hallazgos.push({
          tipo: "pageerror",
          rol,
          ruta: rutaActual,
          detalle: e.message.slice(0, 300),
        }),
      );
      page.on("console", (m) => {
        if (m.type() === "error") {
          informe.hallazgos.push({
            tipo: "console_error",
            rol,
            ruta: rutaActual,
            detalle: m.text().slice(0, 300),
          });
        }
      });
      page.on("response", (r) => {
        if (r.status() < 400) return;
        const metodo = r.request().method();
        const razon = esperado(rol, metodo, r.url());
        if (razon !== null) return;
        informe.hallazgos.push({
          tipo: "http_inesperado",
          rol,
          ruta: rutaActual,
          detalle: `${metodo} ${new URL(r.url()).pathname} → ${r.status()}`,
        });
      });
      page.on("requestfailed", (r) => {
        const err = r.failure()?.errorText ?? "";
        if (/ERR_ABORTED/.test(err)) return; // navegación que cancela una petición en vuelo
        informe.hallazgos.push({
          tipo: "peticion_fallida",
          rol,
          ruta: rutaActual,
          detalle: `${r.method()} ${new URL(r.url()).pathname} · ${err}`,
        });
      });

      const me = await entrar(page, rol);
      mkdirSync(path.join(CAPTURAS, rol), { recursive: true });

      if (SOLO_MOVIL.has(rol)) {
        await expect(page.getByText("SIN SUPERFICIE WEB")).toBeVisible();
        if ((await page.locator("[data-screen-label]").count()) > 0) {
          informe.hallazgos.push({
            tipo: "solo_movil_con_superficie",
            rol,
            ruta: "/",
            detalle: "ve una pantalla de consola",
          });
        }
        await page.screenshot({ path: path.join(CAPTURAS, rol, "sin-superficie.png") });
        informe.rutas.push("/");
      } else {
        const rutas = (me?.allowed_routes ?? []).filter((r) => r !== "/building");
        if (me === null) {
          // Sin /me no hay recorrido honesto: se toman las pestañas visibles.
          const pestanas = await page
            .locator("nav a[href^='/']")
            .evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).pathname));
          rutas.push(...pestanas);
        }
        if ((me?.allowed_routes ?? []).includes("/building") || rutas.length > 0) {
          rutas.push(`/building/${SITE_DEV}`);
        }
        for (const ruta of [...new Set(rutas)]) {
          rutaActual = ruta;
          informe.rutas.push(ruta);
          await page.goto(ruta);
          await asentar(page);
          const monta = (await page.locator("[data-screen-label]").count()) > 0;
          if (!monta) {
            informe.hallazgos.push({
              tipo: "ruta_no_monta",
              rol,
              ruta,
              detalle: "sin data-screen-label",
            });
            continue;
          }
          await page.screenshot({
            path: path.join(
              CAPTURAS,
              rol,
              `${ruta.replace(/\//g, "_").replace(/^_/, "") || "raiz"}.png`,
            ),
          });
          await armarObservador(page);
          await barrerRuta(page, rol, ruta, informe);
        }
      }

      mkdirSync(PARCIALES, { recursive: true });
      writeFileSync(path.join(PARCIALES, `${rol}.json`), JSON.stringify(informe, null, 2));
    });
  });
}

test.afterAll(async () => {
  if (!existsSync(PARCIALES)) return;
  const informes: InformeRol[] = readdirSync(PARCIALES)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(path.join(PARCIALES, f), "utf-8")) as InformeRol);
  const hallazgos = informes.flatMap((i) => i.hallazgos);
  mkdirSync(path.dirname(SALIDA), { recursive: true });
  writeFileSync(
    SALIDA,
    JSON.stringify(
      {
        base_url: process.env.PW_BASE_URL ?? "http://localhost:5173",
        roles: informes.map((i) => i.rol).sort(),
        resumen: {
          controles: informes.reduce((n, i) => n + i.controles.length, 0),
          por_resultado: informes
            .flatMap((i) => i.controles)
            .reduce<
              Record<string, number>
            >((acc, c) => ({ ...acc, [c.resultado]: (acc[c.resultado] ?? 0) + 1 }), {}),
          hallazgos: hallazgos.length,
        },
        hallazgos,
        detalle: informes,
      },
      null,
      2,
    ) + "\n",
  );
});
