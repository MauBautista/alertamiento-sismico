// [T-9.06] Sonido y vibración de la toma de crisis, en UN solo ciclo de vida.
//
// Antes `crisis.tsx` arrancaba el bucle de audio en su propio efecto; ahora ese
// mismo efecto arranca también la vibración, y ambos se paran juntos al salir
// de `alert_active` o al desmontar la pantalla. Juntos a propósito: dos efectos
// separados podrían dejar uno encendido sin el otro —el altavoz callado y el
// motor vibrando, o al revés— y la persona no sabría qué creer.
//
// El sonido no cambia (`sound.ts`, `D-19`): se arranca y se para exactamente
// donde antes.
//
// ⚠️ Android cancela la vibración de la app al apagar la pantalla con el botón,
// sin avisar a JS. Por eso, mientras la alerta siga viva, cada vuelta a primer
// plano (`AppState` → `active`) RELANZA el patrón: sin esto, la persona que
// apagó la pantalla y la volvió a encender veía la crisis sin zumbido.
import { useEffect } from "react";
import { AppState } from "react-native";

import { startAlertLoop, stopAlertLoop } from "./sound";
import { restartAlertVibration, startAlertVibration, stopAlertVibration } from "./vibration";

export function useAlertFeedback(alertaViva: boolean): void {
  useEffect(() => {
    if (!alertaViva) {
      return undefined;
    }
    void startAlertLoop();
    startAlertVibration();
    const sub = AppState.addEventListener("change", (estado) => {
      if (estado === "active") {
        restartAlertVibration();
      }
    });
    return () => {
      sub.remove();
      stopAlertLoop();
      stopAlertVibration();
    };
  }, [alertaViva]);
}
