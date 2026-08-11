// Persistencia de sesión en el almacén seguro del sistema (spec móvil §3/§8):
// Keychain (iOS) / Keystore (Android) vía expo-secure-store. Nada de esto
// toca AsyncStorage. La sesión del occupant es de larga vida — la app debe
// poder alertar sin pedir login en plena crisis.
import * as SecureStore from "expo-secure-store";

import type { ProfileGroup } from "./profileGate";

export const SESSION_KEY = "takab.session.v1";

/** [T-2.114] Inmueble vigilado por este dispositivo. La clave vive AQUÍ y no en
 * `services/mySite.ts` por una razón mecánica: `clearSession()` tiene que poder
 * soltarla al cerrar sesión, y `mySite` importa el store de sesión — tomar la
 * constante desde allá cerraría un ciclo de módulos.
 *
 * `.v2` porque el formato cambió: ya no es el id suelto, sino `{sub, site_id}`.
 * El valor `.v1` NO se lee: no dice de quién es, y ésa es justo la propiedad que
 * faltaba. Al actualizar la app, el ocupante recupera su edificio de `/me` —sin
 * código nuevo, que era la razón por la que este dato no se podía tirar—. */
export const WATCHED_SITE_KEY = "takab.watched_site.v2";

/** Clave del formato viejo. Solo existe para BORRARLA: si se quedara en el
 * Keychain sería un edificio sin dueño esperando a que alguien vuelva a leerlo. */
const WATCHED_SITE_KEY_V1 = "takab.watched_site.v1";

export interface StoredSession {
  profile: ProfileGroup;
  idToken: string;
  refreshToken?: string;
  /** epoch ms del intercambio de código (diagnóstico; la expiración real la
   * dictan los tokens). */
  issuedAt: number;
}

function isStoredSession(value: unknown): value is StoredSession {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const s = value as Record<string, unknown>;
  return (
    (s.profile === "occupant" || s.profile === "tactical") &&
    typeof s.idToken === "string" &&
    typeof s.issuedAt === "number" &&
    (s.refreshToken === undefined || typeof s.refreshToken === "string")
  );
}

export async function saveSession(session: StoredSession): Promise<void> {
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session));
}

/** Carga la sesión; un payload corrupto se purga y devuelve null (el arranque
 * jamás debe reventar por una sesión vieja). */
export async function loadSession(): Promise<StoredSession | null> {
  const raw = await SecureStore.getItemAsync(SESSION_KEY);
  if (raw == null) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isStoredSession(parsed)) {
      return parsed;
    }
  } catch {
    // corrupto: cae al purge de abajo
  }
  await SecureStore.deleteItemAsync(SESSION_KEY);
  return null;
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
  // [T-2.114] El inmueble vigilado se suelta CON la sesión. Antes no se
  // borraba a propósito —el edificio del occupant no viaja en el claim y
  // borrarlo lo dejaba tirado hasta conseguir otro código de alta—, y por eso
  // el siguiente usuario del mismo teléfono lo heredaba. Ya no aplica: `/me`
  // devuelve `enrolled_sites` y el mismo ocupante lo recupera al volver.
  await SecureStore.deleteItemAsync(WATCHED_SITE_KEY);
  await SecureStore.deleteItemAsync(WATCHED_SITE_KEY_V1);
}
