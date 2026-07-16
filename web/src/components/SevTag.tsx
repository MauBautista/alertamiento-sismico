import {
  INCIDENT_SEVERITY,
  UNKNOWN_SEVERITY_KIND,
  type IncidentSeverity,
  type StatusKind,
} from "@takab/design-tokens";
import { AlertOctagon, AlertTriangle, CheckCircle2, Eye } from "lucide-react";

/** Severidades del CHECK de ``incidents.severity`` (db/schema.sql), menor→mayor. */
export type Severity = IncidentSeverity;

// El contrato semántico severidad→tono/etiqueta vive en @takab/design-tokens
// (T-2.01: web y móvil resuelven idéntico); aquí solo lo web-específico.
const KIND_CLS: Record<StatusKind, string> = {
  ok: "soc-sev soc-sev--ok",
  warn: "soc-sev soc-sev--warn",
  crit: "soc-sev soc-sev--red",
};
const ICON: Record<Severity, typeof AlertOctagon> = {
  critical: AlertOctagon,
  warning: AlertTriangle,
  watch: Eye,
  info: CheckCircle2,
};

/** Pill de severidad (port de SevTag del mockup, sobre los valores reales). */
export default function SevTag({ severity }: { severity: string }) {
  const known = INCIDENT_SEVERITY[severity as Severity] as
    | (typeof INCIDENT_SEVERITY)[Severity]
    | undefined;
  if (!known) {
    // Severidad desconocida: se muestra cruda en ámbar — jamás degradar a NORMAL.
    return <span className={KIND_CLS[UNKNOWN_SEVERITY_KIND]}>{severity.toUpperCase()}</span>;
  }
  const Icon = ICON[severity as Severity];
  return (
    <span className={KIND_CLS[known.kind]}>
      <Icon size={11} aria-hidden />
      {known.label}
    </span>
  );
}
