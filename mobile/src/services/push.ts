// Cliente de push del dispositivo (T-2.04 · spec §6).
// La push es DESPERTADOR best-effort: la protección de vida es la sirena del
// edge (R5). Aquí: canales Android (seismic_alert con bypass de No Molestar),
// permisos (con Critical Alerts iOS cuando el entitlement llegue — GATE-STORE)
// y registro del token NATIVO (FCM/APNs) en /me/push-tokens; el backend lo
// mapea a un endpoint de SNS.
import { registerPushTokenMePushTokensPost } from "@takab/sdk";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { type PermissionSnapshot } from "./alertability";

export const SEISMIC_CHANNEL_ID = "seismic_alert";
export const OPS_CHANNEL_ID = "ops";

/** Canales Android (idempotente). El sonido oficial empaquetado llega con las
 * pantallas de crisis (T-2.05); mientras, el del sistema — sin fingir. */
export async function configureAndroidChannels(): Promise<void> {
  if (Platform.OS !== "android") {
    return;
  }
  await Notifications.setNotificationChannelAsync(SEISMIC_CHANNEL_ID, {
    name: "Alerta sísmica",
    importance: Notifications.AndroidImportance.MAX,
    bypassDnd: true,
    sound: "default",
    vibrationPattern: [0, 500, 500, 500, 500, 500],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  await Notifications.setNotificationChannelAsync(OPS_CHANNEL_ID, {
    name: "Operación TAKAB",
    importance: Notifications.AndroidImportance.DEFAULT,
  });
}

function toSnapshot(p: Notifications.NotificationPermissionsStatus): PermissionSnapshot {
  return {
    granted: p.status === "granted",
    canAskAgain: p.canAskAgain,
    iosCriticalAllowed: Platform.OS === "ios" ? (p.ios?.allowsCriticalAlerts ?? false) : null,
  };
}

export async function getPermissionSnapshot(): Promise<PermissionSnapshot> {
  return toSnapshot(await Notifications.getPermissionsAsync());
}

/** Pide permisos (incluye Critical Alerts en iOS: sin entitlement, el sistema
 * lo ignora en silencio — la degradación la declara deriveAlertability). */
export async function requestPermissions(): Promise<PermissionSnapshot> {
  return toSnapshot(
    await Notifications.requestPermissionsAsync({
      ios: {
        allowAlert: true,
        allowSound: true,
        allowBadge: true,
        allowCriticalAlerts: true,
      },
    }),
  );
}

export type PushRegistration = "registered" | "no-permission" | "no-site" | "error";

/** Registra el token NATIVO del dispositivo en el backend (upsert idempotente).
 * Best-effort deliberado: un fallo aquí jamás bloquea el uso de la app.
 *
 * [T-2.109] `siteId` es OBLIGATORIO —y admite `null` explícito— a propósito.
 * Antes era opcional y el único punto de llamada de la app (`app/_layout.tsx`)
 * lo omitía, así que el registro mandaba `site_id: null` SIEMPRE. La nube elige
 * a quién despierta con `WHERE site_id = <uuid> AND tenant_id = ... AND
 * revoked_at IS NULL`, y NULL no iguala a un UUID: ningún dispositivo entraba
 * jamás en la lista de destinatarios. Con el parámetro obligatorio, volver a
 * omitirlo no compila.
 *
 * No es una regresión viva: `push_tokens` está VACÍA en producción porque el
 * canal real sigue detrás de GATE-STORE (T-2.97). Es una MINA — el día que
 * APNs/FCM aterricen, la acreditación saldría verde sin que sonara un teléfono.
 */
export async function registerDeviceForPush(siteId: string | null): Promise<PushRegistration> {
  const snapshot = await getPermissionSnapshot();
  if (!snapshot.granted) {
    return "no-permission";
  }
  // Los canales de Android se crean SIEMPRE que haya permiso: son idempotentes,
  // no dependen del inmueble, y dejar a un teléfono sin `seismic_alert` (bypass
  // de No Molestar) por no haberse enrolado todavía sería un daño gratuito.
  try {
    await configureAndroidChannels();
  } catch (err) {
    console.warn("push: no se pudieron configurar los canales de Android", err);
  }
  if (!siteId) {
    // Sin inmueble no hay a quién pertenecer: un token con `site_id: null` no es
    // destinatario de nada. Registrarlo dejaría una fila que PARECE un teléfono
    // cubierto y no lo es (regla de oro 7). Se declara y se reintenta solo, en
    // cuanto el sitio vigilado exista — el enrolamiento lo fija (T-2.103) y el
    // efecto de `_layout` vuelve a llamar aquí.
    return "no-site";
  }
  try {
    const device = await Notifications.getDevicePushTokenAsync();
    const token = typeof device.data === "string" ? device.data : JSON.stringify(device.data);
    const res = await registerPushTokenMePushTokensPost({
      body: {
        platform: Platform.OS === "ios" ? "ios" : "android",
        token,
        site_id: siteId,
      },
    });
    if (res.error) {
      console.warn("push: el backend rechazó el registro del token", res.error);
      return "error";
    }
    return "registered";
  } catch (err) {
    console.warn("push: registro fallido (best-effort, se reintenta al reabrir)", err);
    return "error";
  }
}
