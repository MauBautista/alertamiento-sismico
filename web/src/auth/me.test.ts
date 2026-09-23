import { describe, expect, it, vi } from "vitest";

import { getMe, MeRequestError } from "./me";

const mocks = vi.hoisted(() => ({ meMeGet: vi.fn() }));

vi.mock("@takab/sdk", () => ({ meMeGet: mocks.meMeGet }));

const ME = {
  sub: "u-1",
  tenant_id: "t-1",
  role: "soc_operator",
  site_scope: "*" as const,
  surface: "web",
  allowed_routes: ["/console", "/fleet", "/triage", "/building"],
  allowed_actions: {
    ack_incident: true,
    sign_dictamen: false,
    export: false,
    edit_thresholds: false,
    siren_test: false,
  },
};

describe("getMe", () => {
  it("devuelve el MeResponse tipado cuando la API responde 200", async () => {
    mocks.meMeGet.mockResolvedValueOnce({ data: ME, response: new Response(null) });
    await expect(getMe()).resolves.toEqual(ME);
  });

  it("lanza MeRequestError con el status cuando no hay data", async () => {
    mocks.meMeGet.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 401 }),
    });
    const err = await getMe().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(MeRequestError);
    expect((err as MeRequestError).status).toBe(401);
    // Un 401 cualquiera NO es el tope: ese se intenta renovar.
    expect((err as MeRequestError).sessionExpired).toBe(false);
  });

  // [T-8.03] El 401 del tope de sesión (D-38) se distingue del token vencido:
  // renovar no sirve y reintentarlo haría un bucle contra la API.
  it("401 con la cabecera `sesion_expirada` ⇒ sessionExpired", async () => {
    mocks.meMeGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "otra cosa" },
      response: new Response(null, {
        status: 401,
        headers: {
          "WWW-Authenticate": 'Bearer error="invalid_token", error_description="sesion_expirada"',
        },
      }),
    });
    const err = (await getMe().catch((e: unknown) => e)) as MeRequestError;
    expect(err.status).toBe(401);
    expect(err.sessionExpired).toBe(true);
  });

  it("401 con el cuerpo `sesion_expirada` (sin cabecera) ⇒ sessionExpired", async () => {
    mocks.meMeGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "sesion_expirada" },
      response: new Response(null, { status: 401 }),
    });
    const err = (await getMe().catch((e: unknown) => e)) as MeRequestError;
    expect(err.sessionExpired).toBe(true);
  });

  it("un 403 con ese texto NO es el tope (solo lo es un 401)", async () => {
    mocks.meMeGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "sesion_expirada" },
      response: new Response(null, { status: 403 }),
    });
    const err = (await getMe().catch((e: unknown) => e)) as MeRequestError;
    expect(err.sessionExpired).toBe(false);
  });
});
