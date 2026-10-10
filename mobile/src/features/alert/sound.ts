// Loop del sonido de alerta mientras ALERT_ACTIVE (spec §7 · 1.2).
// [T-9.70 · D-50] `alert_active` sólo se sirve para un incidente que AUTORIZA evacuar
// (SASMEX o cuórum), y desde el 2026-10-01 eso suena con el sonido OFICIAL del
// SASMEX (revoca en parte `D-19`, que lo había descartado como deslinde). En Android
// suena el MISMO recurso que el canal de la notificación (`raw/alerta_oficial`, que
// el plugin de prebuild llena con el oficial o con el propio), así que la app suena
// igual con la pantalla apagada y en primer plano. Sin ese recurso, y en iOS, el
// tono propio empaquetado: el oficial no está en el repositorio y no se `require`.
// Best-effort: un fallo de audio jamás rompe la pantalla (la push CRISIS ya sonó
// al llegar — esto es refuerzo en primer plano).
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { Platform } from "react-native";

import { RECURSO_OFICIAL, tonoOficialDeLaCompilacion } from "@/services/tonoOficial";

/** Lo que suena en bucle: el recurso de la compilación en Android, si lo hay. */
function fuenteDelBucle(): number | { uri: string } {
  if (Platform.OS === "android" && tonoOficialDeLaCompilacion() !== null) {
    return { uri: RECURSO_OFICIAL.replace(/\.wav$/, "") };
  }
  return require("../../../assets/sounds/alerta_sismica.wav");
}

//
// [T-9.06] ⚠️ CARRERA arranque/parada. `startAlertLoop` espera a
// `setAudioModeAsync` antes de crear el reproductor; si la alerta termina en ese
// hueco, `stopAlertLoop` encontraba `player = null`, no paraba nada, y el
// arranque creaba DESPUÉS un reproductor en bucle que ya nadie iba a parar: la
// sirena del teléfono sonando con la alerta terminada. Cada arranque toma una
// GENERACIÓN; parar la invalida, y un arranque que vuelve del `await` con una
// generación vieja no crea nada.
let player: AudioPlayer | null = null;
let generacion = 0;
let arrancando = false;

export async function startAlertLoop(): Promise<void> {
  if (player || arrancando) {
    return;
  }
  generacion += 1;
  const mia = generacion;
  arrancando = true;
  try {
    await setAudioModeAsync({ playsInSilentMode: true });
    if (mia !== generacion) {
      return; // la alerta terminó mientras se configuraba el audio
    }
    const nuevo = createAudioPlayer(fuenteDelBucle());
    nuevo.loop = true;
    nuevo.play();
    player = nuevo;
  } catch (err) {
    console.warn("alerta: audio no disponible (best-effort)", err);
    player = null;
  } finally {
    if (mia === generacion) {
      arrancando = false;
    }
  }
}

export function stopAlertLoop(): void {
  generacion += 1;
  arrancando = false;
  try {
    player?.pause();
    player?.remove();
  } catch {
    // liberar audio jamás debe reventar la transición de pantalla
  } finally {
    player = null;
  }
}
