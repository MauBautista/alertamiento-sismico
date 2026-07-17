// Loop del sonido de alerta mientras ALERT_ACTIVE (spec §7 · 1.2).
// El asset es el MISMO tono de sirena del gabinete (edge T-1.68); el tono
// oficial SASMEX para móvil queda pendiente de confirmación de licenciamiento
// (anotado en TASKS). Best-effort: un fallo de audio jamás rompe la pantalla
// (la push CRISIS ya sonó al llegar — esto es refuerzo en primer plano).
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";

let player: AudioPlayer | null = null;

export async function startAlertLoop(): Promise<void> {
  if (player) {
    return;
  }
  try {
    await setAudioModeAsync({ playsInSilentMode: true });
    player = createAudioPlayer(require("../../../assets/sounds/alerta_sismica.wav"));
    player.loop = true;
    player.play();
  } catch (err) {
    console.warn("alerta: audio no disponible (best-effort)", err);
    player = null;
  }
}

export function stopAlertLoop(): void {
  try {
    player?.pause();
    player?.remove();
  } catch {
    // liberar audio jamás debe reventar la transición de pantalla
  } finally {
    player = null;
  }
}
