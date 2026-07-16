// Persistencia de sesión en el almacén seguro del sistema (spec móvil §3/§8):
// Keychain (iOS) / Keystore (Android) vía expo-secure-store. Nada de esto
// toca AsyncStorage. La sesión del occupant es de larga vida — la app debe
// poder alertar sin pedir login en plena crisis.
import * as SecureStore from "expo-secure-store";

import type { ProfileGroup } from "./profileGate";

export const SESSION_KEY = "takab.session.v1";

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
}
