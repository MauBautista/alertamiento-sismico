import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import {
  listPushTokensMePushTokensGet,
  registerPushTokenMePushTokensPost,
  revokePushTokenMePushTokensPushTokenIdDelete,
} from "@takab/sdk";

import {
  configureAndroidChannels,
  OPS_CHANNEL_ID,
  PANIC_CHANNEL_ID,
  registerDeviceForPush,
  SEISMIC_CHANNEL_ID,
  SEISMIC_SOUND,
  unregisterOwnPushToken,
} from "./push";

jest.mock("expo-notifications", () => ({
  AndroidImportance: { MAX: 5, DEFAULT: 3 },
  AndroidNotificationVisibility: { PUBLIC: 1 },
  setNotificationChannelAsync: jest.fn(async () => null),
  deleteNotificationChannelAsync: jest.fn(async () => true),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getDevicePushTokenAsync: jest.fn(),
}));

jest.mock("@takab/sdk", () => ({
  registerPushTokenMePushTokensPost: jest.fn(),
  listPushTokensMePushTokensGet: jest.fn(),
  revokePushTokenMePushTokensPushTokenIdDelete: jest.fn(),
}));

const mocked = Notifications as jest.Mocked<typeof Notifications>;
const mockedRegister = registerPushTokenMePushTokensPost as jest.Mock;
const mockedList = listPushTokensMePushTokensGet as jest.Mock;
const mockedRevoke = revokePushTokenMePushTokensPushTokenIdDelete as jest.Mock;

function setPlatform(os: "ios" | "android") {
  Object.defineProperty(Platform, "OS", { value: os, configurable: true });
}

afterEach(() => {
  jest.clearAllMocks();
  setPlatform("ios");
});

describe("configureAndroidChannels", () => {
  it("android: canal sísmico con MAX + bypass de No Molestar", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).toHaveBeenCalledWith(
      SEISMIC_CHANNEL_ID,
      expect.objectContaining({ importance: 5, bypassDnd: true }),
    );
  });

  // [D-19] El tono propio no vale de nada empaquetado si el canal sigue pidiendo
  // el del sistema: es lo que pasaba hasta el 2026-08-22.
  it("android: el canal sísmico suena con el tono PROPIO, no con el del sistema", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).toHaveBeenCalledWith(
      SEISMIC_CHANNEL_ID,
      expect.objectContaining({ sound: SEISMIC_SOUND }),
    );
    expect(SEISMIC_SOUND).not.toBe("default");
  });

  // [T-2.147.a · D-05] El canal que FALTABA. La nube entrega la clase PANIC por él
  // desde el 2026-08-16; sin crearlo, FCM cae al canal por defecto (importancia
  // DEFAULT, sin bypass de DND) y el push NO despierta a la brigada.
  it("android: el canal de pánico existe, despierta como una crisis…", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).toHaveBeenCalledWith(
      PANIC_CHANNEL_ID,
      expect.objectContaining({ importance: 5, bypassDnd: true }),
    );
  });

  // …y NO suena como una: vestir de sismo una activación manual es T-2.104.
  it("android: el canal de pánico NO usa el tono sísmico", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    const panico = mocked.setNotificationChannelAsync.mock.calls.find(
      ([id]) => id === PANIC_CHANNEL_ID,
    );
    expect(panico?.[1].sound).toBe("default");
    expect(panico?.[1].sound).not.toBe(SEISMIC_SOUND);
  });

  it("android: crea los TRES canales que la nube nombra", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    const ids = mocked.setNotificationChannelAsync.mock.calls.map(([id]) => id);
    expect(new Set(ids)).toEqual(
      new Set([SEISMIC_CHANNEL_ID, PANIC_CHANNEL_ID, OPS_CHANNEL_ID]),
    );
  });

  // El sonido de un canal Android es INMUTABLE tras crearlo: sin retirar el v1, el
  // teléfono que ya lo tenía seguiría sonando con el tono viejo para siempre. Y el
  // orden importa — borrar antes de crear dejaría un hueco si la creación fallara.
  it("android: retira el canal sísmico v1, y DESPUÉS de crear el vigente", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    expect(mocked.deleteNotificationChannelAsync).toHaveBeenCalledWith("seismic_alert");
    expect(mocked.deleteNotificationChannelAsync).not.toHaveBeenCalledWith(
      SEISMIC_CHANNEL_ID,
    );
    const borrado = mocked.deleteNotificationChannelAsync.mock.invocationCallOrder[0];
    const creado = mocked.setNotificationChannelAsync.mock.invocationCallOrder;
    expect(Math.max(...creado)).toBeLessThan(borrado);
  });

  it("android: si el borrado del canal viejo falla, el registro NO se cae", async () => {
    setPlatform("android");
    mocked.deleteNotificationChannelAsync.mockRejectedValueOnce(new Error("boom"));
    await expect(configureAndroidChannels()).resolves.toBeUndefined();
  });

  it("iOS: no toca canales (no existen)", async () => {
    setPlatform("ios");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).not.toHaveBeenCalled();
    expect(mocked.deleteNotificationChannelAsync).not.toHaveBeenCalled();
  });
});

describe("registerDeviceForPush", () => {
  it("sin permiso ⇒ no-permission y NO pide token", async () => {
    mocked.getPermissionsAsync.mockResolvedValue({
      status: "denied",
      canAskAgain: true,
    } as never);
    await expect(registerDeviceForPush("site-1")).resolves.toBe("no-permission");
    expect(mocked.getDevicePushTokenAsync).not.toHaveBeenCalled();
  });

  it("[T-2.109] sin inmueble vinculado ⇒ 'no-site' y NO se registra nada", async () => {
    // Un token con `site_id: null` NO es destinatario de nada: el orquestador
    // filtra por `site_id = <uuid>` y NULL nunca iguala a un UUID. Registrarlo
    // igual crearía una fila que parece un teléfono cubierto y no lo es — y el
    // día que GATE-STORE encienda APNs/FCM la acreditación saldría verde sin
    // que sonara un solo teléfono. Se declara y no se manda.
    mocked.getPermissionsAsync.mockResolvedValue({
      status: "granted",
      canAskAgain: true,
    } as never);
    mocked.getDevicePushTokenAsync.mockResolvedValue({
      type: "android",
      data: "fcm-token-huerfano",
    } as never);

    await expect(registerDeviceForPush(null)).resolves.toBe("no-site");
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("con permiso ⇒ registra el token NATIVO con la plataforma correcta", async () => {
    setPlatform("android");
    mocked.getPermissionsAsync.mockResolvedValue({
      status: "granted",
      canAskAgain: true,
    } as never);
    mocked.getDevicePushTokenAsync.mockResolvedValue({
      type: "android",
      data: "fcm-token-xyz",
    } as never);
    mockedRegister.mockResolvedValue({ data: { token: "fcm-token-xyz" } });

    await expect(registerDeviceForPush("site-1")).resolves.toBe("registered");
    expect(mockedRegister).toHaveBeenCalledWith({
      body: { platform: "android", token: "fcm-token-xyz", site_id: "site-1" },
    });
  });

  it("rechazo del backend ⇒ error declarado (best-effort, sin romper la app)", async () => {
    mocked.getPermissionsAsync.mockResolvedValue({
      status: "granted",
      canAskAgain: true,
      ios: { allowsCriticalAlerts: false },
    } as never);
    mocked.getDevicePushTokenAsync.mockResolvedValue({ type: "ios", data: "apns" } as never);
    mockedRegister.mockResolvedValue({ error: { detail: "boom" } });
    await expect(registerDeviceForPush("site-1")).resolves.toBe("error");
  });
});

// [T-8.04 · A-020] Al cerrar sesión, el teléfono deja de ser destinatario.
//
// `DELETE /me/push-tokens/{id}` existía (mobile_me.py) y nadie lo llamaba: tras
// «Cerrar sesión» el token seguía ligado al usuario y al inmueble, así que el
// teléfono de alguien que ya no está seguía recibiendo las alertas del edificio.
// Se da de baja SÓLO el token de ESTE aparato: el mismo usuario puede tener otro
// teléfono que sí debe seguir despertando.
describe("unregisterOwnPushToken", () => {
  const fila = (id: string, token: string) => ({
    push_token_id: id,
    token,
    platform: "android",
    site_id: "site-1",
    created_at: "",
    last_seen_at: "",
    revoked_at: null,
  });

  beforeEach(() => {
    mocked.getDevicePushTokenAsync.mockResolvedValue({ type: "android", data: "fcm-mio" } as never);
  });

  it("da de baja la fila del token de ESTE aparato, y sólo ésa", async () => {
    mockedList.mockResolvedValue({ data: [fila("otro-tel", "fcm-ajeno"), fila("este", "fcm-mio")] });
    mockedRevoke.mockResolvedValue({ data: {} });

    await expect(unregisterOwnPushToken()).resolves.toBe("revoked");

    expect(mockedRevoke).toHaveBeenCalledTimes(1);
    expect(mockedRevoke).toHaveBeenCalledWith({ path: { push_token_id: "este" } });
  });

  it("si este aparato nunca se registró ⇒ 'none' y no borra nada", async () => {
    mockedList.mockResolvedValue({ data: [fila("otro-tel", "fcm-ajeno")] });
    await expect(unregisterOwnPushToken()).resolves.toBe("none");
    expect(mockedRevoke).not.toHaveBeenCalled();
  });

  it("sin token nativo (sin permiso o sin FCM) ⇒ 'none', sin llamar a la API", async () => {
    mocked.getDevicePushTokenAsync.mockRejectedValue(new Error("sin FCM"));
    await expect(unregisterOwnPushToken()).resolves.toBe("none");
    expect(mockedList).not.toHaveBeenCalled();
  });

  it("la API falla ⇒ 'error' declarado, jamás una excepción (el logout sigue)", async () => {
    mockedList.mockResolvedValue({ error: { detail: "boom" } });
    await expect(unregisterOwnPushToken()).resolves.toBe("error");
    mockedList.mockRejectedValue(new TypeError("Network request failed"));
    await expect(unregisterOwnPushToken()).resolves.toBe("error");
    mockedList.mockResolvedValue({ data: [fila("este", "fcm-mio")] });
    mockedRevoke.mockResolvedValue({ error: { detail: "404" } });
    await expect(unregisterOwnPushToken()).resolves.toBe("error");
  });
});
