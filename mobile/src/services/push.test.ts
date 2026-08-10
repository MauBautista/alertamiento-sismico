import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { registerPushTokenMePushTokensPost } from "@takab/sdk";

import {
  configureAndroidChannels,
  registerDeviceForPush,
  SEISMIC_CHANNEL_ID,
} from "./push";

jest.mock("expo-notifications", () => ({
  AndroidImportance: { MAX: 5, DEFAULT: 3 },
  AndroidNotificationVisibility: { PUBLIC: 1 },
  setNotificationChannelAsync: jest.fn(async () => null),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getDevicePushTokenAsync: jest.fn(),
}));

jest.mock("@takab/sdk", () => ({
  registerPushTokenMePushTokensPost: jest.fn(),
}));

const mocked = Notifications as jest.Mocked<typeof Notifications>;
const mockedRegister = registerPushTokenMePushTokensPost as jest.Mock;

function setPlatform(os: "ios" | "android") {
  Object.defineProperty(Platform, "OS", { value: os, configurable: true });
}

afterEach(() => {
  jest.clearAllMocks();
  setPlatform("ios");
});

describe("configureAndroidChannels", () => {
  it("android: canal seismic_alert con MAX + bypass de No Molestar", async () => {
    setPlatform("android");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).toHaveBeenCalledWith(
      SEISMIC_CHANNEL_ID,
      expect.objectContaining({ importance: 5, bypassDnd: true }),
    );
  });

  it("iOS: no toca canales (no existen)", async () => {
    setPlatform("ios");
    await configureAndroidChannels();
    expect(mocked.setNotificationChannelAsync).not.toHaveBeenCalled();
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
