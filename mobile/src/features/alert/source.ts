// Etiqueta de FUENTE del evento (spec §2.1-A) — solo datos REALES del payload:
//   sasmex          → booleano del WR-1: SIN magnitud, SIN epicentro, SIN ETA.
//   local_threshold → PGA instrumental MEDIDO por el gabinete (si ya existe).
//   quorum          → estaciones corroborantes (meta.node_count, mismo dato
//                     que el pill "CONFIRMADO · N estaciones" del Triage).
//   manual          → activación manual.
// Desconocido ⇒ el trigger crudo en mayúsculas — jamás inventar.

export type SourceInput = {
  trigger: string;
  max_pga_g: number | null;
  node_count: number | null;
};

export type SourceLabel = {
  label: string;
  /** Dato adicional REAL (PGA medido / estaciones) o null. */
  detail: string | null;
};

/** PGA legible: ≥0.01g con 2 decimales; menor, en mg (piso MEMS 0.6-1.1 mg). */
export function formatPga(pgaG: number): string {
  if (pgaG >= 0.01) {
    return `${pgaG.toFixed(2)}g`;
  }
  return `${(pgaG * 1000).toFixed(1)}mg`;
}

export function sourceLabel(input: SourceInput): SourceLabel {
  switch (input.trigger) {
    case "sasmex":
      // Contacto seco = booleano. Nada más que decir — y eso ES lo honesto.
      return { label: "FUENTE · SASMEX WR-1", detail: null };
    case "local_threshold":
      return {
        label: "FUENTE · REGLAS LOCALES",
        detail: input.max_pga_g != null ? `PGA ${formatPga(input.max_pga_g)} MEDIDO` : null,
      };
    case "quorum":
      return {
        label: "FUENTE · CUÓRUM DE RED",
        detail:
          input.node_count != null ? `CONFIRMADO · ${input.node_count} ESTACIONES` : null,
      };
    case "manual":
      return { label: "FUENTE · ACTIVACIÓN MANUAL", detail: null };
    default:
      return { label: `FUENTE · ${input.trigger.toUpperCase()}`, detail: null };
  }
}
