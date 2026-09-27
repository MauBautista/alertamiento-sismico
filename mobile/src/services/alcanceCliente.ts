// [D-42] Roles que ven TODO su cliente y no tienen un inmueble propio.
//
// ESPEJO de `api/src/takab_api/notify/circulo.py::ROLES_DE_TODO_EL_CLIENTE`.
// La nube acepta el token push de estos roles SIN inmueble (`site_id: null`) y
// los alcanza en CUALQUIER inmueble de su tenant, con el `site_id` del incidente
// en el payload del push. Si allí cambia la lista, cambia aquí: con un rol de más
// la app registraría un token que la nube rechaza; con uno de menos, ese
// teléfono no despertaría nunca (el defecto que cierra esto: el administrador
// quedaba en 'no-site').
import type { MeResponse } from "@takab/sdk";

export const ROLES_DE_TODO_EL_CLIENTE: ReadonlySet<string> = new Set(["tenant_admin"]);

/** ¿La sesión es de un rol de todo el cliente? Exige las DOS cosas: el rol y el
 *  alcance `"*"`. Un administrador acotado a inmuebles concretos ya tiene los
 *  suyos y se comporta como cualquier táctico. */
export function esDeTodoElCliente(me: MeResponse | null | undefined): boolean {
  if (!me) {
    return false;
  }
  return ROLES_DE_TODO_EL_CLIENTE.has(me.role) && me.site_scope === "*";
}
