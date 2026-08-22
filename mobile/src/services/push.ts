// Cliente de push del dispositivo (T-2.04 · spec §6).
// La push es DESPERTADOR best-effort: la protección de vida es la sirena del
// edge (R5). Aquí: canales Android (los tres, con bypass de No Molestar en los
// dos que despiertan), permisos (con Critical Alerts iOS cuando el entitlement
// llegue — GATE-STORE) y registro del token NATIVO (FCM/APNs) en
// /me/push-tokens; el backend lo mapea a un endpoint de SNS.
import { registerPushTokenMePushTokensPost } from "@takab/sdk";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { type PermissionSnapshot } from "./alertability";

/** Fichero empaquetado por el plugin `expo-notifications` de `app.json`. Es el
 * MISMO tono que sale por el altavoz del gabinete (`edge/takab_edge/audio/assets/
 * siren.wav`, sha256 idéntico), y es propio de TAKAB — nunca el oficial del
 * SASMEX. La razón está escrita en `D-19` y es un deslinde, no una estética:
 * reproducir el tono oficial diría POR EL ALTAVOZ que esto es SASMEX, que es lo
 * contrario de lo que el sistema declara por escrito. Precedente medido: T-2.104.
 *
 * Revocación: solo con licencia de CIRES POR ESCRITO y visto bueno legal, y aun
 * así como tono ALTERNATIVO POR SITIO — jamás como sustituto silencioso. Cambiar
 * el sonido de una alarma que la gente ya aprendió es un cambio de producto. */
export const SEISMIC_SOUND = "alerta_sismica.wav";

/** ⚠️ El sufijo `_v2` NO es cosmético y no se puede quitar.
 *
 * La importancia y el sonido de un canal Android son **inmutables tras crearlo**:
 * volver a llamar a `setNotificationChannelAsync` con un sonido nuevo no cambia
 * nada en un teléfono que ya tenga el canal — Android ignora el cambio en silencio.
 * El canal v1 nació con `sound: "default"` (mientras `D-19` estaba sin decidir),
 * así que estrenar el tono propio EXIGE id nuevo: sin él, el tono funcionaría en
 * una instalación limpia y no en el Pixel con el que se acredita `GATE-HW`, que es
 * justo el teléfono donde se comprobaría.
 *
 * Si algún día cambia otra vez la importancia o el sonido, toca `_v3` y mover el
 * legacy — no editar en sitio. */
export const SEISMIC_CHANNEL_ID = "seismic_alert_v2";
const SEISMIC_CHANNEL_ID_LEGACY = "seismic_alert";

/** [T-2.147.a · D-05] Activación manual del inmueble (quórum de pánico).
 *
 * Este canal FALTABA: `notify/push.py` entregaba la clase PANIC por él desde el
 * 2026-08-16 y la app no lo creaba. FCM, ante un canal inexistente, cae al canal
 * por defecto —importancia DEFAULT, SIN bypass de No Molestar—, así que el push
 * que tiene que sacar a una brigada de la cama a las 3 a.m. llegaba como una
 * notificación cualquiera. `android.priority: "high"` no lo salvaba: en Android 8+
 * el heads-up y el DND los gobierna la importancia del CANAL. */
export const PANIC_CHANNEL_ID = "building_alarm";
export const OPS_CHANNEL_ID = "ops";

/** Canales Android (idempotente). */
export async function configureAndroidChannels(): Promise<void> {
  if (Platform.OS !== "android") {
    return;
  }
  await Notifications.setNotificationChannelAsync(SEISMIC_CHANNEL_ID, {
    name: "Alerta sísmica",
    importance: Notifications.AndroidImportance.MAX,
    bypassDnd: true,
    sound: SEISMIC_SOUND,
    vibrationPattern: [0, 500, 500, 500, 500, 500],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  // Despierta como una crisis (MAX + bypass de DND) y NO suena como una: sonido
  // del sistema y vibración propia. Vestir de sismo una activación manual es el
  // defecto de T-2.104, y aquí sería peor porque el tono propio ya está a mano.
  await Notifications.setNotificationChannelAsync(PANIC_CHANNEL_ID, {
    name: "Alarma del inmueble",
    importance: Notifications.AndroidImportance.MAX,
    bypassDnd: true,
    sound: "default",
    vibrationPattern: [0, 200, 200, 200, 200, 200, 200, 200],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  await Notifications.setNotificationChannelAsync(OPS_CHANNEL_ID, {
    name: "Operación TAKAB",
    importance: Notifications.AndroidImportance.DEFAULT,
  });
  // El v1 se retira DESPUÉS de crear el v2: si el borrado fuera primero y la
  // creación fallara, el teléfono se quedaría sin canal sísmico ninguno.
  // Best-effort — en una instalación limpia no existe y borrarlo no es un error.
  try {
    await Notifications.deleteNotificationChannelAsync(SEISMIC_CHANNEL_ID_LEGACY);
  } catch {
    // un canal que no existe no hay que borrarlo; jamás bloquea el registro
  }
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
  // no dependen del inmueble, y dejar a un teléfono sin el canal sísmico (bypass
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
