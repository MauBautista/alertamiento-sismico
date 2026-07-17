// HONESTIDAD del payload (LFPDPPP, spec 0.3/1.4): el GPS viaja SOLO con
// need_help + consentimiento. Cualquier otra combinación lo descarta aunque
// el fix exista — este test FALLA si alguien relaja esa regla.
import { buildCheckinPayload, whatWillBeSent } from "./payload";

const FIX: [number, number] = [-99.13, 19.43];
const BASE = {
  incidentId: "inc-1",
  zoneId: "z-1",
  fix: FIX,
  tsDevice: "2026-07-16T10:00:00Z",
};

describe("buildCheckinPayload — GPS solo con need_help + consentimiento", () => {
  it("need_help + consentimiento ⇒ el fix viaja", () => {
    const p = buildCheckinPayload({ ...BASE, status: "need_help", gpsConsent: true });
    expect(p.location).toEqual(FIX);
    expect(p.ts_device).toBe(BASE.tsDevice);
    expect(p.zone_id).toBe("z-1");
  });

  it("need_help SIN consentimiento ⇒ jamás GPS (viaja la zona)", () => {
    const p = buildCheckinPayload({ ...BASE, status: "need_help", gpsConsent: false });
    expect(p.location).toBeNull();
    expect(p.zone_id).toBe("z-1");
  });

  it('"estoy bien" JAMÁS manda GPS, ni con consentimiento y fix a la mano', () => {
    const p = buildCheckinPayload({ ...BASE, status: "safe", gpsConsent: true });
    expect(p.location).toBeNull();
  });

  it("need_help + consentimiento pero sin fix (timeout/denegado) ⇒ null declarado", () => {
    const p = buildCheckinPayload({ ...BASE, status: "need_help", gpsConsent: true, fix: null });
    expect(p.location).toBeNull();
  });
});

describe("whatWillBeSent — transparencia previa al toque", () => {
  it("declara GPS solo en la rama consentida", () => {
    expect(whatWillBeSent({ status: "need_help", gpsConsent: true, zoneName: "P10-A" })).toMatch(
      /ubicación GPS actual/,
    );
    expect(whatWillBeSent({ status: "need_help", gpsConsent: false, zoneName: "P10-A" })).toMatch(
      /SIN GPS/,
    );
    expect(whatWillBeSent({ status: "safe", gpsConsent: true, zoneName: "P10-A" })).toMatch(
      /Sin ubicación/,
    );
  });

  it("sin zona asignada lo dice, no lo esconde", () => {
    expect(whatWillBeSent({ status: "safe", gpsConsent: false, zoneName: null })).toMatch(
      /sin zona asignada/,
    );
  });
});
