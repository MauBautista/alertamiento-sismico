import { AlertOctagon, AlertTriangle, CheckCircle2, Eye } from "lucide-react";

/** Severidades del CHECK de ``incidents.severity`` (db/schema.sql), menor→mayor. */
export type Severity = "info" | "watch" | "warning" | "critical";

const SEV: Record<Severity, { cls: string; label: string; Icon: typeof AlertOctagon }> = {
  critical: { cls: "soc-sev soc-sev--red", label: "CRÍTICO", Icon: AlertOctagon },
  warning: { cls: "soc-sev soc-sev--warn", label: "ADVERTENCIA", Icon: AlertTriangle },
  watch: { cls: "soc-sev soc-sev--warn", label: "VIGILANCIA", Icon: Eye },
  info: { cls: "soc-sev soc-sev--ok", label: "NORMAL", Icon: CheckCircle2 },
};

/** Pill de severidad (port de SevTag del mockup, sobre los valores reales). */
export default function SevTag({ severity }: { severity: string }) {
  const known = SEV[severity as Severity] as (typeof SEV)[Severity] | undefined;
  if (!known) {
    // Severidad desconocida: se muestra cruda en ámbar — jamás degradar a NORMAL.
    return <span className="soc-sev soc-sev--warn">{severity.toUpperCase()}</span>;
  }
  const { cls, label, Icon } = known;
  return (
    <span className={cls}>
      <Icon size={11} aria-hidden />
      {label}
    </span>
  );
}
