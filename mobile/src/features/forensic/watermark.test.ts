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
  snapshotStaleSinceMs: null,
};

/** 2026-07-16T09:42:00.000Z — el snapshot con el que se selló, 18 min viejo. */
const SNAPSHOT_VIEJO = Date.parse("2026-07-16T09:42:00.000Z");

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

// [T-2.118] EL SELLO DECLARA SU PROPIA PROCEDENCIA.
//
// `camera.tsx` no PRESENTA el dato del servidor: lo usa para SELLAR
// (`incident_id`, `max_pga_g`). Sellar una foto de evidencia con metadatos
// viejos es un problema distinto y peor que pintar un número viejo — la foto
// entra en la cadena de custodia con una atribución que no corresponde, y nadie
// que la lea meses después tiene forma de saberlo.
//
// La decisión (razón larga en `app/camera.tsx`): NO se deja de sellar —la
// evidencia es perecedera y la falta de red es justo el escenario para el que
// existe la cámara—, se sella DECLARANDO la edad. Y se declara AQUÍ, en la
// marca horneada, porque es el único lugar del sistema del que el aviso no se
// puede separar después: va en el pixel y entra en el SHA-256.
//
// El instante es ABSOLUTO y no relativo: un exhibit se lee dentro de un año, y
// «hace 18 min» no significa nada en un expediente.
describe("watermarkLines — sello con snapshot RETENIDO", () => {
  it("con snapshot fresco NO añade ninguna advertencia (no sería cierta)", () => {
    expect(watermarkLines(BASE).join("\n")).not.toMatch(/RETENIDO/);
  });

  it("con snapshot viejo HORNEA la advertencia con el instante absoluto", () => {
    const lines = watermarkLines({ ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO }).join("\n");
    expect(lines).toMatch(/METADATOS RETENIDOS/);
    expect(lines).toMatch(/2026-07-16 09:42:00Z/);
    // Y la advertencia va ARRIBA, no escondida al final: el titular manda
    // (lección de T-2.104).
    expect(watermarkLines({ ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO })[1]).toMatch(
      /METADATOS RETENIDOS/,
    );
  });

  it("la advertencia NO borra el resto del sello: sigue habiendo PGA, GPS y hora", () => {
    const lines = watermarkLines({ ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO }).join("\n");
    expect(lines).toMatch(/PGA 0.152 g \(gabinete\)/);
    expect(lines).toMatch(/GPS 19.43000, -99.13000/);
    expect(lines).toMatch(/2026-07-16 10:00:00Z/);
    expect(lines).toMatch(/SHA-256/);
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

  it("[T-2.118] el JSON dice lo MISMO que el pixel sobre la edad del snapshot", () => {
    // Si el pixel declarara «retenido» y el JSON callara, la contradicción
    // dentro del propio expediente valdría menos que no declarar nada.
    expect(forensicMetadata(BASE).snapshot_retained).toBe(false);
    expect(forensicMetadata(BASE).snapshot_stale_since).toBeNull();

    const viejo = forensicMetadata({ ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO });
    expect(viejo.snapshot_retained).toBe(true);
    expect(viejo.snapshot_stale_since).toBe("2026-07-16T09:42:00.000Z");
  });
});
