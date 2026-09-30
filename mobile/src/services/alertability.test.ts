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

// [T-9.13] Medido en un Pixel 8 Pro con Android 17 (2026-09-30): el uso de audio
// ALARMA del canal (T-9.12) ya no rompe «No molestar» — Android lo rebaja a
// NOTIFICACIÓN al publicar y la ALERTA SÍSMICA llegó interceptada (muda). Lo que
// sí la deja pasar es el `bypassDnd` del canal, que sólo se fija si la app tiene
// el acceso a «No molestar». Sin él, el teléfono está degradado y hay que DECIRLO.
describe("[T-9.13] Android · la alerta y «No molestar»", () => {
  const base = { granted: true, canAskAgain: true, iosCriticalAllowed: null };

  it("el canal sísmico NO rompe «No molestar» ⇒ degraded, lo dice y ofrece permitirlo", () => {
    const a = deriveAlertability({ ...base, androidDndBypass: false });
    expect(a.level).toBe("degraded");
    expect(a.reasons[0]).toMatch(/No molestar/);
    expect(a.reasons[0]).toMatch(/SILENCIO/);
    expect(a.accion).toBe("permitir_no_molestar");
  });

  it("lo rompe ⇒ ok", () => {
    expect(deriveAlertability({ ...base, androidDndBypass: true })).toEqual({
      level: "ok",
      reasons: [],
    });
  });

  it("sin dato (canal aún sin crear, iOS) ⇒ no se inventa un aviso", () => {
    expect(deriveAlertability({ ...base, androidDndBypass: null }).level).toBe("ok");
  });

  it("sin permiso de notificaciones manda el BLOQUEO, con salida a los ajustes", () => {
    const a = deriveAlertability({
      granted: false,
      canAskAgain: false,
      iosCriticalAllowed: null,
      androidDndBypass: false,
    });
    expect(a.level).toBe("blocked");
    expect(a.accion).toBe("abrir_ajustes");
  });
});
