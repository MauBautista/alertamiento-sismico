// T-2.79 · El servicio de aviso/consentimiento de la app.
import { client } from "@takab/sdk";

import {
  ConsentUnavailableError,
  decideConsent,
  fetchConsentStatus,
  needsConsent,
} from "./privacy";

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

  // INVERTIDO a proposito. Este test asertaba `resolves.toBeNull()` y con eso
  // CONGELABA el bloqueante 3: `null` viajaba hasta la pantalla, que evalua
  // `empty = !cargando && error === null && notice === null` y por tanto
  // afirmaba "SU ORGANIZACION NO TIENE AVISO PUBLICADO" con la nube caida. Una
  // ausencia afirmada sin haberla comprobado. El cliente del SDK no lanza en
  // errores HTTP (solo con `throwOnError`, que la app no activa), asi que el
  // `catch` de la pantalla era inalcanzable y el `null` pasaba por bueno.
  // Ahora "no se pudo preguntar" LANZA y "no hay aviso" es un 200 con
  // `notice: null`: dos estados distintos que se pintan distinto.
  it("un 503 LANZA: 'no se pudo preguntar' no es 'no hay aviso'", async () => {
    get.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });
    await expect(fetchConsentStatus()).rejects.toThrow(/no se pudo consultar/i);
  });

  it("un 200 con `notice: null` NO lanza: ese es el vacio honesto", async () => {
    const status = {
      notice: null,
      state: "missing",
      consent: null,
      blocks_emergency_actions: false,
    };
    get.mockResolvedValue({ data: status, response: { status: 200 } });
    await expect(fetchConsentStatus()).resolves.toEqual(status);
  });

  it("un 500 con cuerpo de error tampoco se disfraza de estado", async () => {
    get.mockResolvedValue({ error: { detail: "boom" }, response: { status: 500 } });
    await expect(fetchConsentStatus()).rejects.toThrow(ConsentUnavailableError);
  });
});

// Los desenlaces del POST no se pueden colapsar en un booleano: `false` valia
// igual para un 409 (el aviso cambio) que para un 503 (la nube no escribe), y
// quien llamaba trataba los dos como "no pasa" — que es justo lo que encerraba
// al ocupante fuera del check-in de vida.
describe("decideConsent", () => {
  it("manda el DIGEST del texto en pantalla y la via movil", async () => {
    post.mockResolvedValue({ data: { consent_id: "c1" }, response: { status: 201 } });
    const digest = "c".repeat(64);
    await expect(decideConsent("accept", digest)).resolves.toBe("recorded");
    expect(post).toHaveBeenCalledWith({
      url: "/privacy/consent",
      // Sin el digest el servidor tendria que adivinar que texto se acepto.
      body: { decision: "accept", digest, via: "mobile" },
    });
  });

  it("un 409 es `superseded`: el aviso cambio bajo el lector, no se registro", async () => {
    post.mockResolvedValue({ error: { detail: "cambio" }, response: { status: 409 } });
    await expect(decideConsent("accept", "d".repeat(64))).resolves.toBe("superseded");
  });

  it("un 503 es `unrecorded`, y NO se confunde con el 409", async () => {
    post.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });
    await expect(decideConsent("accept", "d".repeat(64))).resolves.toBe("unrecorded");
  });

  it("un 403 es `unrecorded`", async () => {
    post.mockResolvedValue({ error: { detail: "forbidden" }, response: { status: 403 } });
    await expect(decideConsent("accept", "d".repeat(64))).resolves.toBe("unrecorded");
  });

  it("la red caida NO propaga la excepcion: es un desenlace mas", async () => {
    // El cliente del SDK sí lanza cuando `fetch` rechaza. Si eso escapara,
    // cada `await decideConsent(...)` sin `try` seria otro cerrojo posible;
    // la funcion es TOTAL a proposito.
    post.mockRejectedValue(new TypeError("Network request failed"));
    await expect(decideConsent("accept", "d".repeat(64))).resolves.toBe("unrecorded");
  });

  it("retirar usa el mismo camino, con su decision", async () => {
    post.mockResolvedValue({ data: {}, response: { status: 201 } });
    await decideConsent("withdraw", "e".repeat(64));
    expect(post.mock.calls[0][0].body.decision).toBe("withdraw");
  });
});
