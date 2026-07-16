// Formato HONESTO de la salud del gabinete (2.1, contrato T-1.40): un dato
// ausente es "S/D" — jamás un cero inventado. No tener UPS medido NO es lo
// mismo que estar al 0% de batería.
import type { MobileSiteHealthOut, SiteStateFrame } from "@takab/sdk";

export function fmtMetric(
  value: number | null | undefined,
  unit: string,
  digits: number = 0,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "S/D";
  }
  return `${value.toFixed(digits)}${unit}`;
}

export function upsLabel(
  powerStatus: string | null | undefined,
  batteryPct: number | null | undefined,
): string {
  if (powerStatus === "mains") {
    return "EN PARED";
  }
  if (powerStatus === "on_battery") {
    return `EN BATERÍA · ${batteryPct == null ? "S/D" : `${Math.round(batteryPct)}%`}`;
  }
  // unknown/null: nadie midió el UPS — se declara, no se adorna.
  return "S/D";
}

/** Superpone al snapshot de mobile-state un frame live MÁS NUEVO del topic
 *  site_state (kind device_health). Las MÉTRICAS se actualizan; el ``status``
 *  (OPERATIVO/DEGRADADO/SIN ENLACE) NO se recalcula local — es del servidor
 *  (verdad única de Flota) y lo refresca el poll de mobile-state. */
export function applyHealthFrame(
  snapshot: MobileSiteHealthOut,
  frame: SiteStateFrame | null,
): MobileSiteHealthOut {
  if (frame === null || frame.kind !== "device_health") {
    return snapshot;
  }
  if (
    snapshot.heartbeat_at !== null &&
    Date.parse(frame.ts) <= Date.parse(snapshot.heartbeat_at)
  ) {
    return snapshot; // el snapshot ya es más fresco que el frame
  }
  return {
    ...snapshot,
    heartbeat_at: frame.ts,
    age_s: 0,
    mqtt_rtt_ms: frame.mqtt_rtt_ms ?? null,
    seedlink_lag_s: frame.seedlink_lag_s ?? null,
    ntp_offset_ms: frame.ntp_offset_ms ?? null,
    cpu_temp_c: frame.cpu_temp_c ?? null,
    power_status: frame.power_status ?? null,
    battery_pct: frame.battery_pct ?? null,
    cert_days_remaining: frame.cert_days_remaining ?? null,
  };
}
