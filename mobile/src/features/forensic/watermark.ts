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
  /**
   * [T-2.118] Epoch ms del snapshot de `mobile-state` del que salieron
   * `incident_id` y `pgaG` CUANDO ese snapshot ya no era fresco; null = se
   * selló con dato vigente.
   *
   * Existe porque la cámara forense no PRESENTA el dato del servidor: lo
   * SELLA. Un número viejo pintado en pantalla se corrige al refrescar; un
   * número viejo horneado en el pixel entra en la cadena de custodia y ya no
   * se corrige nunca. La política —razón larga en `app/camera.tsx`— es sellar
   * igual y DECLARAR la edad, no negarse a sellar.
   */
  snapshotStaleSinceMs: number | null;
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

/** ISO legible (mismo formato que `fmtTs`) del instante del snapshot. */
function isoLegible(epochMs: number): string {
  return new Date(epochMs).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

/**
 * [T-2.118] La advertencia de procedencia, cuando el snapshot con el que se
 * sella NO era fresco. Instante ABSOLUTO y no relativo a propósito: un exhibit
 * se lee meses después y «hace 18 min» no significa nada en un expediente.
 */
function fmtSnapshot(staleSinceMs: number | null): string | null {
  if (staleSinceMs === null) {
    return null;
  }
  return `METADATOS RETENIDOS · SNAPSHOT ${isoLegible(staleSinceMs)} · sin conexión`;
}

/** Líneas de la marca de agua compuestas sobre el pixel (orden fijo).
 *
 *  La advertencia de snapshot retenido va en SEGUNDA posición, no al final:
 *  la lección de T-2.104 es que lo que se lee primero manda, y un deslinde
 *  escondido bajo cuatro líneas de metadatos no deslinda nada. */
export function watermarkLines(meta: ForensicMeta): string[] {
  const retenido = fmtSnapshot(meta.snapshotStaleSinceMs);
  return [
    "TAKAB AILERT · EVIDENCIA FORENSE",
    ...(retenido === null ? [] : [retenido]),
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
    // [T-2.118] Lo MISMO que declara el pixel: si el JSON callara la edad del
    // snapshot mientras la marca la declara, la contradicción dentro del propio
    // expediente valdría menos que no declarar nada.
    snapshot_stale_since:
      meta.snapshotStaleSinceMs === null ? null : new Date(meta.snapshotStaleSinceMs).toISOString(),
    snapshot_retained: meta.snapshotStaleSinceMs !== null,
    integrity: "sha256",
  };
}
