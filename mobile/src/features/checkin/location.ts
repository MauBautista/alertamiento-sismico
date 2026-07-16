// Captura de GPS para "necesito ayuda": mejor esfuerzo con tope de tiempo.
// CUALQUIER fallo (permiso denegado, timeout, sin señal) degrada a null y el
// check-in viaja con la zona asignada — jamás se bloquea un grito de auxilio
// esperando un fix.
import * as Location from "expo-location";

export const GPS_TIMEOUT_MS = 5_000;

export async function captureLocation(
  timeoutMs: number = GPS_TIMEOUT_MS,
): Promise<[number, number] | null> {
  try {
    let perm = await Location.getForegroundPermissionsAsync();
    if (!perm.granted) {
      perm = await Location.requestForegroundPermissionsAsync();
    }
    if (!perm.granted) {
      return null;
    }
    const fix = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs)),
    ]);
    if (!fix) {
      return null;
    }
    return [fix.coords.longitude, fix.coords.latitude];
  } catch {
    return null;
  }
}
