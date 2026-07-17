// Marca de agua forense (2.3) — HORNEADA en el pixel (§2.1-B). Este módulo es
// PURO: arma las líneas de texto que se componen sobre el bitmap y el JSON de
// metadatos duplicado. La honestidad manda: el PGA del gabinete sale del
// backend; sin red se rotula "PGA: pendiente de sync" y JAMÁS se inventa.

export type ForensicMeta = {
  /** ISO del reloj del DISPOSITIVO al capturar (se registra tal cual). */
  tsDevice: string;
  /** Offset NTP (ms) del ÚLTIMO sync del gabinete; null = desconocido. */
  ntpOffsetMs: number | null;
  /** [lon, lat] con consentimiento; null = sin ubicación. */
  gps: [number, number] | null;
  /** PGA (g) que el gabinete registró en ese momento; null = pendiente de sync. */
  pgaG: number | null;
  /** Sub del operador táctico (identidad de la captura). */
  operatorId: string;
  /** Sitio del incidente (contexto). */
  siteId: string;
};

function fmtTs(iso: string, ntpOffsetMs: number | null): string {
  const base = iso.replace("T", " ").replace(/\.\d+Z$/, "Z");
  const off = ntpOffsetMs === null ? "NTP: S/D" : `NTP ${ntpOffsetMs >= 0 ? "+" : ""}${ntpOffsetMs.toFixed(1)} ms`;
  return `${base} · ${off}`;
}

function fmtGps(gps: [number, number] | null): string {
  if (gps === null) {
    return "GPS: sin ubicación";
  }
  const [lon, lat] = gps;
  return `GPS ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function fmtPga(pgaG: number | null): string {
  // Honestidad §2.3: sin dato del gabinete NO se inventa un número.
  return pgaG === null ? "PGA: pendiente de sync" : `PGA ${pgaG.toFixed(3)} g (gabinete)`;
}

/** Líneas de la marca de agua compuestas sobre el pixel (orden fijo). */
export function watermarkLines(meta: ForensicMeta): string[] {
  return [
    "TAKAB AILERT · EVIDENCIA FORENSE",
    fmtTs(meta.tsDevice, meta.ntpOffsetMs),
    fmtGps(meta.gps),
    fmtPga(meta.pgaG),
    `OP ${meta.operatorId.slice(0, 8)} · SHA-256`,
  ];
}

/** Metadatos duplicados en el JSON firmado adjunto al reporte (§4.2). */
export function forensicMetadata(meta: ForensicMeta): Record<string, unknown> {
  return {
    schema: "takab-forensic-v1",
    ts_device: meta.tsDevice,
    ntp_offset_ms: meta.ntpOffsetMs,
    gps: meta.gps,
    pga_g: meta.pgaG,
    pga_pending: meta.pgaG === null,
    operator_id: meta.operatorId,
    site_id: meta.siteId,
    integrity: "sha256",
  };
}
