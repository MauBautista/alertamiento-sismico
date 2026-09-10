/**
 * [T-6.22 · U-30] LAS PESTAÑAS SE DERIVAN DE LO QUE EL ROL PUEDE HACER.
 *
 * El layout táctico enumeraba cinco pestañas iguales para los cuatro roles, y
 * el reparto no era el de RBAC: `inspector` veía LISTA sin `roster_read` y
 * `building_admin` veía TRIAGE sin `damage_report_submit`. Ninguna de las dos
 * es una fuga —el servidor revalida cada acción—, pero las dos son una promesa
 * que la pantalla no puede cumplir: el inspector abre el pase de lista y se
 * come un 403 donde esperaba una lista de personas.
 *
 * La forma de que no vuelva NO es corregir la lista: es que no haya lista. La
 * pestaña cuelga de la acción, y quien añada una pestaña nueva tiene que decir
 * de qué acción depende — o declarar que es de todo el perfil.
 */
import { PESTANAS_TACTICAS, pestanasVisibles } from "./pestanasTacticas";

/** Las acciones tácticas tal y como las devuelve `/me` (subconjunto). */
function acciones(over: Record<string, boolean> = {}): Record<string, boolean> {
  return { panel_read: true, ...over };
}

const nombres = (as: Record<string, boolean> | null | undefined): string[] =>
  pestanasVisibles(as).map((p) => p.name);

describe("[T-6.22] la pestaña cuelga de la acción, no del rol", () => {
  it("brigadista y security_guard: las dos acciones ⇒ TRIAGE y LISTA", () => {
    const as = acciones({ roster_read: true, damage_report_submit: true });
    expect(nombres(as)).toContain("triage");
    expect(nombres(as)).toContain("lista");
  });

  it("inspector NO ve LISTA: no tiene `roster_read`", () => {
    const as = acciones({ roster_read: false, damage_report_submit: true });
    expect(nombres(as)).not.toContain("lista");
    expect(nombres(as)).toContain("triage");
  });

  it("building_admin NO ve TRIAGE: no tiene `damage_report_submit`", () => {
    const as = acciones({ roster_read: true, damage_report_submit: false });
    expect(nombres(as)).not.toContain("triage");
    expect(nombres(as)).toContain("lista");
  });

  it("los CUATRO ven RUTAS y DIRECTORIO: RBAC §3 se los da a los cinco roles", () => {
    for (const as of [
      acciones({ roster_read: true, damage_report_submit: true }),
      acciones({ roster_read: false, damage_report_submit: true }),
      acciones({ roster_read: true, damage_report_submit: false }),
      acciones(),
    ]) {
      expect(nombres(as)).toContain("rutas");
      expect(nombres(as)).toContain("directorio");
    }
  });

  it("sin acciones (sesión a medio cargar) NO se adivina: default-deny", () => {
    // Lo contrario —enseñarlo todo mientras `/me` no llegue— es la pestaña que
    // aparece y desaparece, y el táctico ya pulsó.
    expect(nombres(null)).not.toContain("lista");
    expect(nombres(undefined)).not.toContain("triage");
    // Y lo que NO depende de una acción sigue estando: sin CUENTA no hay forma
    // de cerrar sesión ni de reintentar.
    expect(nombres(null)).toContain("cuenta");
  });

  it("toda pestaña DECLARA de qué depende: `null` es una decisión escrita", () => {
    // Sin esto, una pestaña nueva entra sin gate y nadie lo nota — que es
    // exactamente cómo llegaron aquí LISTA y TRIAGE.
    for (const p of PESTANAS_TACTICAS) {
      expect(Object.prototype.hasOwnProperty.call(p, "requiere")).toBe(true);
      expect(p.requiere === null || typeof p.requiere === "string").toBe(true);
    }
  });

  it("el orden es estable y CUENTA va al final", () => {
    // La barra no puede reordenarse según lo que el rol pueda hacer: el táctico
    // aprende dónde está cada cosa y en una crisis pulsa sin mirar.
    const todas = PESTANAS_TACTICAS.map((p) => p.name);
    const menos = nombres(acciones({ roster_read: false, damage_report_submit: false }));
    expect(menos).toEqual(todas.filter((n) => menos.includes(n)));
    expect(todas[todas.length - 1]).toBe("cuenta");
  });
});
