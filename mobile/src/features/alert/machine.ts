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
import type { MobileStateOut } from "@takab/sdk";

/** Fase servida por GET /sites/{id}/mobile-state (el servidor es la autoridad).
 *
 * [T-2.106] Sale del SDK generado y ya no se transcribe a mano: así, una fase
 * nueva en el contrato deja el `switch` de abajo NO EXHAUSTIVO y el typecheck
 * cae. Antes esta lista era una copia manual, y una fase que el servidor
 * empezara a servir se habría colado hasta el `deriveAlertState` sin que nada
 * chistara — el teléfono habría tenido que ADIVINAR qué hacer con ella, que es
 * exactamente lo que la spec §4.1 prohíbe. */
export type ServerPhase = MobileStateOut["phase"];

/** Estado de la app (spec §4.1). CHECKIN_SENT del diagrama ≡ reentry_blocked:
 * enviado el check-in, lo que queda es el bloqueo hasta el dictamen.
 * [T-9.04] `reentry_blocked` también es la fase homónima del servidor (el
 * bloqueo que persiste con el incidente ya CERRADO, `data.incident = null`);
 * `crisis.tsx` y `checkin.tsx` la distinguen por `data.phase` y la mandan a
 * INICIO, donde se pinta su cartel. */
export type AlertState =
  | "idle"
  | "alert_active"
  | "checkin_pending"
  | "reentry_blocked"
  | "reentry_approved"
  | "building_alarm"
  | "building_movement";

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
    // [T-2.106] ALARMA DEL INMUEBLE: la sirena la ordenó una persona, no un
    // sismo. Pasa TAL CUAL porque el check-in de vida, el bloqueo de reingreso
    // y el dictamen son consecuencias de un sismo y aquí no hay ninguno; la
    // precedencia (lo sísmico gana) ya la resolvió el servidor, que es quien
    // decide las fases (§4.1) — aquí no se recalcula nada.
    case "building_alarm":
      return "building_alarm";
    // [T-9.11 · D-39] MOVIMIENTO EN EL INMUEBLE: el sensor PROPIO detectó
    // movimiento y la nube lo sirve SOLO a los roles con `movement_alert`. No es
    // una alerta sísmica oficial (una estación sola no ordena evacuar), así que
    // el check-in de vida no aplica: pasa TAL CUAL. Quién la ve lo decide el
    // servidor; el `CrisisWatcher` además no la enruta nunca para el ocupante.
    case "building_movement":
      return "building_movement";
    // [T-9.04] Bloqueo PERSISTENTE: el incidente ya cerró (desde `D-33` firmar
    // lo cierra en tres segundos) y lo que sobrevive es el VEREDICTO —un NO
    // HABITAR firmado, o un dictamen que no llega—. Se reutiliza el estado de la
    // app: el reingreso está bloqueado, y el check-in propio ya no lo cambia
    // porque no queda incidente abierto al que reportarse. El PORQUÉ viaja en
    // `reentry.reason` y lo pinta INICIO (`features/reentry/avisoReingreso`);
    // no es toma de pantalla: el `CrisisWatcher` no enruta con este estado.
    case "reentry_blocked":
      return "reentry_blocked";
    default: {
      // [T-9.06] Una APK vieja frente a un servidor más nuevo. Sin `default`, una
      // fase desconocida devolvía `undefined` y cada pantalla que compara
      // `state === …` se quedaba muda sin decir por qué. Cae a `idle` —jamás a
      // crisis ni a reingreso autorizado: el teléfono no adivina (§4.1)— y lo
      // deja escrito en el registro.
      //
      // La asignación a `never` conserva la guarda de T-2.106: una fase nueva
      // en el SDK generado sigue tumbando el typecheck hasta que alguien le dé
      // su caso. El `default` protege al teléfono ya instalado, no al código.
      const desconocida: never = phase;
      // Una vez por fase: esta función corre en cada render y cada sondeo, y un
      // aviso repetido cada 5 s entierra el registro sin decir nada nuevo.
      const nombre = String(desconocida);
      if (!fasesAvisadas.has(nombre)) {
        fasesAvisadas.add(nombre);
        console.warn(`alerta: fase del servidor desconocida para esta versión: ${nombre}`);
      }
      return "idle";
    }
  }
}

const fasesAvisadas = new Set<string>();

/** [T-9.06] Las fases que esta versión CONOCE. `Record` exhaustivo sobre el tipo
 * del SDK: una fase nueva tumba el typecheck hasta que se declare aquí. */
const FASES_CONOCIDAS: Record<ServerPhase, true> = {
  idle: true,
  alert_active: true,
  shaking_concluded: true,
  reentry_approved: true,
  building_alarm: true,
  reentry_blocked: true,
  building_movement: true,
};

/** ¿La app sabe qué significa esta fase? Si no, `deriveAlertState` cae a `idle`
 * para no quedarse muda, pero INICIO no puede leer ese `idle` como «SEGURO»:
 * el servidor dijo algo que esta versión no entiende (`HomeView`). */
export function esFaseConocida(phase: string): phase is ServerPhase {
  return Object.prototype.hasOwnProperty.call(FASES_CONOCIDAS, phase);
}

/** [T-9.04] Fases que NO son un episodio en curso y se sondean al ritmo de
 * reposo. El bloqueo persistente dura DÍAS (un NO HABITAR firmado no caduca):
 * sondearlo cada 5 s mantendría despierto cada teléfono del edificio sin
 * ganar nada — un sismo nuevo llega por la push, que invalida la consulta al
 * instante. Una fase DESCONOCIDA no está aquí a propósito: ante la duda se
 * pregunta más a menudo, no menos. */
export function faseEnReposo(phase: ServerPhase): boolean {
  return phase === "idle" || phase === "reentry_blocked";
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
