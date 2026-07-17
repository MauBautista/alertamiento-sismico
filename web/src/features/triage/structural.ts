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

export type VerifyState = "idle" | "verifying" | "verified" | "tampered" | "error";

/** Copy honesta del estado de verificación de una evidencia. */
export function verifyLabel(state: VerifyState): string {
  switch (state) {
    case "verifying":
      return "VERIFICANDO…";
    case "verified":
      return "HASH VERIFICADO";
    case "tampered":
      return "HASH ALTERADO";
    case "error":
      return "NO SE PUDO VERIFICAR";
    default:
      return "VERIFICAR HASH";
  }
}
