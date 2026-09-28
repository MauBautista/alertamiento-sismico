// [T-9.20 · T-9.81 · D-42] Los roles de la app: siete canónicos y la BAJA de los
// tres viejos. La app NO decide permisos (el servidor revalida todo); solo tiene
// que reconocer el rol que /me le manda. Desde T-9.81 el servidor ni emite un rol
// viejo (su token es 401 `rol_retirado` ⇒ fin de sesión, `rolRetirado.ts`), y la
// app ya no traduce ninguno: solo guarda su rótulo para las filas históricas.
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import * as roles from "./roles";
import { CANONICAL_ROLES, ROLES_RETIRADOS, etiquetaRol } from "./roles";

describe("[D-42] roles de la app", () => {
  it("los siete canónicos son exactamente los de la matriz del servidor", () => {
    const matriz = JSON.parse(
      readFileSync(resolve(process.cwd(), "..", "shared", "fixtures", "rbac-matrix.json"), "utf8"),
    ) as { roles: Record<string, unknown> };
    expect([...CANONICAL_ROLES].sort()).toEqual(Object.keys(matriz.roles).sort());
    expect(CANONICAL_ROLES).toHaveLength(7);
  });

  it("los retirados son los MISMOS que `ROLES_RETIRADOS` de api/.../auth/roles.py", () => {
    // Se lee del fuente de la API: un solo conjunto por lado y este test los ata.
    const fuente = readFileSync(
      resolve(process.cwd(), "..", "api", "src", "takab_api", "auth", "roles.py"),
      "utf8",
    );
    const bloque = /\nROLES_RETIRADOS[^=]*=\s*frozenset\(\{([^}]*)\}\)/.exec(fuente)?.[1] ?? "";
    const api = [...bloque.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
    expect(api).toHaveLength(3);
    expect([...ROLES_RETIRADOS].sort()).toEqual(api);
    for (const viejo of ROLES_RETIRADOS) expect(CANONICAL_ROLES).not.toContain(viejo);
  });

  it("[T-9.81] la app ya no traduce un rol viejo a su heredero", () => {
    const mod = roles as Record<string, unknown>;
    expect(mod.canonizarRol).toBeUndefined();
    expect(mod.ALIAS_HEREDADOS).toBeUndefined();
  });

  it("etiquetas: 7 canónicas + las históricas de filas viejas del roster", () => {
    expect(etiquetaRol("tenant_admin")).toBe("ADMINISTRADOR");
    expect(etiquetaRol("brigadista")).toBe("BRIGADISTA");
    expect(etiquetaRol("occupant")).toBe("OCUPANTE");
    expect(etiquetaRol("gov_operator")).toBe("GOBIERNO");
    // Lo histórico NO se reescribe: una fila vieja dice el rol que tenía.
    expect(etiquetaRol("security_guard")).toBe("SEGURIDAD");
    expect(etiquetaRol("building_admin")).toBe("ADMINISTRACIÓN DEL INMUEBLE");
    expect(etiquetaRol("soc_operator")).toBe("OPERACIÓN SOC");
    // Las siete, idénticas a `ETIQUETA` de la API (ninguna cae al id en mayúsculas).
    const fuente = readFileSync(
      resolve(process.cwd(), "..", "api", "src", "takab_api", "auth", "roles.py"),
      "utf8",
    );
    const bloque = /\nETIQUETA[^=]*=\s*\{([^}]*)\}/.exec(fuente)?.[1] ?? "";
    const api = Object.fromEntries(
      [...bloque.matchAll(/"([a-z_]+)"\s*:\s*"([^"]+)"/g)].map((m) => [m[1], m[2]]),
    );
    expect(Object.keys(api).sort()).toEqual([...CANONICAL_ROLES].sort());
    for (const r of CANONICAL_ROLES) {
      expect([r, etiquetaRol(r)]).toEqual([r, api[r]]);
    }
    expect(etiquetaRol("mystery")).toBe("MYSTERY");
  });
});
