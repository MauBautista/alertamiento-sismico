// T-2.09 — piezas PURAS del control táctico: string canónico espejo del
// servidor, DER→PEM, ack honesto y el orquestador (nonce→firma→POST) con la
// biometría y el SDK mockeados.
import type { CommandOut } from "@takab/sdk";

import { canonicalIntent } from "@/security/intent";
import { derToPem } from "@/security/deviceKey";

import { ackView } from "./ackState";
import { executeTacticalCommand } from "./service";
import { ACK_FALLBACK_TTL_MS, ACK_GRACE_MS, ackCeilingMs } from "./useCommandAck";

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

  // [T-2.116] Estos dos casos usaban `ack: { siren: "on"|"off" }`, un campo que
  // NINGÚN contrato tuvo jamás: el acuse real lleva `channel_state`, el estado
  // del canal tras el arbitraje de demandas del gabinete (schema 1.11.0). El
  // vector completo, producido por el gabinete real, vive en
  // `edge/tests/vectors/command_ack_siren_arbitrado.json`.
  const rele = (activated: boolean) => ({
    channel: "siren",
    action: "deactivate",
    success: true,
    detail: "relay",
    channel_state: {
      channel: "siren",
      energized: activated,
      activated,
      fail_safe: "NO",
      reason: activated ? "alert" : null,
      alert_latched: activated,
    },
  });

  it("silenciar CON alerta vigente: la sirena SIGUE activa, se explica", () => {
    const v = ackView(cmd({ action: "deactivate", status: "acked", ack: rele(true) }));
    expect(v.title).toMatch(/LA SIRENA SIGUE ACTIVA/);
    expect(v.detail).toMatch(/relé de la sirena TODAVÍA ENERGIZADO/);
    expect(v.detail).toMatch(/alerta vigente/);
    expect(v.tone).toBe("warn");
  });

  it("silenciar sin otra demanda: sirena silenciada", () => {
    const v = ackView(cmd({ action: "deactivate", status: "acked", ack: rele(false) }));
    expect(v.title).toBe("SIRENA SILENCIADA");
    expect(v.tone).toBe("ok");
  });

  it("el relé del acuse MANDA sobre la fase: apagado en alerta ⇒ silenciada", () => {
    // Sin esto, `alertActive` (inferencia de T-2.107) taparía un hecho medido.
    const v = ackView(cmd({ action: "deactivate", status: "acked", ack: rele(false) }), {
      alertActive: true,
    });
    expect(v.title).toBe("SIRENA SILENCIADA");
  });

  it("activar y que el relé NO quede energizado se DECLARA, no se celebra", () => {
    const v = ackView(
      cmd({ action: "activate", status: "acked", ack: { ...rele(false), action: "activate" } }),
    );
    expect(v.title).toMatch(/LA SIRENA NO QUEDÓ ACTIVA/);
    expect(v.tone).toBe("crit");
  });

  it("rejected/expired se declaran con su causa", () => {
    expect(ackView(cmd({ status: "rejected", error: "relé abierto" })).detail).toMatch(
      /relé abierto/,
    );
    expect(ackView(cmd({ status: "expired" })).phase).toBe("expired");
  });

  // [T-2.107] El acuse REAL no trae censo del relé (`handle_command_ack`
  // persiste channel/action/success/latency/detail); la fuente de «sigue
  // sonando» es entonces la alerta vigente, y se nombra.
  it("silenciar con ALERTA VIGENTE (acuse sin relé): tampoco finge éxito", () => {
    const v = ackView(
      cmd({ action: "deactivate", status: "acked", ack: { success: true, detail: "relay" } }),
      { alertActive: true },
    );
    expect(v.title).toMatch(/LA SIRENA SIGUE ACTIVA/);
    expect(v.detail).toMatch(/ALERTA VIGENTE/);
    expect(v.tone).toBe("warn");
  });

  it("sin alerta vigente el mismo acuse SÍ silencia (la frase no está a fuego)", () => {
    const v = ackView(
      cmd({ action: "deactivate", status: "acked", ack: { success: true, detail: "relay" } }),
      { alertActive: false },
    );
    expect(v.title).toBe("SIRENA SILENCIADA");
  });

  it("techo vencido ⇒ «sin confirmación», que NO es el `expired` del servidor", () => {
    const v = ackView(cmd({ status: "pending" }), { unconfirmed: true, waitCeilingS: 35 });
    expect(v.phase).toBe("unconfirmed");
    expect(v.title).toBe("SIN CONFIRMACIÓN DEL GABINETE");
    expect(v.detail).toMatch(/35 s/);
    expect(v.detail).toMatch(/NO se sabe si el gabinete ejecutó la orden/);
    // El veredicto del servidor manda sobre el techo local: si el servidor ya
    // dijo algo, se dice lo del servidor.
    expect(ackView(cmd({ status: "expired" }), { unconfirmed: true }).phase).toBe("expired");
  });

  it("la espera declara su techo desde el primer instante", () => {
    expect(ackView(cmd({ status: "pending" }), { waitCeilingS: 35 }).detail).toMatch(/hasta 35 s/);
  });
});

describe("ackCeilingMs — el techo sale del TTL REAL del comando", () => {
  it("mide `expires_at − issued_at` (tiempo del SERVIDOR) + gracia de sondeo", () => {
    // 30 s es `Settings.command_ttl_s`; la resta se hace entre dos instantes
    // del MISMO reloj, así que el desfase del teléfono no entra en la cuenta.
    expect(ackCeilingMs(cmd({}))).toBe(30_000 + ACK_GRACE_MS);
  });

  it("marcas de tiempo ilegibles ⇒ el TTL declarado, jamás una espera infinita", () => {
    expect(ackCeilingMs(cmd({ expires_at: "", issued_at: "" }))).toBe(
      ACK_FALLBACK_TTL_MS + ACK_GRACE_MS,
    );
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
