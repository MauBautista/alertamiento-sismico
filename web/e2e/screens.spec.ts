// Batería SISTEMÁTICA pantalla por pantalla, en los tres viewports de la matriz.
//
// Por qué existe además de los specs que ya había: los otros seis miran defectos
// CONCRETOS que ya ocurrieron (el mapa sin alto, los sobrepuestos que chocaban,
// el último cliente inalcanzable, el movimiento reducido). Ninguno recorre las
// seis pantallas haciéndoles las mismas seis preguntas, así que un defecto
// idéntico al ya corregido puede aparecer mañana en OTRA pantalla y nadie se
// entera hasta que un operador lo sufre en turno. Eso ya pasó dos veces:
//
//   · `.mt__list` sin scroll (T-2.51) ⇒ clientes inalcanzables.
//   · `.triage` sin `overflow-y: auto` (T-2.58) ⇒ el MISMO fallo, otra pantalla,
//     reportado por el usuario en campo porque ningún test lo vigilaba ahí.
//
// Las seis preguntas, para cada pantalla y cada viewport:
//   1. ¿Monta y se identifica? (`data-screen-label` + h1 coherente)
//   2. ¿Se llega al final del contenido? (scroll alcanzable de verdad)
//   3. ¿Desborda en horizontal? (en un SOC no hay scroll lateral)
//   4. ¿Hay algún control TAPADO? (hit-test real con `elementFromPoint`)
//   5. ¿Los botones responden y los apagados dicen por qué?
//   6. ¿Los estados obligatorios están declarados? (regla de oro 7)
//
// Se asserta con NÚMEROS en el mensaje: "desborda 214 px" se arregla; "expected
// true" se ignora.
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import {
  SITE_DEV,
  boxOf,
  devLogin,
  expectNoHorizontalOverflow,
  gotoScreen,
  overlapArea,
} from "./helpers";

/** Control que el test PULSA. Solo cosas sin consecuencia física (ver abajo). */
interface Probe {
  /** Cómo se llama en el informe de fallo. */
  readonly what: string;
  /**
   * Selector ESTABLE — nunca uno que dependa del estado que el clic cambia.
   * Con `.triage__seg-btn[aria-pressed="false"]` el locator apuntaba a OTRO
   * botón después del clic (el que acababa de quedar en false) y el test leía
   * "false → false": un falso positivo de "control muerto" causado por el
   * propio test. Se selecciona por posición y se lee el mismo nodo dos veces.
   */
  readonly selector: string;
  /** Índice dentro del selector; por defecto el primero. */
  readonly nth?: number;
}

interface Screen {
  readonly path: string;
  readonly label: string;
  /** Texto EXACTO del h1 de la pantalla. */
  readonly heading: string;
  /** El h1 de la consola es `.soc-vh` (solo para lectores): existe, no se ve. */
  readonly headingHidden?: boolean;
  /** Raíz de la pantalla: la caja que tiene que contener o scrollear todo. */
  readonly root: string;
  /** Lista principal; su ÚLTIMO elemento es el que hay que poder alcanzar. */
  readonly list: string;
  readonly listName: string;
  /**
   * `true`  ⇒ la pantalla scrollea: si el contenido excede, la raíz DEBE tener
   *           `overflow-y: auto|scroll` (es la conducta que T-2.58 restauró).
   * `false` ⇒ videowall: la raíz es `overflow: hidden` y lo que no cabe queda
   *           INVISIBLE, así que la exigencia es la contraria — tiene que caber.
   */
  readonly scrolls: boolean;
  /** Controles inocuos que se pulsan para ver que la pantalla está viva. */
  readonly probes: readonly Probe[];
}

const SCREENS: readonly Screen[] = [
  {
    path: "/console",
    label: "01 Monitoreo en Vivo",
    heading: "Monitoreo en Vivo",
    headingHidden: true,
    root: ".soc-shell",
    list: ".soc-incidents tbody tr",
    listName: "la cola de incidentes",
    scrolls: false,
    probes: [{ what: "el filtro OCULTAR SIN ENLACE", selector: '[data-testid="hide-no-link"]' }],
  },
  {
    path: "/fleet",
    label: "02 Flota Edge",
    heading: "Flota Edge y Estado de Gabinetes",
    root: ".fleet",
    list: ".fleet__grid > *",
    listName: "el inventario de gabinetes",
    scrolls: true,
    probes: [
      { what: "el filtro OCULTAR SIN ENLACE", selector: '.fleet__toggle input[type="checkbox"]' },
    ],
  },
  {
    path: "/triage",
    label: "03 Evaluación Estructural",
    heading: "Evaluación Estructural Post-Sismo",
    root: ".triage",
    list: '[data-testid="triage-row"]',
    listName: "el historial de incidentes",
    scrolls: true,
    // La faceta 1 es CRÍTICOS; la 0 (TODOS) entra ya activa y pulsarla no puede
    // cambiar nada — el test la leería como un control muerto.
    probes: [{ what: "la faceta CRÍTICOS", selector: ".triage__seg-btn", nth: 1 }],
  },
  {
    path: "/tenants",
    label: "04 Multi-Tenant",
    heading: "Matriz Multi-Tenant y Umbrales",
    root: ".mt",
    list: ".mt-tenant",
    listName: "la lista de clientes",
    scrolls: true,
    // El cliente 0 entra ya seleccionado: se pulsa el segundo.
    probes: [{ what: "la ficha del segundo cliente", selector: ".mt-tenant", nth: 1 }],
  },
  {
    path: "/audit",
    label: "05 Auditoría",
    heading: "Bitácora de Auditoría",
    root: ".audit",
    list: '[data-testid="audit-row"]',
    listName: "la bitácora",
    scrolls: true,
    probes: [
      { what: "APLICAR filtros", selector: '[data-testid="audit-filters"] button[type="submit"]' },
    ],
  },
  {
    path: `/building/${SITE_DEV}`,
    label: "05 Dashboard Edificio",
    heading: "DASHBOARD EDIFICIO",
    root: ".bld",
    list: ".bld__card",
    listName: "las tarjetas del edificio",
    scrolls: true,
    probes: [{ what: "el preset del historial", selector: ".bld__card button[aria-pressed]" }],
  },
];

// NADA de lo que se pulsa aquí toca el mundo físico.
//
// Esta batería corre contra el stack REAL (API + worker + gabinete), así que
// "pulsar todos los botones habilitados" significaría probar sirenas, retirar
// gateways, firmar dictámenes y acusar incidentes de verdad — regla de oro 8:
// actuar es un clic HUMANO. Se pulsa solo lo declarado en `probes` —filtros,
// facetas, presets, selección— y el resto de la superficie se verifica SIN
// pulsarla: que sea alcanzable (hit-test) y que si está apagada diga por qué.

interface Covered {
  readonly control: string;
  readonly by: string;
  readonly point: string;
}

/**
 * Controles que el operador NO puede usar, y por qué. Tres formas de perderlos:
 *
 *   1. **Tapado.** Otro elemento recibe el clic. `toBeVisible()` de Playwright
 *      no lo ve: un botón bajo un sobrepuesto es "visible" para el DOM. Lo
 *      único que responde a la pregunta real —"¿si pincho aquí, le doy a
 *      esto?"— es `elementFromPoint`.
 *   2. **Recortado.** Un ancestro `overflow: hidden` se come el control. No hay
 *      barra que sacar ni rueda que girar: está perdido.
 *   3. **Servido a medias.** Sobrevive un trozo demasiado pequeño para leerlo.
 *      Es lo que pasaba con CONFIRMAR ACUSE a 1280×800: 15 de sus 48 px dentro
 *      del `.soc-shell` y el rótulo fuera de la ventana.
 *
 * Lo que NO se cuenta es el elemento simplemente scrolleado fuera de su lista:
 * ese no está perdido, está guardado, y el operador llega con la rueda. Por eso
 * el recorte distingue si el ancestro que corta SCROLLEA o no — sin esa
 * distinción, toda lista larga daría falsos positivos.
 */
async function coveredControls(page: Page, scope: string): Promise<Covered[]> {
  return page.evaluate((rootSel) => {
    const describe = (el: Element | null): string => {
      if (el === null) return "nada (punto fuera del documento)";
      const cls =
        typeof el.className === "string" && el.className.trim() !== ""
          ? `.${el.className.trim().split(/\s+/).join(".")}`
          : "";
      const txt = (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 48);
      return `${el.tagName.toLowerCase()}${cls}${txt === "" ? "" : ` «${txt}»`}`;
    };

    const scrollable = (cs: CSSStyleDeclaration): boolean =>
      ["auto", "scroll"].includes(cs.overflowY) || ["auto", "scroll"].includes(cs.overflowX);

    /** El documento solo rescata lo que se salga si él mismo puede scrollear. */
    const pageScrolls =
      scrollable(getComputedStyle(document.body)) ||
      scrollable(getComputedStyle(document.documentElement));

    /**
     * Rectángulo que SOBREVIVE a los ancestros que clipan y a la ventana, más
     * quién lo recortó y si ese recorte se puede deshacer con la rueda.
     */
    const visibleRect = (
      el: Element,
    ): { rect: DOMRect; clipper: string | null; recoverable: boolean } => {
      let r = el.getBoundingClientRect();
      let clipper: string | null = null;
      let recoverable = false;
      const cut = (box: { left: number; top: number; right: number; bottom: number }): boolean => {
        const x1 = Math.max(r.left, box.left);
        const y1 = Math.max(r.top, box.top);
        const x2 = Math.min(r.right, box.right);
        const y2 = Math.min(r.bottom, box.bottom);
        const shrank = x2 - x1 < r.width - 1 || y2 - y1 < r.height - 1;
        r = new DOMRect(x1, y1, Math.max(0, x2 - x1), Math.max(0, y2 - y1));
        return shrank;
      };

      let p = el.parentElement;
      while (p !== null) {
        const cs = getComputedStyle(p);
        if (cs.overflowX !== "visible" || cs.overflowY !== "visible") {
          if (cut(p.getBoundingClientRect()) && clipper === null) {
            clipper = describe(p);
            recoverable = scrollable(cs);
          }
        }
        p = p.parentElement;
      }
      if (cut({ left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight })) {
        if (clipper === null) {
          clipper = "la ventana";
          recoverable = pageScrolls;
        }
      }
      return { rect: r, clipper, recoverable };
    };

    const out: { control: string; by: string; point: string }[] = [];
    const scopes = [document.querySelector(".soc-topbar"), document.querySelector(rootSel)];
    const seen = new Set<Element>();

    for (const container of scopes) {
      if (container === null) continue;
      const controls = container.querySelectorAll(
        'button, a[href], select, input:not([type="hidden"]), [role="button"]',
      );
      for (const el of controls) {
        if (seen.has(el)) continue;
        seen.add(el);
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none" || Number(cs.opacity) === 0) {
          continue;
        }
        if (el.closest('[aria-hidden="true"]') !== null) continue;

        const natural = el.getBoundingClientRect();
        if (natural.width < 2 || natural.height < 2) continue;
        const { rect, clipper, recoverable } = visibleRect(el);
        // Guardado en una lista con scroll: alcanzable, no perdido.
        if (recoverable) continue;

        const naturalArea = natural.width * natural.height;
        const shown = rect.width < 1 || rect.height < 1 ? 0 : rect.width * rect.height;
        const pct = Math.round((shown / naturalArea) * 100);
        if (pct < 50) {
          out.push({
            control: describe(el),
            by: `recortado por ${clipper ?? "un ancestro"} que NO scrollea — solo se ve el ${pct} % de sus ${Math.round(natural.width)}×${Math.round(natural.height)}px`,
            point: `${Math.round(natural.left)},${Math.round(natural.top)}`,
          });
          continue;
        }

        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const hit = document.elementFromPoint(cx, cy);
        if (hit !== null && (hit === el || el.contains(hit))) continue;
        out.push({
          control: describe(el),
          by: `tapado por ${describe(hit)}`,
          point: `${Math.round(cx)},${Math.round(cy)}`,
        });
      }
    }
    return out;
  }, scope);
}

/** Medida de desbordamiento vertical de una caja, con el `overflow-y` que declara. */
async function boxOverflow(
  page: Page,
  selector: string,
): Promise<{ scroll: number; client: number; overflowY: string } | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el === null) return null;
    return {
      scroll: el.scrollHeight,
      client: el.clientHeight,
      overflowY: getComputedStyle(el).overflowY,
    };
  }, selector);
}

/**
 * Botones apagados que NO explican por qué.
 *
 * Vale el `title` del propio botón, su `aria-describedby`, o el `title` de un
 * ENVOLTORIO a dos niveles. Lo último no es laxitud: un `<button disabled>` no
 * dispara eventos de puntero, así que su tooltip nativo no siempre aparece, y
 * la consola ya resuelve eso envolviéndolo (`gateTitle` en IncidentTable). El
 * test acepta el patrón que el producto usa a propósito; lo que no acepta es el
 * silencio.
 */
async function mutedDisabled(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const explained = (el: Element): boolean => {
      const title = (el.getAttribute("title") ?? "").trim();
      if (title.length >= 3) return true;
      const describedBy = el.getAttribute("aria-describedby");
      if (describedBy !== null) {
        const desc = describedBy
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ")
          .trim();
        if (desc.length >= 3) return true;
      }
      return false;
    };

    const out: string[] = [];
    const nodes = document.querySelectorAll(
      'button[disabled], button[aria-disabled="true"], [role="button"][aria-disabled="true"]',
    );
    for (const el of nodes) {
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;

      let node: Element | null = el;
      let ok = false;
      for (let up = 0; up < 3 && node !== null; up += 1) {
        if (explained(node)) {
          ok = true;
          break;
        }
        node = node.parentElement;
      }
      if (ok) continue;
      const name = (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40);
      out.push(name === "" ? el.tagName.toLowerCase() : name);
    }
    return out;
  });
}

/**
 * Espera a que los marcos de datos de la pantalla dejen de estar CARGANDO.
 *
 * `gotoScreen` solo aguarda al `data-screen-label`, que monta antes que el dato
 * (la trampa que T-2.57 documentó para `.soc-stage`). Medir o pulsar en ese
 * hueco produce fallos que parecen del layout y son una carrera del test.
 */
async function settle(page: Page, root: string): Promise<void> {
  await page
    .locator(`${root} [data-state="loading"]`)
    .first()
    .waitFor({ state: "detached", timeout: 15_000 })
    .catch(() => {
      /* si sigue cargando, el propio test lo dirá con su medida */
    });
}

/** Errores de JS de la página; se arman en cada test y se exigen VACÍOS al final. */
const pageErrors = new WeakMap<Page, string[]>();

function watchErrors(page: Page): void {
  const bag: string[] = [];
  pageErrors.set(page, bag);
  page.on("pageerror", (e) => bag.push(e.message));
}

async function attach(info: TestInfo, name: string, body: string): Promise<void> {
  await info.attach(name, { body, contentType: "text/plain" });
}

/** Pulsa un control inocuo y devuelve qué pasó, para el informe del test. */
async function pulse(page: Page, probe: Probe): Promise<string> {
  const el: Locator = page.locator(probe.selector).nth(probe.nth ?? 0);
  if ((await el.count()) === 0) return `${probe.what}: no está en este estado del stack`;
  if (!(await el.isVisible())) return `${probe.what}: presente pero no visible`;
  if (!(await el.isEnabled())) return `${probe.what}: presente y deshabilitado`;

  const read = async (): Promise<string | null> =>
    el.evaluate((n) => {
      const pressed = n.getAttribute("aria-pressed");
      if (pressed !== null) return pressed;
      if (n instanceof HTMLInputElement && n.type === "checkbox") return String(n.checked);
      return null;
    });

  const before = await read();
  await el.click();
  const after = await read();
  if (before !== null) {
    expect(
      after,
      `${probe.what} no cambió de estado al pulsarlo (siguió en "${before}"): el control está pintado pero muerto`,
    ).not.toBe(before);
  }
  return `${probe.what}: pulsado (${before ?? "sin estado declarado"} → ${after ?? "sin estado declarado"})`;
}

test.beforeEach(async ({ page }) => {
  watchErrors(page);
});

test.afterEach(async ({ page }) => {
  const errors = pageErrors.get(page) ?? [];
  expect(
    errors,
    `la pantalla lanzó ${errors.length} error(es) de JS:\n${errors.join("\n")}`,
  ).toEqual([]);
});

for (const screen of SCREENS) {
  test.describe(`${screen.label}`, () => {
    test.beforeEach(async ({ page }) => {
      await devLogin(page);
      await gotoScreen(page, screen.path, screen.label);
      await settle(page, screen.root);
    });

    test("monta y se identifica con su rótulo y su h1", async ({ page }) => {
      // El `data-screen-label` sobrevive a cambios de copy; el h1 es lo que un
      // lector de pantalla anuncia al entrar. Los dos, o la pantalla es anónima.
      await expect(page.locator(`[data-screen-label="${screen.label}"]`)).toBeVisible();

      const h1 = page.locator("h1");
      // Un h1 por documento: dos títulos de página compiten y el lector de
      // pantalla anuncia el que le toque. El de la consola está oculto a la
      // vista (`.soc-vh`) a propósito — el videowall no tiene sitio para él—,
      // pero sigue en el árbol de accesibilidad.
      expect(
        await h1.count(),
        `la pantalla tiene ${await h1.count()} elementos h1: debe haber exactamente uno`,
      ).toBe(1);
      await expect(h1).toHaveText(screen.heading);
      if (screen.headingHidden !== true) {
        await expect(h1).toBeVisible();
      }
    });

    test(`se llega al final de ${screen.listName}`, async ({ page }, testInfo) => {
      const items = page.locator(screen.list);
      const count = await items.count();
      const over = await boxOverflow(page, screen.root);
      expect(over, `no se encontró la raíz \`${screen.root}\` de la pantalla`).not.toBeNull();
      const excess = over!.scroll - over!.client;
      await attach(
        testInfo,
        `scroll-${screen.path.replace(/\W+/g, "-")}.txt`,
        `raíz ${screen.root}: contenido ${over!.scroll}px en caja ${over!.client}px (excede ${excess}px) · overflow-y: ${over!.overflowY}\n` +
          `${screen.listName}: ${count} elemento(s)`,
      );

      if (screen.scrolls) {
        // La conducta que T-2.58 restauró para `.triage`, congelada para todas:
        // si el contenido no cabe, la caja tiene que poder scrollear. Sin esto
        // el sobrante existe en el DOM y es FÍSICAMENTE inalcanzable bajo
        // `body { overflow: hidden }`.
        if (excess > 1) {
          expect(
            ["auto", "scroll"],
            `\`${screen.root}\` excede su caja en ${excess}px (${over!.scroll} sobre ${over!.client}) ` +
              `y declara overflow-y: ${over!.overflowY} — el sobrante es inalcanzable`,
          ).toContain(over!.overflowY);
        }
      } else {
        // Videowall: la raíz es `overflow: hidden` y no hay barra que sacar. Lo
        // que no cabe no se "scrollea después": desaparece.
        expect(
          excess,
          `el videowall \`${screen.root}\` no cabe: ${over!.scroll}px de contenido en ${over!.client}px ` +
            `de caja, y con overflow: ${over!.overflowY} los ${excess}px sobrantes quedan invisibles`,
        ).toBeLessThanOrEqual(1);
      }

      if (count === 0) {
        // Lista vacía es un resultado legítimo del stack local; lo que NO es
        // legítimo es una caja en blanco. Eso lo exige el test de estados.
        return;
      }
      const last = items.last();
      await last.scrollIntoViewIfNeeded();
      await expect(
        last,
        `el último elemento de ${screen.listName} no llega a la pantalla ni con scroll programático`,
      ).toBeInViewport();
    });

    test("no desborda en horizontal", async ({ page }) => {
      await expectNoHorizontalOverflow(page);
    });

    test("ningún control queda tapado (con el menú del operador abierto y cerrado)", async ({
      page,
    }) => {
      // Cerrado: el estado normal de la pantalla.
      const closed = await coveredControls(page, screen.root);
      expect(
        closed.map((c) => `${c.control} en (${c.point}) ← ${c.by}`),
        `hay ${closed.length} control(es) que el operador no puede usar`,
      ).toEqual([]);

      // Abierto: el menú del operador es DONDE SE CIERRA SESIÓN y ya se perdió
      // dos veces —T-2.45 metió un sexto hijo en una rejilla de cinco columnas y
      // el menú cayó a la fila implícita, encima del título de cada página. Se
      // comprueba en TODAS las rutas porque el fallo era de la barra, no de una
      // pantalla.
      const trigger = page.locator(".soc-user__btn");
      await expect(trigger, "no hay menú de operador en la topbar").toBeVisible();
      await trigger.click();
      await expect(page.locator(".soc-user__menu")).toBeVisible();

      // Con el menú abierto se mide LA BARRA, no la página: un desplegable
      // tapa lo que hay debajo por definición y el operador lo cierra. Lo que
      // no puede pasar es que el desplegable se coma la propia barra (pestañas,
      // insignia de alcance, reloj) ni sus propios controles — el `<input>` del
      // nombre y los botones GUARDAR/SALIR viven DENTRO de `.soc-topbar`, así
      // que este mismo barrido los cubre.
      const open = await coveredControls(page, ".soc-topbar");
      expect(
        open.map((c) => `${c.control} en (${c.point}) ← ${c.by}`),
        `con el menú del operador abierto hay ${open.length} control(es) inalcanzables en la barra`,
      ).toEqual([]);
      await expect(
        page.getByRole("button", { name: "Cerrar sesión" }),
        "el botón SALIR no está en el menú abierto",
      ).toBeVisible();

      // El disparador vive DENTRO de la barra: si se sale, se pinta encima del
      // contenido de la página (la barra mide 64px con overflow visible).
      const topbar = await boxOf(page.locator(".soc-topbar"));
      const btn = await boxOf(trigger);
      expect(topbar, "no se encontró la topbar").not.toBeNull();
      expect(btn, "no se encontró el disparador del menú de operador").not.toBeNull();
      expect(
        btn!.y + btn!.height,
        `el menú del operador termina en y=${Math.round(btn!.y + btn!.height)} y la topbar en ` +
          `y=${Math.round(topbar!.y + topbar!.height)}: se salió de la barra y se pinta sobre la página`,
      ).toBeLessThanOrEqual(topbar!.y + topbar!.height + 1);

      // …y no se pisa con la navegación ni con el título de la página.
      const nav = await boxOf(page.locator(".soc-nav"));
      if (nav !== null) {
        expect(
          overlapArea(btn!, nav),
          `el menú del operador se solapa ${Math.round(overlapArea(btn!, nav))} px² con la navegación`,
        ).toBe(0);
      }
      const title = await boxOf(page.locator("h1"));
      if (title !== null) {
        expect(
          overlapArea(btn!, title),
          `el menú del operador se solapa ${Math.round(overlapArea(btn!, title))} px² con el h1 de la página`,
        ).toBe(0);
      }
    });

    test("los botones vivos responden y los apagados dicen por qué", async ({ page }, testInfo) => {
      // Vivos: se pulsa lo inocuo (ver `_DOCUMENTA_POR_QUE_NO_SE_PULSA_TODO`) y
      // se exige que la pantalla siga montada. Los errores de JS los caza el
      // `afterEach` global, así que un botón que revienta la app no pasa.
      const notes: string[] = [];
      for (const probe of screen.probes) {
        notes.push(await pulse(page, probe));
      }
      await expect(
        page.locator(`[data-screen-label="${screen.label}"]`),
        "la pantalla se desmontó tras pulsar un control inocuo",
      ).toBeVisible();

      // Apagados: un botón gris sin explicación obliga al operador a adivinar
      // en mitad de un turno. Es el contrato que T-2.43 fijó para miniSEED —
      // seis estados, cada uno con su porqué— generalizado a la consola.
      const muted = await mutedDisabled(page);
      await attach(
        testInfo,
        `botones-${screen.path.replace(/\W+/g, "-")}.txt`,
        `${notes.join("\n")}\nApagados sin explicación: ${muted.length === 0 ? "ninguno" : muted.join(" · ")}`,
      );
      expect(
        muted,
        `${muted.length} botón(es) deshabilitados sin title ni aria-describedby: el operador no puede saber qué le falta`,
      ).toEqual([]);
    });

    test("declara los estados obligatorios: nunca una caja en blanco", async ({ page }) => {
      // Regla de oro 7. `StateFrame` es el enforcer y marca `data-state`; lo que
      // este test vigila es que NADIE se salte el marco y deje un panel mudo.
      const frames = page.locator(`${screen.root} [data-state]`);
      const total = await frames.count();
      expect(total, `la pantalla no declara NINGÚN estado de dato`).toBeGreaterThan(0);

      const bad = await page.evaluate((rootSel) => {
        const root = document.querySelector(rootSel);
        if (root === null) return ["no existe la raíz de la pantalla"];
        const allowed = new Set(["loading", "error", "empty", "stale", "ready"]);
        const out: string[] = [];
        for (const el of root.querySelectorAll("[data-state]")) {
          const state = el.getAttribute("data-state") ?? "";
          if (!allowed.has(state)) {
            out.push(`data-state="${state}" no es uno de los cinco estados`);
            continue;
          }
          if (state !== "empty") continue;
          const r = el.getBoundingClientRect();
          const txt = (el.textContent ?? "").replace(/\s+/g, " ").trim();
          if (txt.length < 3) {
            out.push(
              `un panel vacío de ${Math.round(r.width)}×${Math.round(r.height)}px no dice nada: ` +
                "una caja en blanco es peor que un 'sin datos'",
            );
          }
        }
        return out;
      }, screen.root);

      expect(bad, `estados mal declarados:\n${bad.join("\n")}`).toEqual([]);
    });
  });
}

test("el menú del operador cierra la sesión de verdad", async ({ page }) => {
  // El bug de campo era "no hay botón de cerrar sesión": existía, pero aterrizaba
  // fuera de la barra. Que esté colocado no basta — tiene que FUNCIONAR, y eso
  // solo se comprueba pulsándolo y viendo volver el panel de login.
  await devLogin(page);
  await gotoScreen(page, "/console", "01 Monitoreo en Vivo");
  await page.locator(".soc-user__btn").click();
  const salir = page.getByRole("button", { name: "Cerrar sesión" });
  await expect(salir).toBeVisible();
  await salir.click();
  await expect(
    page.getByText("LOGIN DEV", { exact: false }),
    "tras SALIR la consola no volvió al panel de entrada: la sesión sigue viva",
  ).toBeVisible();
});

test("una ruta inexistente da un 404 legible, no una pantalla en blanco", async ({ page }) => {
  // El comodín `*` de routes.tsx es la última red: si un enlace se rompe, el
  // operador tiene que leer que la ruta no existe, no quedarse mirando el fondo.
  await devLogin(page);
  await page.goto("/no-existe-esta-ruta");
  await expect(page.getByRole("heading", { name: "404" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
