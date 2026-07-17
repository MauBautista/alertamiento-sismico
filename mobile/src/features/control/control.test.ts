// T-2.09 — piezas PURAS del control táctico: string canónico espejo del
// servidor, DER→PEM, ack honesto y el orquestador (nonce→firma→POST) con la
// biometría y el SDK mockeados.
import type { CommandOut } from "@takab/sdk";

import { canonicalIntent } from "@/security/intent";
import { derToPem } from "@/security/deviceKey";

import { ackView } from "./ackState";
import { executeTacticalCommand } from "./service";

jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (k: string) => store.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void store.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void store.delete(k)),
  };
});

const mockBio = {
  biometricKeysExist: jest.fn<Promise<{ keysExist: boolean }>, []>(),
  isSensorAvailable: jest.fn<Promise<{ available: boolean }>, []>(),
  createKeys: jest.fn<Promise<{ publicKey: string }>, []>(),
  createSignature:
    jest.fn<Promise<{ success: boolean; signature?: string; error?: string }>, [unknown]>(),
};
jest.mock("react-native-biometrics", () => ({
  __esModule: true,
  default: jest.fn(() => mockBio),
}));

const mockSdk = {
  registerDeviceKeyMeDeviceKeysPost: jest.fn(),
  issueCommandNonceSitesSiteIdCommandNoncePost: jest.fn(),
  issueCommandSitesSiteIdCommandsPost: jest.fn(),
};
jest.mock("@takab/sdk", () => ({
  registerDeviceKeyMeDeviceKeysPost: (...a: unknown[]) =>
    mockSdk.registerDeviceKeyMeDeviceKeysPost(...a),
  issueCommandNonceSitesSiteIdCommandNoncePost: (...a: unknown[]) =>
    mockSdk.issueCommandNonceSitesSiteIdCommandNoncePost(...a),
  issueCommandSitesSiteIdCommandsPost: (...a: unknown[]) =>
    mockSdk.issueCommandSitesSiteIdCommandsPost(...a),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockBio.biometricKeysExist.mockResolvedValue({ keysExist: false });
  mockBio.isSensorAvailable.mockResolvedValue({ available: true });
  mockBio.createKeys.mockResolvedValue({ publicKey: "QUJDRA==" });
  mockBio.createSignature.mockResolvedValue({ success: true, signature: "c2ln" });
});

describe("canonicalIntent — espejo EXACTO del servidor", () => {
  it("formato takab-intent-v1 con el orden fijo de campos", () => {
    expect(
      canonicalIntent({
        keyId: "k-1",
        siteId: "s-1",
        channel: "siren",
        action: "activate",
        nonce: "n-1",
      }),
    ).toBe("takab-intent-v1:k-1:s-1:siren:activate:n-1");
  });
});

describe("derToPem", () => {
  it("envuelve el DER base64 en SPKI PEM de líneas de 64", () => {
    const pem = derToPem("QUJD".repeat(30));
    expect(pem.startsWith("-----BEGIN PUBLIC KEY-----\n")).toBe(true);
    expect(pem.endsWith("\n-----END PUBLIC KEY-----")).toBe(true);
    const body = pem.split("\n").slice(1, -1);
    expect(body.every((l) => l.length <= 64)).toBe(true);
  });
});

function cmd(over: Partial<CommandOut>): CommandOut {
  return {
    command_id: "c-1",
    tenant_id: "t-1",
    site_id: "s-1",
    gateway_id: "g-1",
    issued_by: "u-1",
    channel: "siren",
    action: "activate",
    event_id: null,
    nonce: "n-1",
    issued_at: "2026-07-16T10:00:00Z",
    expires_at: "2026-07-16T10:00:30Z",
    status: "pending",
    ack: null,
    error: null,
    ...over,
  } as CommandOut;
}

describe("ackView — jamás finge éxito (spec 2.2)", () => {
  it("pending: aguardando acuse del edge", () => {
    expect(ackView(cmd({ status: "pending" })).phase).toBe("pending");
  });

  it("silenciar CON alerta vigente: la sirena SIGUE activa, se explica", () => {
    const v = ackView(cmd({ action: "deactivate", status: "acked", ack: { siren: "on" } }));
    expect(v.title).toMatch(/LA SIRENA SIGUE ACTIVA/);
    expect(v.detail).toMatch(/alerta vigente/);
    expect(v.tone).toBe("warn");
  });

  it("silenciar sin otra demanda: sirena silenciada", () => {
    const v = ackView(cmd({ action: "deactivate", status: "acked", ack: { siren: "off" } }));
    expect(v.title).toBe("SIRENA SILENCIADA");
    expect(v.tone).toBe("ok");
  });

  it("rejected/expired se declaran con su causa", () => {
    expect(ackView(cmd({ status: "rejected", error: "relé abierto" })).detail).toMatch(
      /relé abierto/,
    );
    expect(ackView(cmd({ status: "expired" })).phase).toBe("expired");
  });
});

describe("executeTacticalCommand — nonce → firma → POST", () => {
  it("feliz: registra llave, firma la intención canónica y emite el comando", async () => {
    mockSdk.registerDeviceKeyMeDeviceKeysPost.mockResolvedValue({ data: { key_id: "key-9" } });
    mockSdk.issueCommandNonceSitesSiteIdCommandNoncePost.mockResolvedValue({
      data: { nonce: "nonce-xyz", expires_at: "x", ttl_s: 90 },
    });
    mockSdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: cmd({ status: "pending" }),
    });

    const out = await executeTacticalCommand({ siteId: "s-1", action: "activate" });
    expect(out.ok).toBe(true);

    // firmó EXACTAMENTE el string canónico con el nonce del servidor
    expect(mockBio.createSignature).toHaveBeenCalledWith(
      expect.objectContaining({ payload: "takab-intent-v1:key-9:s-1:siren:activate:nonce-xyz" }),
    );
    // el POST llevó la intención completa
    const body = mockSdk.issueCommandSitesSiteIdCommandsPost.mock.calls[0][0].body;
    expect(body.intent).toEqual({ key_id: "key-9", nonce: "nonce-xyz", signature: "c2ln" });
    expect(body.channel).toBe("siren");
  });

  it("sin biometría: se declara, no se emite nada", async () => {
    mockBio.biometricKeysExist.mockResolvedValue({ keysExist: false });
    mockBio.isSensorAvailable.mockResolvedValue({ available: false });
    const out = await executeTacticalCommand({ siteId: "s-1", action: "activate" });
    expect(out).toEqual({ ok: false, reason: expect.stringMatching(/biometría/) });
    expect(mockSdk.issueCommandSitesSiteIdCommandsPost).not.toHaveBeenCalled();
  });

  it("firma cancelada por el usuario: no hay POST de comando", async () => {
    mockSdk.registerDeviceKeyMeDeviceKeysPost.mockResolvedValue({ data: { key_id: "key-9" } });
    mockSdk.issueCommandNonceSitesSiteIdCommandNoncePost.mockResolvedValue({
      data: { nonce: "n", expires_at: "x", ttl_s: 90 },
    });
    mockBio.createSignature.mockResolvedValue({ success: false, error: "cancelado" });
    const out = await executeTacticalCommand({ siteId: "s-1", action: "activate" });
    expect(out).toEqual({ ok: false, reason: "cancelado" });
    expect(mockSdk.issueCommandSitesSiteIdCommandsPost).not.toHaveBeenCalled();
  });

  it("replay (409) del servidor se traduce a mensaje honesto", async () => {
    mockSdk.registerDeviceKeyMeDeviceKeysPost.mockResolvedValue({ data: { key_id: "k" } });
    mockSdk.issueCommandNonceSitesSiteIdCommandNoncePost.mockResolvedValue({
      data: { nonce: "n", expires_at: "x", ttl_s: 90 },
    });
    mockSdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: undefined,
      response: { status: 409 },
    });
    const out = await executeTacticalCommand({ siteId: "s-1", action: "deactivate" });
    expect(out).toEqual({ ok: false, reason: expect.stringMatching(/replay/i) });
  });

  it("reutiliza la llave de hardware vigente (no re-registra)", async () => {
    const store = jest.requireMock("expo-secure-store");
    await store.setItemAsync("takab.devicekey.id.v1", "key-stored");
    mockBio.biometricKeysExist.mockResolvedValue({ keysExist: true });
    mockSdk.issueCommandNonceSitesSiteIdCommandNoncePost.mockResolvedValue({
      data: { nonce: "n", expires_at: "x", ttl_s: 90 },
    });
    mockSdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({ data: cmd({}) });
    await executeTacticalCommand({ siteId: "s-1", action: "activate" });
    expect(mockSdk.registerDeviceKeyMeDeviceKeysPost).not.toHaveBeenCalled();
    expect(mockBio.createKeys).not.toHaveBeenCalled();
  });
});
