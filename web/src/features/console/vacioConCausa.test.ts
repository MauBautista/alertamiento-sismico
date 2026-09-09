/**
 * [T-6.06] El vacío tiene que decir la causa REAL, no la que se escribió el día
 * que el alcance todavía no filtraba.
 *
 * El defecto es de los que solo se ven el día del apply: con
 * `console_scope_enforced` puesto, un operador con cero estaciones asignadas
 * leía «SIN SITIOS VISIBLES EN EL TENANT» sobre un cliente con veintiuna. La
 * frase era falsa y además mandaba a preguntar lo que no era.
 */
import { describe, expect, it } from "vitest";

import { siteScopeOf } from "../../auth/useSiteScope";

import { vacioConCausa } from "./vacioConCausa";

const SIN_ALCANCE = siteScopeOf({ site_scope: "*", console_scope_enforced: false });
const ALCANCE_VACIO = siteScopeOf({ site_scope: [], console_scope_enforced: true });
const ALCANCE_UNO = siteScopeOf({ site_scope: ["s-1"], console_scope_enforced: true });
const ALCANCE_TRES = siteScopeOf({
  site_scope: ["s-1", "s-2", "s-3"],
  console_scope_enforced: true,
});

describe("vacioConCausa", () => {
  it("sin alcance impuesto habla del TENANT, que es lo que se está viendo", () => {
    expect(vacioConCausa("SIN SITIOS VISIBLES", SIN_ALCANCE)).toBe(
      "SIN SITIOS VISIBLES EN EL TENANT",
    );
  });

  it("con alcance impuesto habla del ALCANCE, y dice de cuántas estaciones", () => {
    expect(vacioConCausa("SIN SITIOS VISIBLES", ALCANCE_TRES)).toBe(
      "SIN SITIOS VISIBLES EN SU ALCANCE (3 ESTACIONES)",
    );
    // Singular: un rótulo que dice «1 ESTACIONES» se lee como un error del
    // sistema, y quien lo lee deja de creerse el resto.
    expect(vacioConCausa("SIN SITIOS VISIBLES", ALCANCE_UNO)).toContain("(1 ESTACIÓN)");
  });

  it("sin NINGUNA estación asignada deja de hablar de lo que no hay", () => {
    // Es el caso que motiva la ficha: la pantalla no está vacía porque el
    // cliente esté vacío, sino porque a esta cuenta no le han dado nada.
    const texto = vacioConCausa("SIN SITIOS VISIBLES", ALCANCE_VACIO);
    expect(texto).toContain("SU CUENTA NO TIENE ESTACIONES ASIGNADAS");
    expect(texto).toContain("SOLICITE EL ALTA");
    expect(texto).not.toContain("TENANT");
  });

  it("la ausencia la escribe cada pantalla; el ÁMBITO lo pone esta función", () => {
    // El defecto original fue que cada pantalla escribiera la frase entera: tres
    // dijeron «tenant» y una «alcance».
    expect(vacioConCausa("SIN GABINETES REGISTRADOS", SIN_ALCANCE)).toBe(
      "SIN GABINETES REGISTRADOS EN EL TENANT",
    );
    expect(vacioConCausa("SIN SITIOS CON COORDENADAS", ALCANCE_TRES)).toBe(
      "SIN SITIOS CON COORDENADAS EN SU ALCANCE (3 ESTACIONES)",
    );
  });
});
