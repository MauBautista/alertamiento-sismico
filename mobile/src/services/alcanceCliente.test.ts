// [D-42 · T-9.20] ¿Rol de todo el cliente? El rol se lee con el MISMO alias que
// la nube (`auth/roles.ts`): un `soc_operator` viejo es un `tenant_admin`.
import type { MeResponse } from "@takab/sdk";

import { esDeTodoElCliente } from "./alcanceCliente";

const me = (role: string, site_scope: string): MeResponse =>
  ({ role, site_scope }) as unknown as MeResponse;

describe("esDeTodoElCliente", () => {
  it("exige rol de todo el cliente Y alcance '*'", () => {
    expect(esDeTodoElCliente(me("tenant_admin", "*"))).toBe(true);
    expect(esDeTodoElCliente(me("tenant_admin", "site-1"))).toBe(false);
    expect(esDeTodoElCliente(me("brigadista", "*"))).toBe(false);
    expect(esDeTodoElCliente(null)).toBe(false);
  });

  it("un rol viejo se canoniza como en la nube", () => {
    expect(esDeTodoElCliente(me("soc_operator", "*"))).toBe(true);
    expect(esDeTodoElCliente(me("building_admin", "*"))).toBe(false);
  });
});
