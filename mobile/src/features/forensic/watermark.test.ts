// 2.3 — honestidad de la marca de agua: el PGA sin dato del gabinete es
// "pendiente de sync", jamás un número inventado; el sello es "SHA-256".
import { forensicMetadata, watermarkLines, type ForensicMeta } from "./watermark";

const BASE: ForensicMeta = {
  tsDevice: "2026-07-16T10:00:00.000Z",
  ntpOffsetMs: -0.2,
  gps: [-99.13, 19.43],
  pgaG: 0.152,
  operatorId: "70000000-0000-0000-0000-00000000bb01",
  siteId: "s-1",
};

describe("watermarkLines — horneada en el pixel", () => {
  it("incluye fecha+NTP, GPS, PGA del gabinete y sello SHA-256", () => {
    const lines = watermarkLines(BASE);
    expect(lines[0]).toMatch(/EVIDENCIA FORENSE/);
    expect(lines.join("\n")).toMatch(/NTP -0.2 ms/);
    expect(lines.join("\n")).toMatch(/GPS 19.43000, -99.13000/);
    expect(lines.join("\n")).toMatch(/PGA 0.152 g \(gabinete\)/);
    expect(lines.join("\n")).toMatch(/SHA-256/);
    // §2.1-B: nada de siglas de hardware inexistente
    expect(lines.join("\n")).not.toMatch(/HSM|TPM|token hw/i);
  });

  it("sin PGA del gabinete ⇒ 'PGA: pendiente de sync' (jamás inventado)", () => {
    expect(watermarkLines({ ...BASE, pgaG: null }).join("\n")).toMatch(/PGA: pendiente de sync/);
  });

  it("sin GPS ⇒ 'sin ubicación'; sin NTP ⇒ 'NTP: S/D'", () => {
    const lines = watermarkLines({ ...BASE, gps: null, ntpOffsetMs: null }).join("\n");
    expect(lines).toMatch(/GPS: sin ubicación/);
    expect(lines).toMatch(/NTP: S\/D/);
  });
});

describe("forensicMetadata — JSON firmado adjunto", () => {
  it("marca pga_pending cuando falta el dato del gabinete", () => {
    expect(forensicMetadata(BASE).pga_pending).toBe(false);
    expect(forensicMetadata({ ...BASE, pgaG: null }).pga_pending).toBe(true);
  });

  it("integridad rotulada sha256 (§2.1-B)", () => {
    expect(forensicMetadata(BASE).integrity).toBe("sha256");
  });
});
