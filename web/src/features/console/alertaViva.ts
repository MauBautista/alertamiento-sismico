// [T-7.19 · D-30] ¿La alerta de este incidente está VIVA?
//
// Viva = el servidor todavía la sostiene: `open` o `acked`. En `in_review` el
// sismo ya concluyó (`D-33`) y en `closed` el registro está cerrado; en las dos
// la animación NO EXISTE — no se apaga con un cronómetro del cliente, deja de
// existir porque el estado cambió (condición 3 de `D-30`).
//
// Vive aquí y no en `features/scene/scene.ts` a propósito: aquello decide la
// ESCENA —qué franja manda en el shell— y su censo prohíbe sacar la decisión de
// la carpeta. Esto decide si la CARCASA de una tarjeta respira, que es una
// propiedad del incidente y no de la escena. Las dos miran el mismo estado y por
// eso `alertKind` devuelve `review` exactamente cuando esto devuelve `false`;
// `AlertBanner.test.tsx` lo fija con una tabla, para que no puedan divergir.

import type { LiveIncident } from "./useLiveIncidents";

/** Los estados en los que el servidor todavía sostiene la alerta. */
export const ESTADOS_VIVOS: readonly string[] = ["open", "acked"];

export function alertaViva(incident: LiveIncident | null): boolean {
  if (incident === null) return false;
  return ESTADOS_VIVOS.includes(incident.state);
}
