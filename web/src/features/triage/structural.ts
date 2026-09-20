// Modelo PURO del Triage Estructural (T-2.10): vista de los reportes de daños
// del móvil (2.4) para la consola. Sin DOM. Los reportes con personas en riesgo
// se ordenan al frente (misma prioridad que la cascada OPS que ya los notificó).
import type { DamageReportOut } from "@takab/sdk";

const CATEGORY_LABEL: Record<string, string> = {
  structural: "Daño estructural",
  non_structural: "Daño no estructural",
  water_leak: "Fuga de agua",
  gas_leak: "Fuga de gas",
  electrical: "Daño eléctrico",
  people_trapped: "Personas atrapadas o heridas",
};

const SEVERITY_RANK: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };

export interface DamageCategoryView {
  key: string;
  label: string;
  severity: string;
}

export interface DamageReportView {
  reportId: string;
  urgent: boolean;
  categories: DamageCategoryView[];
  /** Severidad más alta del reporte (para el color del encabezado). */
  topSeverity: string;
  evidenceIds: string[];
  notes: string | null;
  createdAt: string;
}

function categoryView(raw: Record<string, unknown>): DamageCategoryView {
  const key = String(raw.key ?? "");
  return {
    key,
    label: CATEGORY_LABEL[key] ?? key,
    severity: String(raw.severity ?? "low"),
  };
}

export function damageReportView(report: DamageReportOut): DamageReportView {
  const categories = report.categories.map(categoryView);
  const topSeverity =
    categories.reduce(
      (top, c) => (SEVERITY_RANK[c.severity] > SEVERITY_RANK[top] ? c.severity : top),
      "low",
    ) ?? "low";
  return {
    reportId: report.report_id,
    urgent: report.people_at_risk,
    categories,
    topSeverity,
    evidenceIds: report.evidence_ids,
    notes: report.notes,
    createdAt: report.created_at,
  };
}

/** Reportes ordenados: personas en riesgo primero, luego el más reciente. */
export function orderedDamageReports(reports: DamageReportOut[]): DamageReportView[] {
  return reports
    .map(damageReportView)
    .sort(
      (a, b) =>
        Number(b.urgent) - Number(a.urgent) || Date.parse(b.createdAt) - Date.parse(a.createdAt),
    );
}

export type VerifyState =
  | "idle"
  | "verifying"
  | "verified"
  | "tampered"
  /** [T-7.48] Registrada, pero el objeto no está en S3 todavía (o su key no
   *  existe). El servidor lo distingue —devuelve `actual_sha256: null`— y la
   *  consola lo colapsaba en «HASH ALTERADO». */
  | "sin-objeto"
  | "error";

/** Copy honesta del estado de verificación de una evidencia.
 *
 * ⚠️ [T-7.48] SON CINCO Y NO CUATRO, y el que faltaba acusaba en falso. El
 * servidor tiene TRES desenlaces para `verified: false`: el hash no casa (el
 * objeto se alteró), o no hay objeto que hashear (`actual_sha256: null`,
 * registrada y aún sin subir). La consola pintaba los dos como «HASH ALTERADO»,
 * o sea que le decía a quien firma un dictamen que su evidencia fue MANIPULADA
 * cuando lo único que pasaba es que todavía no había llegado. Un fallback no
 * puede ser `ok`, y tampoco puede ser una acusación.
 */
export function verifyLabel(state: VerifyState): string {
  switch (state) {
    case "verifying":
      return "VERIFICANDO…";
    case "verified":
      return "HASH VERIFICADO";
    case "tampered":
      return "HASH ALTERADO";
    case "sin-objeto":
      return "SIN OBJETO QUE VERIFICAR";
    case "error":
      return "NO SE PUDO VERIFICAR";
    default:
      return "VERIFICAR HASH";
  }
}
