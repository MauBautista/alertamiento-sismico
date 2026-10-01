// Cliente de push del dispositivo (T-2.04 · spec §6).
// La push es DESPERTADOR best-effort: la protección de vida es la sirena del
// edge (R5). Aquí: canales Android (los tres, con bypass de No Molestar en los
// dos que despiertan), permisos (con Critical Alerts iOS cuando el entitlement
// llegue — GATE-STORE) y registro del token NATIVO (FCM/APNs) en
// /me/push-tokens; el backend lo mapea a un endpoint de SNS.
import {
  listPushTokensMePushTokensGet,
  registerPushTokenMePushTokensPost,
  revokePushTokenMePushTokensPushTokenIdDelete,
} from "@takab/sdk";
import * as Notifications from "expo-notifications";
import { Linking, Platform } from "react-native";

import { useSessionStore } from "@/auth/session.store";

import { esDeTodoElCliente } from "./alcanceCliente";
import { type PermissionSnapshot } from "./alertability";
import { tonoOficialDeLaCompilacion } from "./tonoOficial";

/** Fichero empaquetado por el plugin `expo-notifications` de `app.json`. Es el
 * MISMO tono que sale por el altavoz del gabinete (`edge/takab_edge/audio/assets/
 * siren.wav`, sha256 idéntico), y es propio de TAKAB. `D-19` lo hizo el único tono
 * de alerta, como deslinde: reproducir el oficial diría POR EL ALTAVOZ que esto es
 * SASMEX (precedente medido: T-2.104).
 *
 * [T-9.70 · D-50] Revocado en parte: desde el 2026-10-01 SASMEX y el cuórum de red
 * suenan con el OFICIAL, por su propio canal (`OFFICIAL_CHANNEL_ID`). Éste sigue para
 * la CRISIS que no autoriza evacuar y como sonido del canal oficial donde la
 * compilación no trae el recurso. */
export const SEISMIC_SOUND = "alerta_sismica.wav";

/** [T-9.70 · D-50] El canal por el que la nube entrega la CRISIS que AUTORIZA evacuar
 * (SASMEX o cuórum), con el sonido oficial del SASMEX. Su sonido es el RECURSO
 * `res/raw/alerta_oficial.wav`, que el plugin de prebuild (`plugins/tonoOficial.js`)
 * llena con el oficial o, sin él, con el tono propio. El canal guarda la referencia y
 * no una copia: una APK posterior que traiga el oficial lo cambia sin reinstalar. */
export const OFFICIAL_CHANNEL_ID = "alerta_oficial_v1";
export const OFFICIAL_SOUND = "alerta_oficial.wav";

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
 * legacy — no editar en sitio.
 *
 * [T-9.12] Y tocó `_v3`: el audio pasa a uso ALARMA (ver `audioDeAlarma`). */
export const SEISMIC_CHANNEL_ID = "seismic_alert_v3";

/** [T-9.12] ⚠️ POR QUÉ LOS CANALES QUE DESPIERTAN SUENAN COMO ALARMA.
 *
 * Medido en el Pixel el 2026-09-27, con «No molestar» en modo prioridad (el «Hora de
 * dormir» de fábrica de Android): la push de CRISIS llegó con la pantalla apagada y
 * NO sonó ni vibró hasta que se encendió la pantalla, y la voz del MOVIMIENTO no se
 * oyó. `bypassDnd: true` no hacía nada: Android sólo lo respeta si el usuario le da
 * a la app el acceso de «No molestar» a mano, y lo apaga en silencio
 * (`dumpsys notification` ⇒ `mBypassDnd=false`). Lo que el modo prioridad deja pasar
 * por defecto es el audio de uso ALARMA — el mismo que usa el despertador —, y ese
 * es el uso honesto para un aviso que tiene que sacar a alguien de la cama.
 *
 * El uso del audio es INMUTABLE en un canal ya creado, igual que el sonido: por eso
 * cambian los tres ids y los viejos se retiran. `bypassDnd` se queda (con el acceso
 * concedido, además pasa el modo «silencio total»). */
function audioDeAlarma(): Notifications.AudioAttributesInput {
  // Función y no constante de módulo: así importar este fichero no toca los enums
  // nativos (los tests que mockean `expo-notifications` a medias no los traen).
  return {
    usage: Notifications.AndroidAudioUsage.ALARM,
    contentType: Notifications.AndroidAudioContentType.SONIFICATION,
    flags: {
      enforceAudibility: false,
      requestHardwareAudioVideoSynchronization: false,
    },
  };
}

/** Canales cuyo audio ya no se puede cambiar: se borran DESPUÉS de crear los vigentes. */
const CANALES_RETIRADOS = [
  "seismic_alert",
  "seismic_alert_v2",
  "building_alarm",
  "building_movement_v1",
] as const;

/** [T-2.147.a · D-05] Activación manual del inmueble (quórum de pánico).
 *
 * Este canal FALTABA: `notify/push.py` entregaba la clase PANIC por él desde el
 * 2026-08-16 y la app no lo creaba. FCM, ante un canal inexistente, cae al canal
 * por defecto —importancia DEFAULT, SIN bypass de No Molestar—, así que el push
 * que tiene que sacar a una brigada de la cama a las 3 a.m. llegaba como una
 * notificación cualquiera. `android.priority: "high"` no lo salvaba: en Android 8+
 * el heads-up y el DND los gobierna la importancia del CANAL. */
export const PANIC_CHANNEL_ID = "building_alarm_v2";
export const OPS_CHANNEL_ID = "ops";

/** [T-9.11 · D-39] Movimiento detectado por el sensor PROPIO del inmueble.
 *
 * NO es una alerta sísmica oficial —una estación sola no ordena evacuar— pero la
 * brigada tiene que ir a verificar, también a las 3 a.m.: por eso despierta como
 * el sísmico (MAX + bypass de No Molestar) y NO suena como él. Lleva su propio
 * audio de voz (`movimiento_inmueble.wav`) y su propia vibración: vestir de
 * sismo un aviso local es el defecto de T-2.104.
 *
 * Solo lo reciben los roles con `movement_alert` (la nube filtra); el ocupante no.
 * Como todo canal Android, su importancia y su sonido son inmutables tras
 * crearlo: si cambian, `_v2` — nunca editar en sitio. [T-9.12] Y cambió: `_v2`
 * suena con uso ALARMA. */
export const MOVEMENT_CHANNEL_ID = "building_movement_v2";
export const MOVEMENT_SOUND = "movimiento_inmueble.wav";

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
    audioAttributes: audioDeAlarma(),
    vibrationPattern: [0, 500, 500, 500, 500, 500],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  // [T-9.70 · D-50] La CRISIS de SASMEX y del cuórum: despierta igual que la sísmica y
  // suena por el recurso del oficial. Sin recurso en la compilación (sin el plugin),
  // el tono propio: el canal NUNCA apunta a un recurso inexistente.
  await Notifications.setNotificationChannelAsync(OFFICIAL_CHANNEL_ID, {
    name: "Alerta sísmica oficial",
    importance: Notifications.AndroidImportance.MAX,
    bypassDnd: true,
    sound: tonoOficialDeLaCompilacion() === null ? SEISMIC_SOUND : OFFICIAL_SOUND,
    audioAttributes: audioDeAlarma(),
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
    audioAttributes: audioDeAlarma(),
    vibrationPattern: [0, 200, 200, 200, 200, 200, 200, 200],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  // Despierta a la brigada (MAX + bypass de DND) con voz propia y un patrón de
  // vibración largo-corto que no se confunde con el sísmico ni con el de pánico.
  await Notifications.setNotificationChannelAsync(MOVEMENT_CHANNEL_ID, {
    name: "Movimiento en el inmueble",
    importance: Notifications.AndroidImportance.MAX,
    bypassDnd: true,
    sound: MOVEMENT_SOUND,
    audioAttributes: audioDeAlarma(),
    vibrationPattern: [0, 800, 300, 200, 300, 800],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  await Notifications.setNotificationChannelAsync(OPS_CHANNEL_ID, {
    name: "Operación TAKAB",
    importance: Notifications.AndroidImportance.DEFAULT,
  });
  // Los viejos se retiran DESPUÉS de crear los vigentes: si el borrado fuera primero
  // y la creación fallara, el teléfono se quedaría sin canal ninguno. Best-effort —
  // en una instalación limpia no existen y borrarlos no es un error.
  for (const viejo of CANALES_RETIRADOS) {
    try {
      await Notifications.deleteNotificationChannelAsync(viejo);
    } catch {
      // un canal que no existe no hay que borrarlo; jamás bloquea el registro
    }
  }
}

function toSnapshot(
  p: Notifications.NotificationPermissionsStatus,
): PermissionSnapshot {
  return {
    granted: p.status === "granted",
    canAskAgain: p.canAskAgain,
    iosCriticalAllowed:
      Platform.OS === "ios" ? (p.ios?.allowsCriticalAlerts ?? false) : null,
    androidDndBypass: null,
  };
}

export async function getPermissionSnapshot(): Promise<PermissionSnapshot> {
  return toSnapshot(await Notifications.getPermissionsAsync());
}

/** [T-9.13] ¿El canal sísmico rompe «No molestar»? Lo dice su `bypassDnd`.
 *
 * Medido en un Pixel 8 Pro con Android 17 (2026-09-30): el uso ALARMA del canal
 * (T-9.12) ya NO basta —Android lo rebaja a NOTIFICACIÓN al publicar y la ALERTA
 * SÍSMICA llegó interceptada—, y lo que decide es `bypassDnd`. Android sólo lo
 * fija si la app tiene el acceso a «No molestar» al crear o reaplicar el canal, y
 * lo RESPETA aunque luego se retire el acceso: la marca, no el acceso, es la verdad.
 * `null` = sin canal todavía, o no se pudo leer. */
export async function leerPasoNoMolestar(): Promise<boolean | null> {
  if (Platform.OS !== "android") {
    return null;
  }
  try {
    // [T-9.70 · D-50] SASMEX y el cuórum llegan por el canal OFICIAL; la CRISIS que no
    // autoriza, por el sísmico. Rompe «No molestar» sólo si LOS DOS lo hacen.
    const marcas: boolean[] = [];
    for (const id of [SEISMIC_CHANNEL_ID, OFFICIAL_CHANNEL_ID]) {
      const canal = await Notifications.getNotificationChannelAsync(id);
      if (canal) {
        marcas.push(canal.bypassDnd === true);
      }
    }
    return marcas.length === 0 ? null : marcas.every(Boolean);
  } catch {
    return null;
  }
}

/** [T-9.13] Los permisos + si la alerta rompe «No molestar». Reaplica los canales
 * ANTES de leer: un acceso recién concedido en los ajustes sólo fija la marca
 * cuando la app vuelve a aplicar el canal, y sin esto no se vería hasta reinstalar. */
export async function getAlertabilitySnapshot(): Promise<PermissionSnapshot> {
  const base = await getPermissionSnapshot();
  if (Platform.OS !== "android" || !base.granted) {
    return base;
  }
  try {
    await configureAndroidChannels();
  } catch (err) {
    console.warn("push: no se pudieron reaplicar los canales de Android", err);
  }
  return { ...base, androidDndBypass: await leerPasoNoMolestar() };
}

/** [T-9.13] Abre el ajuste de Android donde se concede el acceso a «No molestar». */
export async function abrirAccesoNoMolestar(): Promise<void> {
  await Linking.sendIntent("android.settings.NOTIFICATION_POLICY_ACCESS_SETTINGS");
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

export type PushRegistration =
  "registered" | "no-permission" | "no-site" | "error";

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
export async function registerDeviceForPush(
  siteId: string | null,
): Promise<PushRegistration> {
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
  // [D-42] El rol de TODO el cliente (tenant_admin con `site_scope: "*"`) se
  // registra SIN inmueble, siempre: la nube lo alcanza en cualquier inmueble de
  // su tenant. Aunque haya ADOPTADO un sitio de una push (para ver ese
  // incidente), registrar ese sitio lo estrecharía a un solo edificio. El rol se
  // lee de la sesión viva —no de un parámetro— para no cambiar la firma.
  const deTodoElCliente = esDeTodoElCliente(useSessionStore.getState().me);
  if (!siteId && !deTodoElCliente) {
    // Sin inmueble no hay a quién pertenecer: un token con `site_id: null` no es
    // destinatario de nada. Registrarlo dejaría una fila que PARECE un teléfono
    // cubierto y no lo es (regla de oro 7). Se declara y se reintenta solo, en
    // cuanto el sitio vigilado exista — el enrolamiento lo fija (T-2.103) y el
    // efecto de `_layout` vuelve a llamar aquí.
    return "no-site";
  }
  try {
    const device = await Notifications.getDevicePushTokenAsync();
    const token =
      typeof device.data === "string"
        ? device.data
        : JSON.stringify(device.data);
    const res = await registerPushTokenMePushTokensPost({
      body: {
        platform: Platform.OS === "ios" ? "ios" : "android",
        token,
        site_id: deTodoElCliente ? null : siteId,
      },
    });
    if (res.error) {
      console.warn("push: el backend rechazó el registro del token", res.error);
      return "error";
    }
    return "registered";
  } catch (err) {
    console.warn(
      "push: registro fallido (best-effort, se reintenta al reabrir)",
      err,
    );
    return "error";
  }
}

export type PushUnregistration = "revoked" | "none" | "error";

/** Cuánto se espera al token nativo (FCM/APNs) al cerrar sesión: sin servicios
 * de Google o sin red puede no volver nunca, y el logout no se cuelga por eso. */
const NATIVE_TOKEN_TIMEOUT_MS = 4_000;

/** [T-8.04 · A-020] Da de baja en el backend el token push de ESTE aparato.
 *
 * `DELETE /me/push-tokens/{id}` existía y nadie lo llamaba: tras «Cerrar sesión»
 * el token seguía ligado al usuario y al inmueble, y el teléfono de alguien que
 * ya no está seguía recibiendo las alertas del edificio. Se busca la fila por
 * el token NATIVO (el mismo que registra `registerDeviceForPush`) entre las del
 * portador: el mismo usuario puede tener OTRO teléfono que sí debe despertar.
 *
 * Se llama con la sesión aún viva (el DELETE necesita Bearer). Best-effort: jamás
 * lanza — el cierre de sesión sigue pase lo que pase aquí. */
export async function unregisterOwnPushToken(): Promise<PushUnregistration> {
  let token: string;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const device = await Promise.race([
      Notifications.getDevicePushTokenAsync(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("token nativo: sin respuesta")),
          NATIVE_TOKEN_TIMEOUT_MS,
        );
      }),
    ]);
    token =
      typeof device.data === "string"
        ? device.data
        : JSON.stringify(device.data);
  } catch {
    // Sin token nativo este aparato no pudo registrarse nunca: nada que dar de baja.
    return "none";
  } finally {
    clearTimeout(timer);
  }
  try {
    const list = await listPushTokensMePushTokensGet();
    if (!list.data) {
      return "error";
    }
    const propias = list.data.filter((t) => t.token === token);
    if (propias.length === 0) {
      return "none";
    }
    let ok = true;
    for (const fila of propias) {
      const res = await revokePushTokenMePushTokensPushTokenIdDelete({
        path: { push_token_id: fila.push_token_id },
      });
      if (res.error) {
        ok = false;
      }
    }
    return ok ? "revoked" : "error";
  } catch (err) {
    console.warn("push: no se pudo dar de baja el token al cerrar sesión", err);
    return "error";
  }
}
