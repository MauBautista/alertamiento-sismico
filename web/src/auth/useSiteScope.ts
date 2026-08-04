/**
 * [T-2.45] Alcance por sitio del operador, tal como el SERVIDOR lo aplica.
 *
 * El front **no filtra**: la autoridad es el servidor y el front solo declara. Si el
 * cliente escondiera estaciones por su cuenta, la consola mostraría un alcance que la
 * API no está imponiendo — y el día que el filtro del servidor fallara, nadie se
 * enteraría porque la pantalla ya lo estaba disimulando.
 *
 * `console_scope_enforced` viene de `/me` y dice si el servidor está filtrando **de
 * verdad**. Existe porque el cutover va en dos fases: durante la fase A un claim vacío
 * no filtra, y una insignia que dijera "ALCANCE · 0 ESTACIONES" mientras se ve todo el
 * tenant sería exactamente el dato falso que la regla de oro 7 prohíbe.
 */
import { useSessionStore } from "./session.store";

export interface SiteScopeView {
  /** El servidor está acotando las respuestas de consola. */
  enforced: boolean;
  /** Sitios del alcance. Vacío con `enforced` ⇒ ninguno (fase B). */
  siteIds: readonly string[];
  /** Rótulo de la insignia. */
  label: string;
  /** Explicación para el `title`. */
  hint: string;
}

export function siteScopeOf(
  me: { site_scope?: "*" | string[]; console_scope_enforced?: boolean } | null,
): SiteScopeView {
  const enforced = me?.console_scope_enforced === true;
  const raw = me?.site_scope;
  const siteIds = Array.isArray(raw) ? raw : [];

  if (!enforced) {
    return {
      enforced: false,
      siteIds: [],
      label: "ALCANCE · TODO EL TENANT",
      hint:
        raw === "*"
          ? "Su cuenta tiene alcance a todas las estaciones del cliente."
          : "Su rol no está acotado a estaciones concretas; ve todo el cliente.",
    };
  }
  if (siteIds.length === 0) {
    return {
      enforced: true,
      siteIds,
      label: "ALCANCE · SIN ESTACIONES ASIGNADAS",
      hint: "Su cuenta no tiene ninguna estación asignada. Solicite el alta a su administrador.",
    };
  }
  const n = siteIds.length;
  return {
    enforced: true,
    siteIds,
    label: `ALCANCE · ${n} ${n === 1 ? "ESTACIÓN" : "ESTACIONES"}`,
    hint: "El servidor está acotando esta consola a las estaciones asignadas a su cuenta.",
  };
}

export function useSiteScope(): SiteScopeView {
  return siteScopeOf(useSessionStore((s) => s.me));
}
