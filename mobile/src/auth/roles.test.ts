// [T-9.20 · D-42] Los roles de la app: siete canónicos y la ventana de alias.
// La app NO decide permisos (el servidor revalida todo); solo tiene que
// reconocer el rol que /me le manda. El servidor ya canoniza, pero si llegara
// un rol viejo, la app lo trata con EL MISMO alias que la nube.
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { ALIAS_HEREDADOS, CANONICAL_ROLES, canonizarRol, etiquetaRol } from "./roles";

describe("[D-42] roles de la app", () => {
  it("los siete canónicos son exactamente los de la matriz del servidor", () => {
    const matriz = JSON.parse(
      readFileSync(resolve(process.cwd(), "..", "shared", "fixtures", "rbac-matrix.json"), "utf8"),
    ) as { roles: Record<string, unknown> };
    expect([...CANONICAL_ROLES].sort()).toEqual(Object.keys(matriz.roles).sort());
    expect(CANONICAL_ROLES).toHaveLength(7);
  });

  it("el alias es el MISMO que el de api/src/takab_api/auth/roles.py", () => {
    // Se lee del fuente de la API: un solo mapa por lado y este test los ata.
    const fuente = readFileSync(
      resolve(process.cwd(), "..", "api", "src", "takab_api", "auth", "roles.py"),
      "utf8",
    );
    const bloque = /ALIAS_HEREDADOS[^=]*=\s*\{([^}]*)\}/.exec(fuente)?.[1] ?? "";
    const api = Object.fromEntries(
      [...bloque.matchAll(/"([a-z_]+)"\s*:\s*"([a-z_]+)"/g)].map((m) => [m[1], m[2]]),
    );
    expect(Object.keys(api).length).toBeGreaterThan(0);
    expect(ALIAS_HEREDADOS).toEqual(api);
  });

  it("un rol viejo se canoniza; un canónico o desconocido pasa tal cual", () => {
    expect(canonizarRol("soc_operator")).toBe("tenant_admin");
    expect(canonizarRol("security_guard")).toBe("brigadista");
    expect(canonizarRol("building_admin")).toBe("brigadista");
    expect(canonizarRol("inspector")).toBe("inspector");
    expect(canonizarRol("mystery")).toBe("mystery");
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
