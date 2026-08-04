// Derivaciones del simulacro institucional (T-2.48). Puro y sin React: el
// reporte de acuse es evidencia de cumplimiento para Protección Civil, así que
// se calcula en un módulo testeable y no dentro de un render.
//
// La distinción que define este archivo: **SIN GABINETE COMANDABLE ≠ SIN
// ACUSE**. Colapsarlas en un solo "no respondió" haría creer que un edificio
// ignoró el simulacro cuando en realidad no había a quién mandárselo — un dato
// falso presentado como hecho, que es exactamente lo que prohíbe la regla de
// oro 7. Por eso el denominador de "N/M ACUSADOS" son los sitios COMANDADOS.

import type { DrillOut, DrillSiteOut } from "@takab/sdk";

/** Cuánto antes de la hora programada aparece el banner de simulacro ARMADO. */
export const ARMED_LEAD_MS = 15 * 60_000;

/**
 * Cuánto sigue anunciándose una agenda vencida que nadie ejecutó. Pasado ese
 * plazo deja de ser "lo que va a pasar" y es historial: un banner permanente de
 * un simulacro de hace tres días es ruido que acaba enseñando a ignorar banners.
 */
export const ARMED_EXPIRE_MS = 24 * 60 * 60_000;

export type DrillSiteAck =
  | "acked"
  | "pending"
  | "rejected"
  | "no_gateway"
  | "not_sent"
  | "scheduled";

const ACK_LABELS: Record<DrillSiteAck, string> = {
  acked: "ACUSADO",
  pending: "SIN ACUSE",
  rejected: "RECHAZADO POR EL GABINETE",
  no_gateway: "SIN GABINETE COMANDABLE",
  not_sent: "SIN COMANDO EMITIDO",
  scheduled: "PROGRAMADO",
};

export function ackLabel(state: DrillSiteAck): string {
  return ACK_LABELS[state];
}

/** ¿La fila es una AGENDA que todavía no se ejecutó ni se canceló? */
export function isPendingSchedule(drill: DrillOut): boolean {
  return drill.scheduled_at !== null && drill.stopped_at === null;
}

/** Estado de UN sitio dentro de un simulacro. */
export function drillSiteAck(site: DrillSiteOut, drill: DrillOut): DrillSiteAck {
  if (isPendingSchedule(drill)) return "scheduled";
  if (site.command_id === null) {
    // `commandable === false` lo afirma el servidor; ausente (contrato viejo) se
    // trata como comandable, que es la lectura conservadora: nunca se inventa
    // una excusa para un sitio que sí tenía gabinete.
    return site.commandable === false ? "no_gateway" : "not_sent";
  }
  if (site.command_status === "acked") return "acked";
  if (site.command_status === "rejected" || site.command_status === "expired") return "rejected";
  return "pending";
}

export interface DrillAckReport {
  /** Sitios que confirmaron la ejecución. */
  acked: number;
  /** Denominador honesto: sitios a los que SÍ se les emitió el comando. */
  commanded: number;
  /** Comandados sin respuesta todavía. */
  pending: number;
  /** El gabinete recibió y NO ejecutó (rechazado o vencido). */
  rejected: number;
  /** No había gabinete comandable: no cuenta como incumplimiento del sitio. */
  noGateway: number;
  /** La nube no llegó a emitir el comando (fallo de firma/publicación). */
  notSent: number;
  /** Sitios de una agenda todavía pendiente. */
  scheduled: number;
  /** Sitios apuntados en total. */
  total: number;
}

export function drillAckReport(drill: DrillOut): DrillAckReport {
  const report: DrillAckReport = {
    acked: 0,
    commanded: 0,
    pending: 0,
    rejected: 0,
    noGateway: 0,
    notSent: 0,
    scheduled: 0,
    total: drill.sites.length,
  };
  for (const site of drill.sites) {
    switch (drillSiteAck(site, drill)) {
      case "acked":
        report.acked += 1;
        report.commanded += 1;
        break;
      case "pending":
        report.pending += 1;
        report.commanded += 1;
        break;
      case "rejected":
        report.rejected += 1;
        report.commanded += 1;
        break;
      case "no_gateway":
        report.noGateway += 1;
        break;
      case "not_sent":
        report.notSent += 1;
        break;
      case "scheduled":
        report.scheduled += 1;
        break;
    }
  }
  return report;
}

/** Fase de una agenda respecto al reloj: sin banner, armado, precargado o vencido. */
export type ArmedPhase = "waiting" | "armed" | "due" | "expired";

export function armedPhase(drill: DrillOut, nowMs: number): ArmedPhase {
  if (drill.scheduled_at === null) return "waiting";
  const at = Date.parse(drill.scheduled_at);
  if (Number.isNaN(at)) return "waiting";
  if (nowMs < at - ARMED_LEAD_MS) return "waiting";
  if (nowMs < at) return "armed";
  if (nowMs <= at + ARMED_EXPIRE_MS) return "due";
  return "expired";
}

/**
 * La agenda MÁS PRÓXIMA que hoy toca anunciar, o ``null``. Solo entra lo que
 * sigue pendiente: una agenda cancelada o ya ejecutada (``stopped_at``) no se
 * anuncia — el banner dejaría de describir la realidad en cuanto se pulsa
 * EJECUTAR AHORA, y un rótulo que sobrevive al hecho que describe es una mentira
 * en pantalla.
 */
export function nextArmedDrill(items: readonly DrillOut[], nowMs: number): DrillOut | null {
  const candidates = items
    .filter((d) => isPendingSchedule(d))
    .filter((d) => {
      const phase = armedPhase(d, nowMs);
      return phase === "armed" || phase === "due";
    });
  if (candidates.length === 0) return null;
  return candidates.reduce((best, d) =>
    Date.parse(d.scheduled_at as string) < Date.parse(best.scheduled_at as string) ? d : best,
  );
}
