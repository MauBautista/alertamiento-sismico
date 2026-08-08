// T-2.79 · El servicio de aviso/consentimiento de la app.
import { client } from "@takab/sdk";

import { decideConsent, fetchConsentStatus, needsConsent } from "./privacy";

jest.mock("@takab/sdk", () => ({
  client: { get: jest.fn(), post: jest.fn() },
}));

const get = client.get as jest.Mock;
const post = client.post as jest.Mock;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("needsConsent", () => {
  it("solo `current` no pide nada", () => {
    // Con UN solo valor de entrada este test no distinguiria la funcion de una
    // constante; se comprueban los cuatro estados del contrato.
    expect(needsConsent("current")).toBe(false);
    expect(needsConsent("missing")).toBe(true);
    expect(needsConsent("stale")).toBe(true);
    expect(needsConsent("withdrawn")).toBe(true);
  });
});

describe("fetchConsentStatus", () => {
  it("devuelve el estado servido tal cual (la app no lo recalcula)", async () => {
    const status = {
      notice: { digest: "a".repeat(64), version: "1.0.0" },
      state: "stale",
      consent: { notice_digest: "b".repeat(64) },
      blocks_emergency_actions: false,
    };
    get.mockResolvedValue({ data: status, response: { status: 200 } });
    await expect(fetchConsentStatus()).resolves.toEqual(status);
    expect(get).toHaveBeenCalledWith({ url: "/privacy/consent" });
  });

  it("sin datos devuelve null, que NO es lo mismo que 'no hay aviso'", async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 503 } });
    await expect(fetchConsentStatus()).resolves.toBeNull();
  });
});

describe("decideConsent", () => {
  it("manda el DIGEST del texto en pantalla y la via movil", async () => {
    post.mockResolvedValue({ data: { consent_id: "c1" }, response: { status: 201 } });
    const digest = "c".repeat(64);
    await expect(decideConsent("accept", digest)).resolves.toBe(true);
    expect(post).toHaveBeenCalledWith({
      url: "/privacy/consent",
      // Sin el digest el servidor tendria que adivinar que texto se acepto.
      body: { decision: "accept", digest, via: "mobile" },
    });
  });

  it("un 409 devuelve false: el aviso cambio y NO se da por aceptado", async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 409 } });
    await expect(decideConsent("accept", "d".repeat(64))).resolves.toBe(false);
  });

  it("retirar usa el mismo camino, con su decision", async () => {
    post.mockResolvedValue({ data: {}, response: { status: 201 } });
    await decideConsent("withdraw", "e".repeat(64));
    expect(post.mock.calls[0][0].body.decision).toBe("withdraw");
  });
});
