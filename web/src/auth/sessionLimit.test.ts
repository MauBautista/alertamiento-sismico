import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  authTimeOf,
  effectiveDeadline,
  forgetSessionWindow,
  isSessionExpiredBody,
  isSessionExpiredHeader,
  isSessionExpiredResponse,
  jwtPayload,
  maxAgeLabel,
  MAX_TIMER_MS,
  parseInstant,
  readSessionWindow,
  recordLogin,
  recordMaxAge,
} from "./sessionLimit";

/** JWT sin firma real: sólo interesa el payload (el cliente nunca lo verifica). */
function fakeJwt(payload: Record<string, unknown>): string {
  // UTF-8 primero, como hace un emisor real: `btoa` a pelo codificaría «ñ» en
  // Latin-1 y el test estaría probando un token que nadie emite.
  const b64 = (o: unknown) =>
    btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(o))))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${b64({ alg: "RS256" })}.${b64(payload)}.firma`;
}

describe("sessionLimit · el 401 del tope se distingue del token vencido", () => {
  it("la cabecera del contrato ES el tope", () => {
    expect(
      isSessionExpiredHeader('Bearer error="invalid_token", error_description="sesion_expirada"'),
    ).toBe(true);
  });

  it("un `invalid_token` cualquiera NO es el tope (ese se renueva)", () => {
    expect(isSessionExpiredHeader('Bearer error="invalid_token"')).toBe(false);
    expect(
      isSessionExpiredHeader('Bearer error="invalid_token", error_description="expired"'),
    ).toBe(false);
    expect(isSessionExpiredHeader(null)).toBe(false);
  });

  it("el cuerpo `detail: sesion_expirada` también lo es; otro detail no", () => {
    expect(isSessionExpiredBody({ detail: "sesion_expirada" })).toBe(true);
    expect(isSessionExpiredBody({ detail: "token expirado" })).toBe(false);
    expect(isSessionExpiredBody(null)).toBe(false);
  });

  it("sobre una Response: cabecera, o cuerpo si falta la cabecera — y no consume el original", async () => {
    const porCabecera = new Response(JSON.stringify({ detail: "x" }), {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Bearer error="invalid_token", error_description="sesion_expirada"',
      },
    });
    expect(await isSessionExpiredResponse(porCabecera)).toBe(true);

    const porCuerpo = new Response(JSON.stringify({ detail: "sesion_expirada" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
    expect(await isSessionExpiredResponse(porCuerpo)).toBe(true);
    // El que hizo la petición todavía puede leer su cuerpo.
    await expect(porCuerpo.json()).resolves.toEqual({ detail: "sesion_expirada" });

    const generico = new Response("no json", { status: 401 });
    expect(await isSessionExpiredResponse(generico)).toBe(false);

    const noEs401 = new Response(JSON.stringify({ detail: "sesion_expirada" }), { status: 403 });
    expect(await isSessionExpiredResponse(noEs401)).toBe(false);
  });
});

describe("sessionLimit · lectura del propio token", () => {
  it("lee `auth_time` en ms; sin él, null", () => {
    expect(authTimeOf(fakeJwt({ auth_time: 1_700_000_000 }))).toBe(1_700_000_000_000);
    expect(authTimeOf(fakeJwt({ sub: "x" }))).toBeNull();
    expect(authTimeOf("no-es-un-jwt")).toBeNull();
  });

  it("decodifica base64url con caracteres fuera de ASCII", () => {
    expect(jwtPayload(fakeJwt({ sub: "ñandú" }))?.sub).toBe("ñandú");
  });

  it("parseInstant no inventa: vacío o ilegible ⇒ null", () => {
    expect(parseInstant("2026-09-22T18:00:00Z")).toBe(Date.parse("2026-09-22T18:00:00Z"));
    expect(parseInstant(null)).toBeNull();
    expect(parseInstant(undefined)).toBeNull();
    expect(parseInstant("mañana")).toBeNull();
  });
});

describe("sessionLimit · el plazo efectivo es el MENOR de los dos", () => {
  const LOGIN = Date.parse("2026-09-22T08:00:00Z");

  it("sin ningún dato no hay plazo", () => {
    expect(effectiveDeadline({ expiresAt: null, loginAt: null, maxAgeS: null })).toBeNull();
    // La marca del login sola no basta: sin la edad máxima no hay suma posible.
    expect(effectiveDeadline({ expiresAt: null, loginAt: LOGIN, maxAgeS: null })).toBeNull();
  });

  it("el servidor solo, o el cinturón solo", () => {
    expect(effectiveDeadline({ expiresAt: LOGIN + 5, loginAt: null, maxAgeS: null })).toBe(
      LOGIN + 5,
    );
    expect(effectiveDeadline({ expiresAt: null, loginAt: LOGIN, maxAgeS: 86_400 })).toBe(
      LOGIN + 86_400_000,
    );
  });

  it("si Cognito moviera `auth_time` al refrescar, el cinturón gana", () => {
    // El servidor calcula desde un auth_time que avanzó 3 h; la marca no se movió.
    const servidor = LOGIN + 3 * 3_600_000 + 86_400_000;
    expect(effectiveDeadline({ expiresAt: servidor, loginAt: LOGIN, maxAgeS: 86_400 })).toBe(
      LOGIN + 86_400_000,
    );
  });

  it("el temporizador no puede armarse de un golpe a 30 días (desborda a 24.8 d)", () => {
    expect(30 * 86_400_000).toBeGreaterThan(MAX_TIMER_MS);
  });
});

describe("sessionLimit · la marca del login en localStorage", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("se graba al volver del login y la edad máxima se le suma después", () => {
    recordLogin(1_000);
    expect(readSessionWindow()).toEqual({ loginAt: 1_000, maxAgeS: null });
    recordMaxAge(86_400);
    expect(readSessionWindow()).toEqual({ loginAt: 1_000, maxAgeS: 86_400 });
    forgetSessionWindow();
    expect(readSessionWindow()).toEqual({ loginAt: null, maxAgeS: null });
  });

  it("la edad máxima sin login grabado no crea una marca inventada", () => {
    recordMaxAge(86_400);
    expect(readSessionWindow()).toEqual({ loginAt: null, maxAgeS: null });
  });

  it("un almacenamiento que lanza (ventana privada) no tumba la consola", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("bloqueado", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("bloqueado", "SecurityError");
    });
    expect(() => recordLogin(1)).not.toThrow();
    expect(readSessionWindow()).toEqual({ loginAt: null, maxAgeS: null });
  });

  it("basura en la clave ⇒ sin marca", () => {
    window.localStorage.setItem("takab.session.window", "{no json");
    expect(readSessionWindow()).toEqual({ loginAt: null, maxAgeS: null });
  });
});

describe("sessionLimit · el rótulo de la duración", () => {
  it.each([
    [86_400, "24 H"],
    [2_592_000, "30 DÍAS"],
    [7_776_000, "90 DÍAS"],
    [3_600, "1 H"],
  ])("%i s ⇒ «%s»", (s, label) => {
    expect(maxAgeLabel(s)).toBe(label);
  });

  it("desconocido o no redondo ⇒ null (aviso genérico, no uno inventado)", () => {
    expect(maxAgeLabel(null)).toBeNull();
    expect(maxAgeLabel(0)).toBeNull();
    expect(maxAgeLabel(1_234)).toBeNull();
  });
});
