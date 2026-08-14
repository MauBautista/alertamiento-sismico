// 2.3 — honestidad de la marca de agua: el PGA sin dato del gabinete es
// "pendiente de sync", jamás un número inventado; el sello es "SHA-256".
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { forensicMetadata, watermarkLines, type ForensicMeta } from "./watermark";

const BASE: ForensicMeta = {
  tsDevice: "2026-07-16T10:00:00.000Z",
  ntpOffsetMs: -0.2,
  gps: [-99.13, 19.43],
  pgaG: 0.152,
  operatorId: "70000000-0000-0000-0000-00000000bb01",
  siteId: "s-1",
  incidentId: "11111111-2222-3333-4444-555555555555",
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

// ---------------------------------------------------------------------------
// [T-2.126] PIXEL Y JSON NO PUEDEN DIVERGIR — POR CONSTRUCCIÓN, NO POR VIGILANCIA
// ---------------------------------------------------------------------------
//
// Hasta aquí los dos espejos se mantenían iguales A MANO: el pixel arma sus
// líneas y el JSON arma sus campos EN PARALELO, y un test por campo vigila que
// coincidan. Esa estructura sí puede divergir: basta añadir una línea a la marca
// —como hizo `T-2.118` con el aviso de snapshot retenido— y olvidar su campo en
// el JSON. El test que faltara nadie lo echaría de menos.
//
// El JSON lleva ahora las LÍNEAS EXACTAS que se hornean. No es una copia más:
// es el mismo array, así que un verificador puede leer la foto y confrontarla
// contra el manifiesto carácter a carácter, y no hay forma de cambiar una sin
// cambiar el otro.
const MATRIZ: [string, ForensicMeta][] = [
  ["completo y fresco", BASE],
  ["sin GPS", { ...BASE, gps: null }],
  ["sin NTP", { ...BASE, ntpOffsetMs: null }],
  ["sin PGA del gabinete", { ...BASE, pgaG: null }],
  ["snapshot retenido", { ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO }],
  [
    "el peor caso: sin nada y con snapshot viejo",
    { ...BASE, gps: null, ntpOffsetMs: null, pgaG: null, snapshotStaleSinceMs: SNAPSHOT_VIEJO },
  ],
];

describe("[T-2.126] el JSON no puede contradecir al pixel", () => {
  it.each(MATRIZ)("%s: el JSON lleva las líneas EXACTAS que se hornean", (_caso, meta) => {
    expect(forensicMetadata(meta).watermark_lines).toEqual(watermarkLines(meta));
  });

  it.each(MATRIZ)("%s: el aviso de retenido está en los dos o en ninguno", (_caso, meta) => {
    const json = forensicMetadata(meta);
    const enElPixel = watermarkLines(meta).some((l) => l.includes("METADATOS RETENIDOS"));
    expect(json.snapshot_retained).toBe(enElPixel);
    expect(json.snapshot_stale_since === null).toBe(!enElPixel);
  });

  it.each(MATRIZ)("%s: el PGA pendiente está en los dos o en ninguno", (_caso, meta) => {
    const enElPixel = watermarkLines(meta).some((l) => l.includes("pendiente de sync"));
    expect(forensicMetadata(meta).pga_pending).toBe(enElPixel);
  });

  it("una línea nueva en el pixel entra sola en el JSON (no hay que acordarse)", () => {
    // Ésta es la garantía entera: la prueba de que el vínculo es estructural y
    // no una lista de asserts que hay que ampliar cada vez.
    const conAviso = forensicMetadata({ ...BASE, snapshotStaleSinceMs: SNAPSHOT_VIEJO });
    const lineas = conAviso.watermark_lines as string[];
    expect(lineas).toHaveLength(watermarkLines(BASE).length + 1);
    expect(lineas[1]).toMatch(/METADATOS RETENIDOS/);
  });
});

// ---------------------------------------------------------------------------
// [T-2.126] LA COSTURA SIGUE CERRADA — Y ESTE TEST SE APAGA SOLO EL DÍA QUE SE ABRA
// ---------------------------------------------------------------------------
//
// `forensicMetadata` NO está cableado al flujo de captura, y la razón larga
// —con el cambio exacto que haría falta— vive en `watermark.ts`, junto a la
// función. El resumen: hoy no existe por dónde meterlo.
//
// Este test lee el CONTRATO GENERADO y exige que siga sin admitir metadatos
// forenses. No es celo: una declaración de «esto no se puede hacer todavía» se
// pudre en cuanto deja de ser cierta, y nadie vuelve a leerla. El día que el
// contrato crezca el campo, esto se pone rojo señalando la ficha, que es
// exactamente cuando hay que cablearlo.
const TIPOS_SDK = resolve(__dirname, "..", "..", "..", "..", "shared", "sdk-ts", "src", "gen", "types.gen.ts");

/** Campos declarados en `EvidenceRegisterIn` del contrato generado. */
export function camposDeEvidenceRegisterIn(fuente: string): string[] {
  const bloque = fuente.split("export type EvidenceRegisterIn = {")[1]?.split("\n};")[0];
  if (bloque === undefined) {
    throw new Error(
      `EvidenceRegisterIn no encontrado en ${TIPOS_SDK}: el contrato se movió, no está verde`,
    );
  }
  return [...bloque.matchAll(/^\s{4}(\w+)\??:/gm)].map((m) => m[1]);
}

// ---------------------------------------------------------------------------
// [T-2.135] EL INCIDENTE VA EN EL JSON, Y NO EN EL PIXEL
// ---------------------------------------------------------------------------
//
// `ForensicMeta` existe para probar la atribución «quién, dónde, CON QUÉ
// INCIDENTE», y no llevaba el incidente: esa mitad vivía sólo en el item de la
// cola (`offline/queue.ts::EvidencePayload`), que es transporte, no manifiesto.
//
// La decisión —y su porqué largo— está en `watermark.ts`. Lo que estos tests
// FIJAN es la mitad que puede romperse sin querer: que meter el incidente en el
// manifiesto no haya cambiado lo que entra en el SHA-256.
describe("[T-2.135] el manifiesto nombra el incidente; el pixel no cambia", () => {
  it("el JSON lleva el incidente: la atribución deja de estar coja", () => {
    expect(forensicMetadata(BASE).incident_id).toBe("11111111-2222-3333-4444-555555555555");
  });

  it("sin incidente lo dice con `null`, no con una cadena vacía", () => {
    // Una cadena vacía en un manifiesto forense es una afirmación falsa con
    // aspecto de dato; `null` es «no consta», que es la verdad.
    expect(forensicMetadata({ ...BASE, incidentId: null }).incident_id).toBeNull();
  });

  it("CRITERIO · el incidente NO se hornea: el pixel no lo nombra", () => {
    expect(watermarkLines(BASE).join("\n")).not.toContain("11111111");
  });

  it("CRITERIO · cambiar el incidente NO cambia lo que entra en el SHA-256", () => {
    // Es la prueba de que la spec §2.3 sigue siendo cierta byte a byte: la
    // enumeración de lo que va en el pixel no se ha movido, así que el sello
    // sigue significando exactamente lo que significaba.
    const otro = { ...BASE, incidentId: "99999999-8888-7777-6666-555555555555" };
    const sinIncidente = { ...BASE, incidentId: null };
    expect(watermarkLines(otro)).toEqual(watermarkLines(BASE));
    expect(watermarkLines(sinIncidente)).toEqual(watermarkLines(BASE));
  });

  it("y el vínculo pixel↔JSON de T-2.126 sigue en pie con el campo nuevo", () => {
    expect(forensicMetadata(BASE).watermark_lines).toEqual(watermarkLines(BASE));
  });
});

describe("[T-2.126] el contrato de evidencia sigue sin poder llevar el JSON", () => {
  const campos = camposDeEvidenceRegisterIn(readFileSync(TIPOS_SDK, "utf8"));

  it("el censo no está vacío (si esto falla, el resto de este bloque miente)", () => {
    expect(campos).toContain("sha256");
  });

  it("ningún campo puede transportar metadatos forenses", () => {
    const capaz = campos.filter((c) => /meta|forensic|manifest|attest|watermark/i.test(c));
    expect(capaz).toEqual([]);
  });
});
