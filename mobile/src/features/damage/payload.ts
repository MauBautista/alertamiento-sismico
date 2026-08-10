// Construcción PURA del cuerpo de POST /incidents/{id}/damage-reports (2.4).
// La derivación de people_at_risk la hace el backend (categoría people_trapped);
// aquí solo se arma el payload con las evidencias ya subidas.
// El tipo de categoría se acepta ANCHO (`string`) a propósito: desde T-2.108
// el cuerpo se arma al DESPACHAR, con lo que se leyó de la cola en disco —que
// pudo escribirla otra versión de la app—, no con lo que el formulario tiene
// en pantalla. `SelectedCategory` encaja aquí sin conversiones.
export type DamageCategoryLike = { key: string; severity: string; note?: string };

export function buildDamageReportBody(args: {
  categories: DamageCategoryLike[];
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
