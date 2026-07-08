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
  });
});
