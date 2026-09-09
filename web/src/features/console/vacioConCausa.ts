/**
 * [T-6.06] EL VACÍO DICE POR QUÉ ESTÁ VACÍO.
 *
 * Cuatro estados vacíos de la consola atribuían al TENANT lo que, en cuanto
 * `console_scope_enforced` esté puesto, será el ALCANCE de la cuenta: un
 * operador con cero estaciones asignadas leería «SIN SITIOS VISIBLES EN EL
 * TENANT» sobre un cliente que tiene veintiuna. Eso no es un matiz de redacción:
 * manda al operador a preguntar por qué su cliente está vacío en vez de a pedir
 * el alta de sus estaciones, que es lo que le falta.
 *
 * La frase se DERIVA del mismo `useSiteScope()` del que sale la insignia de la
 * barra superior — la única fuente que dice si el servidor está acotando de
 * verdad—, así que no puede desincronizarse de ella. Tres desenlaces:
 *
 *   · sin alcance impuesto ⇒ «… EN EL TENANT» (hoy es cierto: se ve todo);
 *   · con alcance y N estaciones ⇒ «… EN SU ALCANCE (N estaciones)»;
 *   · con alcance y NINGUNA ⇒ deja de hablar de lo que no hay y dice lo que
 *     pasa: la cuenta no tiene estaciones asignadas, y a quién pedírselas.
 *
 * Va **antes** de `T-2.89` (el apply del alcance) a propósito: después sería un
 * arreglo con la consola ya mintiendo en producción.
 */
import type { SiteScopeView } from "../../auth/useSiteScope";

/** Qué se pide en el alta cuando la cuenta no tiene ninguna estación. */
const SIN_ASIGNACION =
  "SU CUENTA NO TIENE ESTACIONES ASIGNADAS · SOLICITE EL ALTA A SU ADMINISTRADOR";

/**
 * `base` es la ausencia SIN ámbito: «SIN SITIOS VISIBLES», «SIN GABINETES
 * REGISTRADOS». El ámbito lo pone esta función, nunca el componente — que es lo
 * que permitió que tres pantallas dijeran «tenant» y una «alcance».
 */
export function vacioConCausa(base: string, scope: SiteScopeView): string {
  if (!scope.enforced) {
    return `${base} EN EL TENANT`;
  }
  if (scope.siteIds.length === 0) {
    return SIN_ASIGNACION;
  }
  const n = scope.siteIds.length;
  return `${base} EN SU ALCANCE (${n} ${n === 1 ? "ESTACIÓN" : "ESTACIONES"})`;
}
