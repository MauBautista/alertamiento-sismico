// Loop del sonido de alerta mientras ALERT_ACTIVE (spec §7 · 1.2).
// El asset es el MISMO tono de sirena del gabinete (edge T-1.68), y ES EL
// DEFINITIVO: `D-19` (2026-08-17) decidió tono PROPIO de TAKAB y descartó pedirle
// licencia a CIRES. No es estética, es el deslinde hecho sonido — reproducir el
// tono oficial diría por el altavoz que esto es SASMEX, justo lo contrario de lo
// que el sistema declara por escrito (precedente medido: T-2.104). Revocación:
// solo con licencia por escrito Y visto bueno legal, y aun así como tono
// ALTERNATIVO POR SITIO, nunca como sustituto silencioso.
// El mismo fichero es ahora el sonido de la NOTIFICACIÓN (`services/push.ts`),
// así que la app suena igual con la pantalla apagada y en primer plano.
// Best-effort: un fallo de audio jamás rompe la pantalla (la push CRISIS ya sonó
// al llegar — esto es refuerzo en primer plano).
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";

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
    const nuevo = createAudioPlayer(require("../../../assets/sounds/alerta_sismica.wav"));
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
