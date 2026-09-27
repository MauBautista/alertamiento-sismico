// [T-9.06] Vibración en bucle mientras ALERT_ACTIVE — hermana de `sound.ts`.
//
// Medido el 24-sep en el Pixel: con la toma de crisis puesta el teléfono SONÓ
// pero no vibró (buzz = 0). La vibración del canal `seismic_alert_v2`
// (`services/push.ts`) sólo acompaña a la NOTIFICACIÓN; con la app en primer
// plano nadie movía el motor. Una persona con el teléfono en el bolsillo y el
// volumen bajo es justo la que más necesita el zumbido.
//
// `android.permission.VIBRATE` ya está en el manifiesto (lo aporta la plantilla
// de `prebuild`; verificado el 2026-09-27 en `android/app/src/main` y en los
// manifiestos fusionados de debug y release), así que `app.json` no lo repite.
//
// Best-effort, como el sonido: un fallo del vibrador jamás rompe la pantalla de
// crisis. Y la CANCELACIÓN es tan importante como el arranque: un teléfono que
// sigue vibrando cuando la alerta ya terminó es un dato congelado pintado como
// vivo, sólo que en la mano.
import { Vibration } from "react-native";

/**
 * Patrón de Android `[espera, vibra, espera, …]` en ms, repetido en bucle. Es
 * el MISMO ritmo que el canal sísmico de notificación (500 ms encendido / 500
 * ms apagado): la push y la pantalla se sienten como el mismo aviso. En iOS el
 * sistema vibra un tramo fijo y usa estos números como pausas; el bucle sigue.
 */
export const PATRON_ALERTA: readonly number[] = [0, 500, 500];

let vibrando = false;

export function startAlertVibration(): void {
  if (vibrando) {
    return; // no reiniciar el ritmo en cada re-render
  }
  try {
    Vibration.vibrate([...PATRON_ALERTA], true);
    vibrando = true;
  } catch (err) {
    console.warn("alerta: vibración no disponible (best-effort)", err);
    vibrando = false;
  }
}

/**
 * Relanza el bucle AUNQUE este módulo crea que ya vibra.
 *
 * Android cancela la vibración de la app al apagar la pantalla con el botón,
 * sin avisar a JS: el flag `vibrando` seguía en `true` y, al volver, nadie
 * movía el motor aunque la alerta siguiera viva. `useAlertFeedback` lo llama
 * cada vez que la app vuelve a primer plano con la alerta viva.
 */
export function restartAlertVibration(): void {
  stopAlertVibration();
  startAlertVibration();
}

export function stopAlertVibration(): void {
  try {
    // Se cancela SIEMPRE, aunque este módulo crea que no vibra: no cuesta nada
    // y cubre el caso de un bucle que arrancó otra instancia de la pantalla.
    Vibration.cancel();
  } catch {
    // liberar el vibrador jamás debe reventar la transición de pantalla
  } finally {
    vibrando = false;
  }
}
