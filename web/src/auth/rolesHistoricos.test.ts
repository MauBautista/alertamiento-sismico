// [T-9.20 · D-42] Los rótulos de los roles, atados a la fuente de la api.
//
// D-42 bajó los roles de 10 a 7. Las filas HISTÓRICAS (bitácora, acciones,
// usuarios que todavía no pasó el script de T-9.21) siguen trayendo el id viejo,
// y la web necesita pintarlo con SU rótulo, no con el id crudo ni con el del
// heredero (eso reescribiría la historia en pantalla). Ese rótulo vive en UN
// solo fichero de la web y aquí se ata, celda a celda, a
// `api/src/takab_api/auth/roles.py`: una copia que nadie compara diverge.
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import matriz from "../../../shared/fixtures/rbac-matrix.json";
import {
  ETIQUETA_ROL,
  ROL_HISTORICO,
  ROLES_HEREDADOS,
  esRolHeredado,
  etiquetaDeRol,
} from "./rolesHistoricos";

const ROLES_PY = readFileSync(
  path.resolve(process.cwd(), "../api/src/takab_api/auth/roles.py"),
  "utf8",
);

/** Lee un `NOMBRE: dict[str, str] = { "a": "b", ... }` literal de `roles.py`. */
function dictDe(nombre: string): Record<string, string> {
  const m = ROLES_PY.match(new RegExp(`^${nombre}: dict\\[str, str\\] = \\{([^}]*)\\}`, "m"));
  if (m === null) throw new Error(`no encuentro ${nombre} en roles.py`);
  const out: Record<string, string> = {};
  for (const par of m[1].matchAll(/"([a-z_]+)":\s*"([^"]+)"/g)) out[par[1]] = par[2];
  return out;
}

describe("[T-9.20] rolesHistoricos: un solo sitio, atado a la api", () => {
  it("los rótulos canónicos son los de `roles.ETIQUETA`, y son los 7 de la matriz", () => {
    expect(ETIQUETA_ROL).toEqual(dictDe("ETIQUETA"));
    expect(Object.keys(ETIQUETA_ROL).sort()).toEqual(Object.keys(matriz.roles).sort());
  });

  it("los rótulos históricos son los de `roles.ROL_HISTORICO`", () => {
    const py = dictDe("ROL_HISTORICO");
    expect(Object.keys(py)).toHaveLength(3);
    expect(ROL_HISTORICO).toEqual(py);
    expect([...ROLES_HEREDADOS].sort()).toEqual(Object.keys(dictDe("ALIAS_HEREDADOS")).sort());
  });

  it("ningún rol histórico sigue en la matriz: por eso necesitan rótulo aparte", () => {
    for (const viejo of ROLES_HEREDADOS) {
      expect(Object.keys(matriz.roles), viejo).not.toContain(viejo);
      expect(esRolHeredado(viejo)).toBe(true);
    }
    for (const canonico of Object.keys(matriz.roles)) expect(esRolHeredado(canonico)).toBe(false);
  });

  it("etiquetaDeRol: canónico con su rótulo, viejo con el SUYO (no el del heredero), desconocido crudo", () => {
    expect(etiquetaDeRol("tenant_admin")).toBe("ADMINISTRADOR");
    expect(etiquetaDeRol("soc_operator")).toBe("OPERACIÓN SOC (ROL RETIRADO)");
    expect(etiquetaDeRol("building_admin")).toBe("ADMINISTRACIÓN DEL INMUEBLE (ROL RETIRADO)");
    expect(etiquetaDeRol("rol_que_no_existe")).toBe("rol_que_no_existe");
  });
});
