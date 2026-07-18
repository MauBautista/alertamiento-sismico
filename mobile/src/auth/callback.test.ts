import { planCallback } from "./callback";
import type { PendingAuth } from "./pendingAuth";

const PENDING: PendingAuth = {
  profile: "tactical",
  codeVerifier: "verifier-abc",
  state: "state-xyz",
};

describe("planCallback", () => {
  it("code válido + state que coincide ⇒ canjear con perfil/code/verifier", () => {
    const plan = planCallback({ code: "auth-code-1", state: "state-xyz" }, PENDING);
    expect(plan).toEqual({
      kind: "exchange",
      profile: "tactical",
      code: "auth-code-1",
      codeVerifier: "verifier-abc",
    });
  });

  it("?error=… del proveedor ⇒ error con la descripción (o el código)", () => {
    expect(
      planCallback({ error: "access_denied", error_description: "MFA cancelada" }, PENDING),
    ).toEqual({ kind: "provider_error", message: "MFA cancelada" });
    expect(planCallback({ error: "server_error" }, PENDING)).toEqual({
      kind: "provider_error",
      message: "server_error",
    });
  });

  it("sin code ⇒ expired", () => {
    expect(planCallback({ state: "state-xyz" }, PENDING)).toEqual({ kind: "expired" });
  });

  it("code presente pero SIN contexto pendiente ⇒ expired (acceso perdido)", () => {
    expect(planCallback({ code: "auth-code-1", state: "state-xyz" }, null)).toEqual({
      kind: "expired",
    });
  });

  it("state que NO coincide ⇒ state_mismatch (anti-CSRF)", () => {
    expect(planCallback({ code: "auth-code-1", state: "otro-state" }, PENDING)).toEqual({
      kind: "state_mismatch",
    });
  });

  it("state ausente en el retorno ⇒ state_mismatch (no se puede verificar)", () => {
    expect(planCallback({ code: "auth-code-1" }, PENDING)).toEqual({ kind: "state_mismatch" });
  });

  it("params repetidos (string[]) ⇒ toma el primero", () => {
    const plan = planCallback(
      { code: ["auth-code-1", "dup"], state: ["state-xyz", "dup"] },
      PENDING,
    );
    expect(plan).toEqual({
      kind: "exchange",
      profile: "tactical",
      code: "auth-code-1",
      codeVerifier: "verifier-abc",
    });
  });
});
