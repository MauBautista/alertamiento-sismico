// [T-6.22 · U-30] Qué pestañas ve el perfil TÁCTICO, derivado de `allowed_actions`.
//
// Hasta aquí el layout enumeraba cinco pestañas iguales para los cuatro roles
// tácticos, y el reparto no era el de `RBAC-TAKAB.md §3`. El servidor revalida
// cada acción, así que no era una fuga; era una promesa que la pantalla no
// podía cumplir — el inspector abría el pase de lista para encontrarse un 403.
//
// La tabla es el único sitio donde se decide, y CADA entrada declara de qué
// depende: `requiere: null` no es «sin gate», es «de todo el perfil táctico, y
// alguien lo escribió». Sin esa obligación, la pestaña siguiente entra sin gate
// y nadie lo nota, que es justo como llegaron aquí LISTA y TRIAGE.

/** Nombre de icono de `@expo/vector-icons/Feather`. */
export type IconoPestana = "activity" | "clipboard" | "users" | "map" | "phone" | "refresh-cw" | "user";

export interface PestanaTactica {
  /** Fichero de ruta dentro de `app/(brigadista)/`. */
  name: string;
  /** Rótulo de la barra. */
  title: string;
  icon: IconoPestana;
  /**
   * Acción de `allowed_actions` que la habilita, o `null` si es de todo el
   * perfil táctico. Las tres de `null` lo son por razones distintas y conviene
   * no confundirlas:
   *
   * · RUTAS y DIRECTORIO — `RBAC-TAKAB.md §3` las concede a los CINCO roles
   *   móviles, ocupante incluido. No hay acción que las gatee porque no hay
   *   nada que autorizar: son lectura del inmueble donde uno está.
   * · SYNC — es la cola de escritura de ESTA app, no un permiso del servidor.
   * · CUENTA — sin ella no hay forma de cerrar sesión ni de reintentar.
   */
  requiere: string | null;
}

/**
 * Orden ESTABLE de la barra. No se reordena según lo que el rol pueda hacer: el
 * táctico aprende dónde está cada cosa y en una crisis pulsa sin mirar. Lo que
 * no le corresponde se cae, y el resto no se mueve.
 */
export const PESTANAS_TACTICAS: readonly PestanaTactica[] = [
  { name: "panel", title: "PANEL", icon: "activity", requiere: "panel_read" },
  { name: "triage", title: "TRIAGE", icon: "clipboard", requiere: "damage_report_submit" },
  { name: "lista", title: "LISTA", icon: "users", requiere: "roster_read" },
  { name: "rutas", title: "RUTAS", icon: "map", requiere: null },
  { name: "directorio", title: "DIRECTORIO", icon: "phone", requiere: null },
  { name: "sync", title: "SYNC", icon: "refresh-cw", requiere: null },
  { name: "cuenta", title: "CUENTA", icon: "user", requiere: null },
];

/**
 * Las pestañas que este operador puede usar. DEFAULT-DENY: sin `allowed_actions`
 * —sesión a medio cargar— sólo quedan las que no dependen de ninguna. Lo
 * contrario es la pestaña que aparece y desaparece cuando llega `/me`, y para
 * entonces el táctico ya pulsó.
 */
export function pestanasVisibles(
  actions: Record<string, boolean> | null | undefined,
): PestanaTactica[] {
  return PESTANAS_TACTICAS.filter(
    (p) => p.requiere === null || actions?.[p.requiere] === true,
  );
}
