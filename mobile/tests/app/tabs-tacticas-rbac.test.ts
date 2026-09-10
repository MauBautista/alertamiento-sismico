/**
 * [T-6.22 · U-30] LA BARRA TÁCTICA, CRUZADA CONTRA LA MATRIZ DE RBAC.
 *
 * `pestanasTacticas.test.ts` comprueba la REGLA con acciones sintéticas. Lo que
 * falta —y es lo que se rompió— es que la regla case con lo que el servidor le
 * concede de verdad a cada rol. La matriz no se copia aquí: se lee de
 * `shared/fixtures/rbac-matrix.json`, que `scripts/export_rbac_matrix.py`
 * genera desde `api/src/takab_api/auth/matrix.py` y `make drift` vigila. Si
 * mañana el inspector gana `roster_read` en el servidor, la pestaña aparece y
 * este test sigue en verde sin tocar nada; si alguien la enseña SIN la acción,
 * se pone rojo con el nombre del rol.
 */
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { PESTANAS_TACTICAS, pestanasVisibles } from "@/auth/pestanasTacticas";
import { TACTICAL_ROLES } from "@/auth/profileGate";

interface Matriz {
  actions: string[];
  roles: Record<string, { actions: Record<string, boolean> }>;
}

const MATRIZ: Matriz = JSON.parse(
  readFileSync(resolve(process.cwd(), "..", "shared", "fixtures", "rbac-matrix.json"), "utf8"),
);

const TACTICOS = [...TACTICAL_ROLES].sort();

describe("[T-6.22] las pestañas del táctico cuadran con la matriz de RBAC", () => {
  it("el fixture trae los cuatro roles tácticos (si no, esto no mira nada)", () => {
    expect(TACTICOS).toEqual(["brigadista", "building_admin", "inspector", "security_guard"]);
    for (const rol of TACTICOS) {
      expect(MATRIZ.roles[rol]).toBeDefined();
    }
  });

  it("toda acción que una pestaña exige EXISTE en la matriz", () => {
    // Una pestaña colgada de una acción mal escrita se apagaría para todo el
    // mundo, para siempre, y en silencio: `actions?.[nombre] === true` sobre un
    // nombre inexistente es `undefined`.
    const exigidas = PESTANAS_TACTICAS.map((p) => p.requiere).filter(
      (a): a is string => a !== null,
    );
    expect(exigidas.length).toBeGreaterThan(0);
    for (const a of exigidas) {
      expect(MATRIZ.actions).toContain(a);
    }
  });

  it.each(TACTICOS)("%s ve exactamente lo que puede usar", (rol) => {
    // Los desajustes se ACUMULAN y se afirman de golpe: `expect` de jest no
    // admite mensaje, así que el nombre de la pestaña tiene que salir en el
    // valor comparado o el fallo no dice cuál de las siete es.
    const acciones = MATRIZ.roles[rol].actions;
    const visibles = new Set(pestanasVisibles(acciones).map((p) => p.name));
    const desajustes: string[] = [];
    for (const p of PESTANAS_TACTICAS) {
      const deberia = p.requiere === null || acciones[p.requiere] === true;
      if (visibles.has(p.name) !== deberia) {
        desajustes.push(
          `${p.name}: se ve=${visibles.has(p.name)} pero ${p.requiere ?? "(todo el perfil)"}=${deberia}`,
        );
      }
    }
    expect(desajustes).toEqual([]);
  });

  it("los dos defectos que cerró esta ficha, nombrados", () => {
    // Escritos en positivo: si un cambio de matriz los reabriera, el mensaje
    // dice cuál de los dos es y no hay que deducirlo del `it.each`.
    const inspector = pestanasVisibles(MATRIZ.roles.inspector.actions).map((p) => p.name);
    expect(MATRIZ.roles.inspector.actions.roster_read).toBe(false);
    expect(inspector).not.toContain("lista");

    const admin = pestanasVisibles(MATRIZ.roles.building_admin.actions).map((p) => p.name);
    expect(MATRIZ.roles.building_admin.actions.damage_report_submit).toBe(false);
    expect(admin).not.toContain("triage");
  });

  it("y los CUATRO llegan a RUTAS y DIRECTORIO (RBAC §3, los cinco roles)", () => {
    for (const rol of TACTICOS) {
      const visibles = pestanasVisibles(MATRIZ.roles[rol].actions).map((p) => p.name);
      expect(visibles).toContain("rutas");
      expect(visibles).toContain("directorio");
    }
  });

  it("RUTAS y DIRECTORIO del táctico son EL MISMO módulo que los del ocupante", () => {
    // Una copia habría que probarla aparte —y divergiría—, así que las dos
    // pestañas nuevas reexportan. Eso además deja el dato de servidor DENTRO de
    // la ruta del ocupante, que es donde `screenStateCensus` lo vigila y donde
    // `rutas-states.test.tsx` ya prueba sus cuatro estados: la pantalla nueva
    // no estrena deuda porque no estrena código.
    for (const nombre of ["rutas", "directorio"]) {
      const fuente = readFileSync(
        resolve(process.cwd(), "src", "app", "(brigadista)", `${nombre}.tsx`),
        "utf8",
      );
      expect(fuente).toContain(`export { default } from "../(occupant)/${nombre}"`);
      // Y NADA más: en cuanto alguien le añada lógica propia, deja de ser el
      // mismo módulo y hay que probarla.
      const codigo = fuente
        .split("\n")
        .filter((l) => l.trim().length > 0 && !l.trim().startsWith("//"));
      expect(codigo).toHaveLength(1);
    }
  });

  it("el layout no vuelve a enumerar pestañas a mano", () => {
    // La regresión más probable no es cambiar la tabla: es añadir un
    // `<Tabs.Screen name="…">` suelto al lado del `.map`, que quedaría sin gate.
    const layout = readFileSync(
      resolve(process.cwd(), "src", "app", "(brigadista)", "_layout.tsx"),
      "utf8",
    );
    const declarados = [...layout.matchAll(/name="([a-z]+)"/g)].map((m) => m[1]);
    // Cualquier `name="…"` literal que coincida con una pestaña de la tabla es
    // una pestaña puesta al margen del gate.
    expect(declarados.filter((n) => PESTANAS_TACTICAS.some((p) => p.name === n))).toEqual([]);
    expect(layout).toContain("PESTANAS_TACTICAS.map");
  });
});
