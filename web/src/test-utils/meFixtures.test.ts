import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { ROLES_RETIRADOS } from "../auth/rolesHistoricos";
import matriz from "../../../shared/fixtures/rbac-matrix.json";
import { ACTIONS_NONE, ALL_ROUTES, ME_FIXTURES, MOBILE_ONLY_ROLES, WEB_ROLES } from "./meFixtures";

/**
 * [T-5.28] Guarda de no-vacuidad de las fixtures DERIVADAS.
 *
 * La igualdad con la matriz real la ata `api/tests/auth/test_rbac_fixture_es_la_
 * matriz.py` (y `make drift`). Lo que no puede ver desde Python es que la
 * derivación de este lado produzca objetos vacíos: `Object.fromEntries` sobre una
 * lista vacía devuelve `{}` sin quejarse, y a partir de ahí **todos** los tests
 * que preguntan por un permiso lo verían en `undefined` — que es falsy, o sea el
 * mismo apagón silencioso que motivó la ficha, con otra causa.
 *
 * Por eso los números van escritos. Si mañana cambian, este archivo se pone rojo
 * y alguien mira a quién se le concedió qué — la conversación que la divergencia
 * de trece celdas se saltó durante meses.
 */
describe("[T-5.28] fixtures de /me derivadas de la matriz", () => {
  it("declara CUÁNTOS roles, acciones y rutas trae", () => {
    // [T-9.20 · D-42] 7 roles (eran 10).
    expect(Object.keys(ME_FIXTURES)).toHaveLength(7);
    // [T-9.11] 37: `movement_alert` (D-39). [T-9.31] 38: `confirm_dictamen` (D-43).
    // [T-9.40] 39: `close_incident` (D-43).
    expect(Object.keys(ACTIONS_NONE)).toHaveLength(39);
    expect(ALL_ROUTES).toHaveLength(6);
    // 5 con superficie web + 2 solo móvil (brigadista, occupant). El reparto también se deriva.
    expect(WEB_ROLES).toHaveLength(5);
    expect(MOBILE_ONLY_ROLES).toHaveLength(2);
  });

  it("ningún rol sale con el mapa de acciones vacío", () => {
    for (const [rol, me] of Object.entries(ME_FIXTURES)) {
      expect(Object.keys(me.allowed_actions), `${rol} sin acciones`).toHaveLength(39);
      for (const [accion, valor] of Object.entries(me.allowed_actions)) {
        expect(typeof valor, `${rol}.${accion} no es booleano`).toBe("boolean");
      }
    }
  });

  it("[T-6.03] `is_internal` sale del fichero: exactamente dos roles internos, ninguno de campo", () => {
    const internos = Object.entries(ME_FIXTURES)
      .filter(([, me]) => me.is_internal === true)
      .map(([rol]) => rol)
      .sort();
    expect(internos).toEqual([...matriz.internal_roles].sort());
    expect(internos).toHaveLength(2);
    for (const rol of MOBILE_ONLY_ROLES) expect(ME_FIXTURES[rol].is_internal).toBe(false);
  });

  it("`ACTIONS_NONE` es TODO en false: es la base sobre la que se pinta cada rol", () => {
    expect(Object.values(ACTIONS_NONE).every((v) => v === false)).toBe(true);
  });

  it("cada fixture dice lo que dice el fichero, celda a celda", () => {
    // No es redundante con el test de Python: aquél ata el FICHERO a la matriz;
    // éste ata las FIXTURES al fichero. Entre los dos no queda hueco.
    for (const [rol, fila] of Object.entries(matriz.roles)) {
      const me = ME_FIXTURES[rol as keyof typeof ME_FIXTURES];
      expect(me, `falta la fixture de ${rol}`).toBeDefined();
      expect(me.allowed_routes).toEqual(fila.routes);
      expect(me.allowed_actions).toEqual(fila.actions);
    }
  });

  it("los roles de campo no traen rutas web, y los de consola sí", () => {
    for (const rol of MOBILE_ONLY_ROLES) {
      expect(ME_FIXTURES[rol].allowed_routes, `${rol} con ruta web`).toHaveLength(0);
      expect(ME_FIXTURES[rol].surface).toBe("mobile");
    }
    for (const rol of WEB_ROLES) {
      expect(ME_FIXTURES[rol].allowed_routes.length, `${rol} sin rutas`).toBeGreaterThan(0);
      expect(ME_FIXTURES[rol].surface).toBe("web");
    }
  });

  it("el rol principal de la consola SÍ tiene los permisos de CCTV", () => {
    // La celda que destapó la ficha: el operador SOC no los tenía en el espejo, y
    // por eso `T-5.12` se encontró un panel vacío que la matriz real sí llena.
    // [T-9.20] Desde D-42 ese operador es `tenant_admin`.
    expect(ME_FIXTURES.tenant_admin.allowed_actions.cctv_read).toBe(true);
    expect(ME_FIXTURES.tenant_admin.allowed_actions.cctv_video).toBe(true);
  });
});

/**
 * [T-9.20 · D-42] Ningún test pide un rol que el fichero no trae.
 *
 * Al bajar de 10 a 7 roles, pedir la fixture del operador SOC da `undefined` y
 * sembrar la del administrador de inmueble siembra una sesión vacía: el componente que gatea
 * no se monta y el test sigue en verde sobre la nada — el mismo apagón silencioso
 * de T-5.28 con otra causa. El tipo lo caza en `tsc`, pero vitest no compila
 * tipos; esto lo caza al correr.
 */
const SRC = path.resolve(process.cwd(), "src");
const E2E = path.resolve(process.cwd(), "e2e");

function ficheros(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...ficheros(p));
    else if (/\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

/** Donde un rol retirado aparece A PROPÓSITO: la tabla de rótulos, su test, el
 * pintado de un usuario sin migrar y la ventana de alias del token. */
const PERMITIDOS_HEREDADOS = new Set(
  [
    "src/auth/rolesHistoricos.ts",
    "src/auth/rolesHistoricos.test.ts",
    "src/features/tenants/UsersCard.test.tsx",
  ].map((f) => path.resolve(process.cwd(), f)),
);

describe("[T-9.20] ningún test pide un rol que la matriz no trae", () => {
  const roles = new Set(Object.keys(matriz.roles));
  const todos = [...ficheros(SRC), ...ficheros(E2E)];

  it('cada `ME_FIXTURES.<rol>` / `ME_FIXTURES["rol"]` / `seedRole("rol")` existe en el fichero', () => {
    const malos: string[] = [];
    const patron =
      /ME_FIXTURES(?:\.([a-z_]+)|\[\s*["']([a-z_]+)["']\s*\])|(?:seedRole|como|devLogin\(\s*page,)\s*\(?\s*["']([a-z_]+)["']/g;
    // Este fichero se salta: su propio título cita el patrón con `"rol"`.
    const aMirar = todos.filter(
      (t) => /\.(test|spec)\.tsx?$|e2e\/helpers\.ts$/.test(t) && !t.endsWith("meFixtures.test.ts"),
    );
    for (const f of aMirar) {
      for (const m of readFileSync(f, "utf8").matchAll(patron)) {
        const rol = m[1] ?? m[2] ?? m[3];
        if (!roles.has(rol)) malos.push(`${path.relative(process.cwd(), f)}: ${rol}`);
      }
    }
    expect(malos).toEqual([]);
  });

  it("el recorrido e2e por rol entra con EXACTAMENTE los roles de la matriz", () => {
    // Su lista vive en el spec (Playwright no comparte las fixtures de vitest);
    // aquí se ata al fichero para que no se quede en 10 cuando la matriz cambie.
    const spec = readFileSync(path.join(E2E, "recorrido_por_rol.spec.ts"), "utf8");
    const bloque = spec.match(/const ROLES = \[([^\]]*)\] as const;/);
    expect(bloque, "no encuentro `const ROLES = [...]` en el recorrido").not.toBeNull();
    const enSpec = [...(bloque?.[1] ?? "").matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
    expect(enSpec).toEqual([...roles].sort());
    const soloMovil = spec.match(/const SOLO_MOVIL[^=]*= new Set\(\[([^\]]*)\]\)/);
    const movil = [...(soloMovil?.[1] ?? "").matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
    expect(movil).toEqual([...MOBILE_ONLY_ROLES].sort());
  });

  it("los ids retirados solo aparecen como dato donde se tratan COMO retirados", () => {
    const malos: string[] = [];
    for (const f of todos) {
      if (PERMITIDOS_HEREDADOS.has(f)) continue;
      const texto = readFileSync(f, "utf8");
      for (const viejo of ROLES_RETIRADOS) {
        // Como DATO (literal entre comillas o `.propiedad`), no en la prosa de un
        // comentario, que puede contar la historia con su nombre.
        const comoDato = new RegExp(`["']${viejo}["']|\\.${viejo}\\b`);
        if (comoDato.test(texto)) malos.push(`${path.relative(process.cwd(), f)}: ${viejo}`);
      }
    }
    expect(malos).toEqual([]);
  });
});
