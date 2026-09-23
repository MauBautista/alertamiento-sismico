// [T-8.03] El login dev tiene que poder RENOVARSE igual que el de Cognito: es lo
// que deja probar en local (e2e contra `make soc-local`) que el canal live y el
// REST sobreviven al vencimiento del token del handshake. Y renovar no puede
// cambiar QUIÉN es el portador ni CUÁNDO entró: el `sub` se conserva (sin él
// `/dev/token` inventa uno nuevo en cada llamada) y el `auth_time` también (si
// no, cada renovación rejuvenecería la sesión y el tope de D-38 no llegaría).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEV_MAX_AUTH_AGE_S,
  loadDevSession,
  readDevSession,
  renewDevToken,
  requestDevToken,
  saveDevSession,
  type DevSession,
} from "./devToken";

function fakeJwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(o))))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${b64({ alg: "RS256" })}.${b64(payload)}.firma`;
}

function tokenResponse(payload: Record<string, unknown>, expiresIn = 3600): Response {
  return new Response(
    JSON.stringify({ id_token: fakeJwt(payload), token_use: "id", expires_in: expiresIn }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function sentBody(fetchMock: ReturnType<typeof vi.fn>, call = 0): Record<string, unknown> {
  const init = fetchMock.mock.calls[call][1] as RequestInit;
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

const NOW = Date.parse("2026-09-22T12:00:00Z");

describe("devToken", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
    vi.stubEnv("VITE_API_BASE_URL", "/api");
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("guarda con la sesión lo necesario para re-emitirla: parámetros + sub del token", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse({ sub: "u-7", auth_time: NOW / 1000 }, 120));

    const session = await requestDevToken({
      role: "soc_operator",
      tenant_id: "t-1",
      expires_in: 120,
    });

    expect(sentBody(fetchMock)).toEqual({
      role: "soc_operator",
      tenant_id: "t-1",
      expires_in: 120,
    });
    expect(session.expiresAt).toBe(NOW + 120_000);
    expect(session.request).toEqual({
      role: "soc_operator",
      tenant_id: "t-1",
      expires_in: 120,
      sub: "u-7",
    });
    expect(session.authTimeMs).toBe(NOW);
  });

  it("la hora del login la dice el token (`auth_time`) cuando la trae", async () => {
    const hace2h = NOW - 7_200_000;
    fetchMock.mockResolvedValueOnce(tokenResponse({ sub: "u-7", auth_time: hace2h / 1000 }));

    const session = await requestDevToken({ role: "soc_operator", tenant_id: "t-1" });

    expect(session.authTimeMs).toBe(hace2h);
  });

  it("sin `auth_time` en el token, se deduce de la edad pedida (no de la nada)", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse({ sub: "u-7" }));

    const session = await requestDevToken({
      role: "soc_operator",
      tenant_id: "t-1",
      auth_age_s: 600,
    });

    expect(session.authTimeMs).toBe(NOW - 600_000);
    // La edad NO es un parámetro de la sesión: renovar la recalcula.
    expect(session.request).not.toHaveProperty("auth_age_s");
  });

  it("renovar conserva el sub y el auth_time: la edad pedida es la transcurrida", async () => {
    const stored: DevSession = {
      idToken: "viejo",
      expiresAt: NOW - 1_000,
      request: { role: "brigadista", tenant_id: "t-1", site_scope: "s-1", sub: "u-7" },
      authTimeMs: NOW - 5_000_000,
    };
    fetchMock.mockResolvedValueOnce(
      tokenResponse({ sub: "u-7", auth_time: stored.authTimeMs! / 1000 }),
    );

    const fresh = await renewDevToken(stored);

    expect(sentBody(fetchMock)).toEqual({
      role: "brigadista",
      tenant_id: "t-1",
      site_scope: "s-1",
      sub: "u-7",
      auth_age_s: 5_000,
    });
    expect(fresh.authTimeMs).toBe(stored.authTimeMs);
    expect(fresh.request?.sub).toBe("u-7");
    expect(fresh.idToken).not.toBe("viejo");
  });

  it("la edad pedida se acota al máximo que acepta /dev/token (100 días)", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse({ sub: "u-7" }));

    await renewDevToken({
      idToken: "x",
      expiresAt: 0,
      request: { role: "occupant", tenant_id: "t-1", sub: "u-7" },
      authTimeMs: NOW - 200 * 86_400_000,
    });

    expect(sentBody(fetchMock).auth_age_s).toBe(DEV_MAX_AUTH_AGE_S);
    expect(DEV_MAX_AUTH_AGE_S).toBe(100 * 86_400);
  });

  it("una sesión guardada SIN parámetros (formato anterior) no se puede renovar: lo dice", async () => {
    await expect(renewDevToken({ idToken: "x", expiresAt: 0 })).rejects.toThrow(/renovar/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("readDevSession devuelve la vencida (para renovarla); loadDevSession sigue sin darla", () => {
    saveDevSession({
      idToken: "vencido",
      expiresAt: NOW - 1,
      request: { role: "soc_operator", tenant_id: "t-1" },
      authTimeMs: NOW - 10_000,
    });

    expect(readDevSession()?.idToken).toBe("vencido");
    expect(loadDevSession()).toBeNull();
  });

  it("readDevSession descarta basura", () => {
    window.sessionStorage.setItem("takab.dev.session", "{no json");
    expect(readDevSession()).toBeNull();
    window.sessionStorage.setItem("takab.dev.session", JSON.stringify({ idToken: 3 }));
    expect(readDevSession()).toBeNull();
  });
});
