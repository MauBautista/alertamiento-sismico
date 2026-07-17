import { deriveAlertability } from "./alertability";

describe("deriveAlertability — sin optimismo", () => {
  it("sin permiso ⇒ blocked (con re-pregunta posible)", () => {
    const a = deriveAlertability({ granted: false, canAskAgain: true, iosCriticalAllowed: null });
    expect(a.level).toBe("blocked");
    expect(a.reasons[0]).toMatch(/no están concedidas/);
  });

  it("denegado en ajustes ⇒ blocked y lo dice", () => {
    const a = deriveAlertability({ granted: false, canAskAgain: false, iosCriticalAllowed: null });
    expect(a.level).toBe("blocked");
    expect(a.reasons[0]).toMatch(/DENEGADAS/);
  });

  it("concedido sin Critical Alerts (iOS) ⇒ degraded, jamás ok", () => {
    const a = deriveAlertability({ granted: true, canAskAgain: true, iosCriticalAllowed: false });
    expect(a.level).toBe("degraded");
  });

  it("concedido pleno ⇒ ok sin motivos", () => {
    expect(
      deriveAlertability({ granted: true, canAskAgain: true, iosCriticalAllowed: true }),
    ).toEqual({ level: "ok", reasons: [] });
    // Android: critical no aplica (null) — concedido es ok
    expect(
      deriveAlertability({ granted: true, canAskAgain: true, iosCriticalAllowed: null }).level,
    ).toBe("ok");
  });
});
