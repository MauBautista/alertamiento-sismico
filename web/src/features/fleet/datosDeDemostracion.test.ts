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

import { esDeDemostracion, siteLabelText } from "./datosDeDemostracion";

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

describe("siteLabelText · [T-6.04] el nombre en texto plano lleva el rótulo", () => {
  it("pega el rótulo al simulado y deja intacto al real", () => {
    expect(siteLabelText("Sitio Sim 001 Puebla", "site-sim-001")).toBe(
      "Sitio Sim 001 Puebla · DEMO",
    );
    expect(siteLabelText("Planta Cholula", "site-cholula-a")).toBe("Planta Cholula");
    expect(siteLabelText("Sin código", null)).toBe("Sin código");
  });
});

// [T-7.11] La RED DE DEMOSTRACIÓN: tres sitios que SÍ van a la nube.
//
// Es la diferencia que hace estos casos distintos de los de arriba. `sim_fleet.sql`
// nunca toca el entorno desplegado, así que su cinta protege una pantalla de
// desarrollo; `demo_red.sql` se aplica a la nube a propósito, y su cinta es lo
// único que separa, en la pantalla que ve un cliente, tres edificios inventados de
// uno que existe y tiene gente dentro.
describe("[T-7.11] la red de demostración lleva cinta", () => {
  it.each([
    ["site-sim-101", "Centro Cívico Demostración · Tlaxcala"],
    ["site-sim-102", "Hospital Demostración · Ciudad de México"],
    ["site-sim-103", "Planta Demostración · Toluca"],
  ])("el sitio %s es de demostración", (codigo) => {
    expect(esDeDemostracion(codigo)).toBe(true);
  });

  it.each(["gw-sim-0101", "gw-sim-0102", "gw-sim-0103"])("el gabinete %s también", (serial) => {
    expect(esDeDemostracion(serial)).toBe(true);
  });

  it.each(["SIM101", "SIM102", "SIM103"])("y el sensor %s", (serial) => {
    expect(esDeDemostracion(serial)).toBe(true);
  });

  it("la estación REAL de Puebla sigue sin cinta", () => {
    // La dirección cara del error: rotular de demostración un edificio con gente
    // dentro es peor que no rotular nada.
    expect(esDeDemostracion("site-dev")).toBe(false);
    expect(esDeDemostracion("gw-dev-0001")).toBe(false);
    expect(esDeDemostracion("R4F74")).toBe(false);
  });
});
