// Llave del operador respaldada por hardware (T-2.09 · spec §2.1-B):
// react-native-biometrics genera el par en Keystore/Secure Enclave (la
// privada JAMÁS sale del hardware) y cada firma exige el prompt biométrico.
// La pública (RSA-2048, DER base64) se registra en /me/device-keys como PEM;
// el key_id del servidor se guarda en el almacén seguro.
//
// GATE-HW: la validación física (attestation real en dispositivo) es parte
// del gate de hardware de T-2.09/T-2.14 — aquí queda el flujo completo.
import { registerDeviceKeyMeDeviceKeysPost } from "@takab/sdk";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import ReactNativeBiometrics from "react-native-biometrics";

export const DEVICE_KEY_ID_STORE = "takab.devicekey.id.v1";

/** DER (base64) → PEM SubjectPublicKeyInfo (líneas de 64). */
export function derToPem(base64Der: string): string {
  const clean = base64Der.replace(/\s+/g, "");
  const lines = clean.match(/.{1,64}/g) ?? [];
  return `-----BEGIN PUBLIC KEY-----\n${lines.join("\n")}\n-----END PUBLIC KEY-----`;
}

function rnBiometrics(): ReactNativeBiometrics {
  return new ReactNativeBiometrics();
}

export type DeviceKeyResult =
  | { ok: true; keyId: string }
  | { ok: false; reason: string };

/** Garantiza llave de hardware REGISTRADA: reutiliza la vigente o genera y
 *  registra una nueva. Cualquier fallo se declara (jamás firma degradada). */
export async function ensureDeviceKey(): Promise<DeviceKeyResult> {
  const bio = rnBiometrics();
  const stored = await SecureStore.getItemAsync(DEVICE_KEY_ID_STORE);
  if (stored) {
    const { keysExist } = await bio.biometricKeysExist();
    if (keysExist) {
      return { ok: true, keyId: stored };
    }
    // La llave murió en el hardware (reinstalación/borrado biométrico): el
    // key_id guardado ya no firma nada — se regenera y re-registra.
    await SecureStore.deleteItemAsync(DEVICE_KEY_ID_STORE);
  }
  const { available } = await bio.isSensorAvailable();
  if (!available) {
    return { ok: false, reason: "Este dispositivo no tiene biometría disponible." };
  }
  const { publicKey } = await bio.createKeys();
  const res = await registerDeviceKeyMeDeviceKeysPost({
    body: {
      platform: Platform.OS === "ios" ? "ios" : "android",
      public_key: derToPem(publicKey),
    },
  });
  if (!res.data) {
    return { ok: false, reason: "No se pudo registrar la llave en el servidor." };
  }
  const keyId = String(res.data.key_id);
  await SecureStore.setItemAsync(DEVICE_KEY_ID_STORE, keyId);
  return { ok: true, keyId };
}

export type SignResult = { ok: true; signature: string } | { ok: false; reason: string };

/** Firma el string canónico con la llave de hardware (prompt biométrico). */
export async function signIntent(canonical: string, promptMessage: string): Promise<SignResult> {
  const { success, signature, error } = await rnBiometrics().createSignature({
    promptMessage,
    payload: canonical,
  });
  if (!success || !signature) {
    return { ok: false, reason: error ?? "Firma cancelada." };
  }
  return { ok: true, signature };
}
