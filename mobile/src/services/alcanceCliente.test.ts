// [D-42 · T-9.81] ¿Rol de todo el cliente? Desde la baja de los alias el rol se
// lee TAL CUAL: un `soc_operator` viejo ya no es un `tenant_admin`.
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

  it("[T-9.81] un rol retirado no se traduce a su heredero", () => {
    expect(esDeTodoElCliente(me("soc_operator", "*"))).toBe(false);
    expect(esDeTodoElCliente(me("building_admin", "*"))).toBe(false);
  });
});
