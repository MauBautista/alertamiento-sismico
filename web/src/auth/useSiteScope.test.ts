import { describe, expect, it } from "vitest";

import { siteScopeOf } from "./useSiteScope";

const SITIO_A = "11111111-1111-1111-1111-111111111111";
const SITIO_B = "22222222-2222-2222-2222-222222222222";

describe("siteScopeOf (T-2.45) · la insignia declara lo que el SERVIDOR hace", () => {
  it("fase A: el servidor no filtra ⇒ lo dice, aunque el claim venga vacío", () => {
    // El caso que motiva el campo: con `site_scope: []` y sin filtro real, decir
    // "0 ESTACIONES" sería afirmar un alcance que la API no está aplicando.
    const v = siteScopeOf({ site_scope: [], console_scope_enforced: false });
    expect(v.enforced).toBe(false);
    expect(v.label).toBe("ALCANCE · TODO EL TENANT");
    expect(v.label).not.toMatch(/0 ESTACION/);
  });

  it("alcance total declarado con '*'", () => {
    const v = siteScopeOf({ site_scope: "*", console_scope_enforced: false });
    expect(v.label).toBe("ALCANCE · TODO EL TENANT");
    expect(v.hint).toMatch(/todas las estaciones/);
  });

  it("una estación se dice en singular", () => {
    const v = siteScopeOf({ site_scope: [SITIO_A], console_scope_enforced: true });
    expect(v.label).toBe("ALCANCE · 1 ESTACIÓN");
    expect(v.enforced).toBe(true);
    expect(v.siteIds).toEqual([SITIO_A]);
  });

  it("varias estaciones, en plural", () => {
    const v = siteScopeOf({ site_scope: [SITIO_A, SITIO_B], console_scope_enforced: true });
    expect(v.label).toBe("ALCANCE · 2 ESTACIONES");
  });

  it("fase B con cero estaciones: lo declara y dice qué hacer", () => {
    const v = siteScopeOf({ site_scope: [], console_scope_enforced: true });
    expect(v.label).toMatch(/SIN ESTACIONES ASIGNADAS/);
    expect(v.hint).toMatch(/administrador/);
  });

  it("sin sesión no inventa un alcance", () => {
    expect(siteScopeOf(null).enforced).toBe(false);
  });

  it("un /me viejo sin el campo se lee como 'no filtra'", () => {
    // Retrocompatibilidad: el campo es aditivo y por defecto false.
    expect(siteScopeOf({ site_scope: [SITIO_A] }).enforced).toBe(false);
  });
});
