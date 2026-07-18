import { clearPendingAuth, setPendingAuth, takePendingAuth } from "./pendingAuth";

const CTX = { profile: "tactical" as const, codeVerifier: "verifier-abc", state: "state-xyz" };

describe("pendingAuth", () => {
  afterEach(() => clearPendingAuth());

  it("take devuelve lo guardado y lo consume (un solo uso)", () => {
    setPendingAuth(CTX);
    expect(takePendingAuth()).toEqual(CTX);
    expect(takePendingAuth()).toBeNull();
  });

  it("sin nada guardado ⇒ null", () => {
    expect(takePendingAuth()).toBeNull();
  });

  it("clear descarta el contexto (p.ej. iOS ya intercambió)", () => {
    setPendingAuth(CTX);
    clearPendingAuth();
    expect(takePendingAuth()).toBeNull();
  });

  it("un nuevo setPendingAuth sobreescribe al anterior", () => {
    setPendingAuth(CTX);
    setPendingAuth({ ...CTX, state: "state-2" });
    expect(takePendingAuth()?.state).toBe("state-2");
  });
});
