// Construcción PURA del cuerpo de POST /incidents/{id}/damage-reports (2.4).
// La derivación de people_at_risk la hace el backend (categoría people_trapped);
// aquí solo se arma el payload con las evidencias ya subidas.
import type { SelectedCategory } from "./categories";

export function buildDamageReportBody(args: {
  categories: SelectedCategory[];
  notes: string;
  zoneId: string | null;
  evidenceIds: string[];
  tsDevice: string;
}) {
  return {
    categories: args.categories.map((c) => ({
      key: c.key,
      severity: c.severity,
      ...(c.note ? { note: c.note } : {}),
    })),
    notes: args.notes.trim() || null,
    zone_id: args.zoneId,
    evidence_ids: args.evidenceIds,
    ts_device: args.tsDevice,
  };
}
