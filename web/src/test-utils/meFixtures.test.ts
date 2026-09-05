import { describe, expect, it } from "vitest";

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
    expect(Object.keys(ME_FIXTURES)).toHaveLength(10);
    expect(Object.keys(ACTIONS_NONE)).toHaveLength(36);
    expect(ALL_ROUTES).toHaveLength(6);
    // 7 con superficie web + 3 solo móvil. El reparto también se deriva.
    expect(WEB_ROLES).toHaveLength(7);
    expect(MOBILE_ONLY_ROLES).toHaveLength(3);
  });

  it("ningún rol sale con el mapa de acciones vacío", () => {
    for (const [rol, me] of Object.entries(ME_FIXTURES)) {
      expect(Object.keys(me.allowed_actions), `${rol} sin acciones`).toHaveLength(36);
      for (const [accion, valor] of Object.entries(me.allowed_actions)) {
        expect(typeof valor, `${rol}.${accion} no es booleano`).toBe("boolean");
      }
    }
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
    // La celda que destapó la ficha: `soc_operator` no los tenía en el espejo, y
    // por eso `T-5.12` se encontró un panel vacío que la matriz real sí llena.
    expect(ME_FIXTURES.soc_operator.allowed_actions.cctv_read).toBe(true);
    expect(ME_FIXTURES.soc_operator.allowed_actions.cctv_video).toBe(true);
  });
});
