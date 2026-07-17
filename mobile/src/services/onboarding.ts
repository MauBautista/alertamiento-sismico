// Estado LOCAL del onboarding (por dispositivo, en el almacén seguro):
// completado + consentimiento GPS (LFPDPPP: revocable; el check-in "necesito
// ayuda" funciona sin GPS enviando la zona — spec 0.3/1.4).
import * as SecureStore from "expo-secure-store";

export const ONBOARDING_KEY = "takab.onboarding.v1";
export const GPS_CONSENT_KEY = "takab.consent.gps.v1";

export async function isOnboardingDone(): Promise<boolean> {
  return (await SecureStore.getItemAsync(ONBOARDING_KEY)) === "done";
}

export async function markOnboardingDone(): Promise<void> {
  await SecureStore.setItemAsync(ONBOARDING_KEY, "done");
}

/** Consentimiento GPS: null = aún no decidido (se trata como NO consentido). */
export async function getGpsConsent(): Promise<boolean | null> {
  const raw = await SecureStore.getItemAsync(GPS_CONSENT_KEY);
  if (raw === "granted") {
    return true;
  }
  if (raw === "denied") {
    return false;
  }
  return null;
}

export async function setGpsConsent(granted: boolean): Promise<void> {
  await SecureStore.setItemAsync(GPS_CONSENT_KEY, granted ? "granted" : "denied");
}
