// [T-5.05] El censo se DERIVA del seed, no de una lista escrita aquí.
//
// Si los identificadores esperados se teclearan en este fichero, el test se
// compararía consigo mismo: el día que el seed añadiera `site-sim-021` nadie se
// enteraría. Aquí se leen los dos seeds reales y se exige que la función acierte
// en LAS DOS MITADES por igualdad — todo lo simulado marcado, y **nada** de lo
// real marcado. La segunda mitad es la que importa de verdad: rotular de demo un
// edificio con gente dentro es peor que no rotular nada.
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { esDeDemostracion } from "./datosDeDemostracion";

const RAIZ = resolve(process.cwd(), "..");
const ID_RE = /'(site-[a-z0-9-]+|gw-[a-z0-9-]+|SIM\d+|R4F74)'/g;

function identificadores(seed: string): string[] {
  const sql = readFileSync(join(RAIZ, "db", "seeds", seed), "utf-8");
  return [...new Set([...sql.matchAll(ID_RE)].map((m) => m[1]))].sort();
}

const SIM = identificadores("sim_fleet.sql");
const PROD = identificadores("prod_fleet.sql");

describe("esDeDemostracion · derivado de los seeds, no de una lista", () => {
  it("los dos seeds se leen y traen identificadores (no-vacuidad)", () => {
    // Sin esto, un seed renombrado dejaría los dos censos vacíos y en verde.
    expect(SIM.length).toBeGreaterThanOrEqual(40);
    expect(PROD.length).toBeGreaterThanOrEqual(2);
  });

  it("TODO lo del seed simulado sale marcado", () => {
    expect(SIM.filter((id) => !esDeDemostracion(id))).toEqual([]);
  });

  it("NADA del seed de producción sale marcado", () => {
    expect(PROD.filter((id) => esDeDemostracion(id))).toEqual([]);
  });

  it("no marca por parecido: el prefijo va anclado", () => {
    // Un `includes("sim")` marcaría estos tres, y el tercero es un edificio real.
    for (const id of ["site-simon-01", "gw-similar-1", "SIMONA", "presim-01", "site-sim-x"]) {
      expect(esDeDemostracion(id)).toBe(false);
    }
  });

  it("sin dato no inventa una marca en ninguna dirección", () => {
    expect(esDeDemostracion(null)).toBe(false);
    expect(esDeDemostracion(undefined)).toBe(false);
    expect(esDeDemostracion("")).toBe(false);
  });
});
