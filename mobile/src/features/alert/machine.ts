// Máquina de estados de crisis (spec §4.1) — PURA y determinista.
//
// La FASE la sirve el backend (`mobile-state.phase`, derivada de incidente +
// transiciones reales de tier + dictamen firmado). El ÚNICO insumo local es si
// este dispositivo ya envió SU check-in (conmuta check-in ↔ bloqueo). El
// teléfono JAMÁS decide que el movimiento terminó ni que el reingreso procede.
//
// Modos de prueba del gabinete (T-1.67/T-1.69): el edge en prueba NO publica a
// la nube ⇒ no hay incidente ⇒ phase=idle. La garantía es server-side y esta
// función no tiene NINGÚN otro insumo — no existe camino local para "salir de
// IDLE por una prueba" (los tests del edge fijan la supresión; aquí se fija
// que la firma de la función no admite más entradas).

/** Fase servida por GET /sites/{id}/mobile-state (el servidor es la autoridad). */
export type ServerPhase = "idle" | "alert_active" | "shaking_concluded" | "reentry_approved";

/** Estado de la app (spec §4.1). CHECKIN_SENT del diagrama ≡ reentry_blocked:
 * enviado el check-in, lo que queda es el bloqueo hasta el dictamen. */
export type AlertState =
  | "idle"
  | "alert_active"
  | "checkin_pending"
  | "reentry_blocked"
  | "reentry_approved";

/** §2.1-A: el WR-1 entrega un BOOLEANO — no hay dato de magnitud/ETA que
 * mostrar. Si una fuente futura transporta ETA POR DATO, este flag activa el
 * campo sin tocar el layout. Jamás se pone en true sin esa fuente. */
export const ALERT_SOURCE_CARRIES_ETA = false as const;

export function deriveAlertState(phase: ServerPhase, hasOwnCheckin: boolean): AlertState {
  switch (phase) {
    case "idle":
      return "idle";
    case "alert_active":
      return "alert_active";
    case "shaking_concluded":
      // Movimiento terminado (dato del edge vía backend): toca check-in; con el
      // check-in PROPIO enviado, lo que sigue es el bloqueo de reingreso.
      return hasOwnCheckin ? "reentry_blocked" : "checkin_pending";
    case "reentry_approved":
      return "reentry_approved";
  }
}

/** Segundos transcurridos desde la apertura (T+ ascendente, dato real y
 * verificable). Un sesgo de reloj del dispositivo jamás produce negativos. */
export function elapsedSeconds(openedAtIso: string, nowMs: number): number {
  const opened = Date.parse(openedAtIso);
  if (Number.isNaN(opened)) {
    return 0;
  }
  return Math.max(0, Math.floor((nowMs - opened) / 1000));
}

/** ``T+04s`` bajo el minuto; ``T+1m32s`` después — SIEMPRE ascendente (el
 * cronómetro regresivo está PROHIBIDO, §2.1-A). */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) {
    return `T+${String(seconds).padStart(2, "0")}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `T+${minutes}m${String(rest).padStart(2, "0")}s`;
}
