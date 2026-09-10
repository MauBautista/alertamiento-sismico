// [T-6.19] LA FRANJA VIVE EN EL NAVEGADOR, NO EN UNA PESTAÑA — y se mide.
//
// U-32: el simulacro y el modo demostración sólo se veían en INICIO; en RUTAS,
// DIRECTORIO y CUENTA no había rastro, y el brigadista (U-02) no los veía en
// ninguna parte. La garantía de «se ve igual en todas las pestañas» es
// estructural: la franja se monta UNA vez en el layout de cada pestañera, y
// ninguna pantalla la monta por su cuenta. Este test lo deriva del sistema de
// ficheros (la tabla de rutas de `expo-router`), no de una lista.
//
// Y la segunda mitad: la franja solapa la banda superior que las pestañas
// reservan para la barra de estado (`TAB_SCREEN_TOP_RESERVE`). Si una pantalla
// deja de reservar esos 64, la franja abre un hueco o tapa contenido, y este
// test lo dice con el nombre del fichero.
/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { TAB_SCREEN_TOP_RESERVE } from "@/features/notices/drillNotice";

const SRC = resolve(process.cwd(), "src");
const GRUPOS = ["(occupant)", "(brigadista)"] as const;

function leer(rel: string): string {
  return readFileSync(join(SRC, rel), "utf8");
}

/**
 * Cierre transitivo de lo que una pestaña importa desde `@/features/...`:
 * CUENTA llega a su vista en dos saltos (`cuenta.tsx` → `AccountScreen` →
 * `AccountView`), y la reserva de 64 vive en el último.
 */
function vistasImportadas(texto: string, vistas = new Set<string>(), hondura = 0): string[] {
  if (hondura > 4) {
    return [...vistas];
  }
  const destinos: string[] = [];
  for (const m of texto.matchAll(/from "@\/features\/([^"]+)"/g)) {
    destinos.push(`features/${m[1]}.tsx`);
  }
  // [T-6.22] Y una ruta que REEXPORTA otra: las dos pestañas que el táctico
  // estrenó (`rutas`, `directorio`) son el MISMO módulo que las del ocupante,
  // no una copia. Sin seguir el salto, este barrido las acusaría de no reservar
  // la banda superior — cuando la reserva está donde siempre estuvo.
  for (const m of texto.matchAll(/from "\.\.\/(\([a-z]+\)\/[a-z]+)"/g)) {
    destinos.push(`app/${m[1]}.tsx`);
  }
  for (const rel of destinos) {
    if (vistas.has(rel)) {
      continue;
    }
    let fuente: string;
    try {
      fuente = leer(rel);
    } catch {
      continue;
    }
    vistas.add(rel);
    vistasImportadas(fuente, vistas, hondura + 1);
  }
  return [...vistas];
}

describe("la franja de avisos del sitio", () => {
  it("se monta en el layout de las DOS pestañeras", () => {
    for (const grupo of GRUPOS) {
      const layout = leer(`app/${grupo}/_layout.tsx`);
      expect(layout).toContain("<SiteNotices />");
      // …y ANTES del navegador, para que quede encima de cualquier pestaña.
      expect(layout.indexOf("<SiteNotices />")).toBeLessThan(layout.indexOf("<Tabs"));
    }
  });

  it("ninguna pestaña la monta por su cuenta (se vería doble, o distinta)", () => {
    const pestañas = GRUPOS.flatMap((g) =>
      readdirSync(join(SRC, "app", g))
        .filter((f) => f.endsWith(".tsx") && f !== "_layout.tsx")
        .map((f) => `app/${g}/${f}`),
    );
    expect(pestañas.length).toBeGreaterThanOrEqual(9);
    for (const rel of pestañas) {
      const texto = leer(rel);
      const vistas = vistasImportadas(texto).map(leer);
      for (const fuente of [texto, ...vistas]) {
        expect(fuente).not.toContain("SiteNotices");
        expect(fuente).not.toContain("drill-banner");
        expect(fuente).not.toContain("demo-mode-banner");
      }
    }
  });

  it("toda pestaña reserva la banda superior que la franja solapa", () => {
    const pestañas = GRUPOS.flatMap((g) =>
      readdirSync(join(SRC, "app", g))
        .filter((f) => f.endsWith(".tsx") && f !== "_layout.tsx")
        .map((f) => `app/${g}/${f}`),
    );
    const sinReserva: string[] = [];
    for (const rel of pestañas) {
      const texto = leer(rel);
      const fuentes = [texto, ...vistasImportadas(texto).map(leer)];
      const reserva = new RegExp(`paddingTop:\\s*${TAB_SCREEN_TOP_RESERVE}\\b`);
      if (!fuentes.some((f) => reserva.test(f))) {
        sinReserva.push(rel);
      }
    }
    expect(sinReserva).toEqual([]);
  });
});
