// Utilidades compartidas por los specs de la matriz de viewports (T-2.56).
//
// No es un spec: Playwright solo recoge `*.spec.ts`, así que este archivo no
// aporta tests aunque viva en `testDir`.
import { expect, type Locator, type Page } from "@playwright/test";

/** Sitio real del seed (`db/seeds/prod_fleet.sql`): site-dev · Puebla. */
export const SITE_DEV = "d1000000-0000-0000-0000-000000000000";

/** Roles del panel de login dev (`/dev/token`, solo con VITE_DEV_TOKEN_ENABLED). */
export type DevRole = "takab_superadmin" | "soc_operator" | "tenant_admin";

/**
 * Entra con el login dev y espera a que la primera pantalla monte.
 *
 * El login aterriza en `/console`; navegar antes de que monte tira la sesión
 * (trampa ya documentada en el smoke de T-1.62), así que aquí se espera SIEMPRE
 * al `data-screen-label` antes de devolver el control.
 */
export async function devLogin(page: Page, role: DevRole = "takab_superadmin"): Promise<void> {
  await page.goto("/");
  await expect(
    page.getByText("LOGIN DEV", { exact: false }),
    "No está el panel de login dev: ¿corre `make soc-local` y web/.env tiene VITE_DEV_TOKEN_ENABLED=true?",
  ).toBeVisible();
  await page.getByLabel("ROL").selectOption(role);
  await page.getByRole("button", { name: "ENTRAR COMO ROL" }).click();
  await expect(page.locator("[data-screen-label]").first()).toBeVisible();
}

/** Entra y navega a `path`, esperando su layout. */
export async function gotoScreen(page: Page, path: string, label: string): Promise<void> {
  await page.goto(path);
  await expect(
    page.locator(`[data-screen-label="${label}"]`),
    `${path} no montó su layout`,
  ).toBeVisible();
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Caja de un elemento VISIBLE y con área; `null` si no está o no ocupa nada. */
export async function boxOf(locator: Locator): Promise<Box | null> {
  if ((await locator.count()) === 0) return null;
  if (!(await locator.first().isVisible())) return null;
  const box = await locator.first().boundingBox();
  if (box === null || box.width < 1 || box.height < 1) return null;
  return box;
}

/**
 * Área de intersección en px². Cero = no se tocan.
 *
 * Se compara ÁREA y no "¿se tocan?" porque un borde compartido de sub-píxel
 * (dos cajas pegadas) no es una colisión y haría el test inestable entre
 * viewports con distinto device pixel ratio.
 */
export function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return w > 1 && h > 1 ? w * h : 0;
}

/** El documento no puede desbordar en horizontal: en un SOC no hay scroll lateral. */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return { scroll: el.scrollWidth, client: el.clientWidth };
  });
  expect(
    overflow.scroll,
    `el documento desborda ${overflow.scroll - overflow.client} px en horizontal`,
  ).toBeLessThanOrEqual(overflow.client + 1);
}

/**
 * Las SEIS pantallas de la consola (las cinco pestañas + la ficha del edificio,
 * que no es pestaña y por eso se quedaba fuera de los barridos — T-6.09).
 */
export const MATRIX_SCREENS = [
  { path: "/console", label: "01 Monitoreo en Vivo" },
  { path: "/fleet", label: "02 Flota Edge" },
  { path: "/triage", label: "03 Evaluación Estructural" },
  { path: "/tenants", label: "04 Multi-Tenant" },
  { path: "/audit", label: "05 Auditoría" },
  { path: `/building/${SITE_DEV}`, label: "06 Dashboard Edificio" },
] as const;

/**
 * Espera a que la pantalla deje de CARGAR y a que las fuentes estén: medir antes
 * da cajas de un texto que aún va en la fuente de respaldo (otro ancho) o de un
 * marco que todavía es un chip «CARGANDO». `gotoScreen` sólo aguarda al
 * `data-screen-label`, que monta antes que el dato (T-2.57).
 */
export async function settle(page: Page, timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if ((await page.locator('[data-state="loading"]').count()) === 0) break;
    await page.waitForTimeout(250);
  }
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  // Un frame más: los sobrepuestos absolutos se colocan tras el primer layout.
  await page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => r())));
}

/** Dos elementos visibles con texto (o controles) cuyas cajas se pisan. */
export interface OverlapPair {
  a: string;
  b: string;
  /** px² de la mayor intersección entre las cajas de línea de uno y otro. */
  area: number;
  boxA: Box;
  boxB: Box;
}

/** Excepción ESCRITA al barrido: dos selectores que pueden pisarse, y por qué. */
export interface AllowedOverlap {
  a: string;
  b: string;
  reason: string;
}

/**
 * [T-7.04] BARRIDO GENERAL DE SOLAPES: cada elemento VISIBLE que tiene texto
 * propio (nodos de texto hijos, no sólo descendientes) o es un control, contra
 * todos los demás. Dos de ellos no pueden intersecarse salvo que uno sea
 * ancestro del otro o la pareja esté en `allowed` con su razón.
 *
 * Qué se mide y por qué así:
 *   · Del texto se toman las cajas de sus NODOS DE TEXTO (`Range.getClientRects`:
 *     una por renglón, con el alto del área de contenido de la fuente —ascendente
 *     + descendente—), no la caja del elemento: un `<span>` que parte en dos
 *     líneas tiene una caja envolvente que «pisa» al hermano que ocupa el hueco
 *     de la segunda línea sin que ningún glifo se toque. Y como el alto es el de
 *     la fuente y no el `line-height`, dos textos apilados con un interlineado
 *     menor que su fuente se pisan aquí aunque los glifos no se toquen: es la
 *     zona donde un descendente SÍ tocaría. De un control se toma su caja
 *     entera: su rótulo es lo que se pulsa.
 *   · Cada caja se recorta con los ancestros que recortan (`overflow` ≠ visible) y
 *     con la ventana —o con el documento, si es él quien scrollea—: lo que está
 *     guardado en una lista con scroll no está encimado, está fuera de vista.
 *   · La tolerancia es la de `overlapArea`: un borde compartido de sub-píxel no
 *     es una colisión.
 *
 * Qué NO ve (y se declara): texto dibujado en `<canvas>` (los rótulos DEMO del
 * mapa van en una capa de símbolos de MapLibre con `text-allow-overlap`), texto
 * dentro de `<svg>` y el contenido de pseudo-elementos.
 */
export async function textOverlaps(
  page: Page,
  allowed: readonly AllowedOverlap[] = [],
): Promise<OverlapPair[]> {
  return page.evaluate((allowedIn) => {
    interface R {
      left: number;
      top: number;
      right: number;
      bottom: number;
    }
    const SKIP = new Set([
      "SCRIPT",
      "STYLE",
      "NOSCRIPT",
      "TEMPLATE",
      "CANVAS",
      "BR",
      "WBR",
      "OPTION",
      "IFRAME",
      "VIDEO",
      "AUDIO",
      "IMG",
      "PICTURE",
      "SOURCE",
    ]);
    const CONTROL =
      "button, a[href], select, textarea, input:not([type=hidden]), [role=button], " +
      "[role=link], [role=tab], [role=menuitem], [role=checkbox], [role=radio], [role=switch]";

    const root = document.documentElement;
    const rootCs = getComputedStyle(root);
    const bodyCs = getComputedStyle(document.body);
    // El viewport scrollea salvo que html (o body, si html es visible) lo impida.
    const viewportOverflow = rootCs.overflowY !== "visible" ? rootCs.overflowY : bodyCs.overflowY;
    const pageScrolls = viewportOverflow !== "hidden" && viewportOverflow !== "clip";
    const clipBox: R = pageScrolls
      ? {
          left: -window.scrollX,
          top: -window.scrollY,
          right: root.scrollWidth - window.scrollX,
          bottom: root.scrollHeight - window.scrollY,
        }
      : { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };

    const toR = (d: DOMRect): R => ({ left: d.left, top: d.top, right: d.right, bottom: d.bottom });
    const inter = (a: R, b: R): R | null => {
      const r: R = {
        left: Math.max(a.left, b.left),
        top: Math.max(a.top, b.top),
        right: Math.min(a.right, b.right),
        bottom: Math.min(a.bottom, b.bottom),
      };
      return r.right - r.left > 0 && r.bottom - r.top > 0 ? r : null;
    };
    const clips = (cs: CSSStyleDeclaration): boolean =>
      cs.overflowX !== "visible" || cs.overflowY !== "visible";

    /** Recorte que sufre el CONTENIDO de `el` (sus ancestros que recortan, él mismo y la ventana). */
    const clipCache = new Map<Element, R | null>();
    const clipOf = (el: Element): R | null => {
      const hit = clipCache.get(el);
      if (hit !== undefined) return hit;
      const cs = getComputedStyle(el);
      let box: R | null;
      if (cs.position === "fixed") box = clipBox;
      else box = el.parentElement === null ? clipBox : clipOf(el.parentElement);
      if (box !== null && clips(cs)) box = inter(box, toR(el.getBoundingClientRect()));
      clipCache.set(el, box);
      return box;
    };

    /** `display: none` u `opacity: 0` en el elemento o en un ancestro: no se ve. */
    const goneCache = new Map<Element, boolean>();
    const gone = (el: Element): boolean => {
      const hit = goneCache.get(el);
      if (hit !== undefined) return hit;
      const cs = getComputedStyle(el);
      const g =
        cs.display === "none" ||
        Number(cs.opacity) === 0 ||
        (el.parentElement !== null && gone(el.parentElement));
      goneCache.set(el, g);
      return g;
    };

    const describe = (el: Element): string => {
      const one = (n: Element): string => {
        const cls =
          typeof n.className === "string" && n.className.trim() !== ""
            ? `.${n.className.trim().split(/\s+/).slice(0, 3).join(".")}`
            : "";
        const id = n.id !== "" ? `#${n.id}` : "";
        const tid = n.getAttribute("data-testid");
        return `${n.tagName.toLowerCase()}${id}${cls}${tid === null ? "" : `[data-testid=${tid}]`}`;
      };
      const own = Array.from(el.childNodes)
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent ?? "")
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      const txt = (own === "" ? (el.textContent ?? "") : own).replace(/\s+/g, " ").trim();
      const chain: string[] = [one(el)];
      let p = el.parentElement;
      for (let up = 0; up < 2 && p !== null && p !== document.body; up += 1) {
        chain.unshift(one(p));
        p = p.parentElement;
      }
      return `${chain.join(" > ")}${txt === "" ? "" : ` «${txt.slice(0, 40)}»`}`;
    };

    interface Item {
      el: Element;
      rects: R[];
      label: string;
    }
    const items: Item[] = [];
    for (const el of document.body.querySelectorAll("*")) {
      if (SKIP.has(el.tagName.toUpperCase())) continue;
      if (el.closest("svg") !== null) continue;
      if (gone(el)) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility !== "visible") continue;
      const control = el.matches(CONTROL);
      // El rótulo de un control ya está dentro de la caja del control.
      if (!control && el.parentElement !== null && el.parentElement.closest(CONTROL) !== null) {
        continue;
      }
      const clip = el.parentElement === null ? clipBox : clipOf(el.parentElement);
      if (clip === null) continue;
      let rects: R[] = [];
      if (control) {
        const r = inter(clip, toR(el.getBoundingClientRect()));
        if (r !== null) rects.push(r);
      } else {
        const own = clipOf(el);
        if (own === null) continue;
        for (const node of el.childNodes) {
          if (node.nodeType !== Node.TEXT_NODE || !/\S/.test(node.textContent ?? "")) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const d of range.getClientRects()) {
            const r = inter(own, toR(d));
            if (r !== null) rects.push(r);
          }
        }
      }
      rects = rects.filter((r) => r.right - r.left >= 2 && r.bottom - r.top >= 2);
      if (rects.length === 0) continue;
      items.push({ el, rects, label: describe(el) });
    }

    // Misma tolerancia que `overlapArea`: w > 1 y h > 1.
    const area = (a: R, b: R): number => {
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      return w > 1 && h > 1 ? w * h : 0;
    };
    const box = (r: R) => ({
      x: Math.round(r.left),
      y: Math.round(r.top),
      width: Math.round(r.right - r.left),
      height: Math.round(r.bottom - r.top),
    });
    const excused = (a: Element, b: Element): boolean =>
      allowedIn.some(
        (x) =>
          (a.closest(x.a) !== null && b.closest(x.b) !== null) ||
          (a.closest(x.b) !== null && b.closest(x.a) !== null),
      );

    const out: {
      a: string;
      b: string;
      area: number;
      boxA: ReturnType<typeof box>;
      boxB: ReturnType<typeof box>;
    }[] = [];
    for (let i = 0; i < items.length; i += 1) {
      for (let j = i + 1; j < items.length; j += 1) {
        const A = items[i];
        const B = items[j];
        if (A.el.contains(B.el) || B.el.contains(A.el)) continue;
        let best = 0;
        let ra = A.rects[0];
        let rb = B.rects[0];
        for (const x of A.rects) {
          for (const y of B.rects) {
            const v = area(x, y);
            if (v > best) {
              best = v;
              ra = x;
              rb = y;
            }
          }
        }
        if (best === 0 || excused(A.el, B.el)) continue;
        out.push({ a: A.label, b: B.label, area: Math.round(best), boxA: box(ra), boxB: box(rb) });
      }
    }
    return out.sort((p, q) => q.area - p.area);
  }, allowed as AllowedOverlap[]);
}

/** Una línea por solape, con la medida: «expected []» no se arregla, «312 px²» sí. */
export function formatOverlap(p: OverlapPair): string {
  const at = (b: Box): string => `${b.x},${b.y} ${b.width}×${b.height}`;
  return `${p.a} ∩ ${p.b} = ${p.area} px² (A en ${at(p.boxA)} · B en ${at(p.boxB)})`;
}
