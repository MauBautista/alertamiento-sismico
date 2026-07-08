import type { ReactNode } from "react";

export interface LinkPillProps {
  /** ok = enlace vivo (valor crudo); crit = SIN ENLACE. El semáforo fino por
   * métrica NO existe aquí: los umbrales viven solo en el servidor. */
  kind: "ok" | "crit";
  label: string;
  value: string;
  icon: ReactNode;
}

/** Pill de enlace (MQTT / SeedLink) de la tarjeta de gabinete. */
export default function LinkPill({ kind, label, value, icon }: LinkPillProps) {
  return (
    <div className={`fleet-link fleet-link--${kind}`}>
      <span className="fleet-link__hd">
        {icon}
        <span>{label}</span>
        <span className={`soc-dot ${kind === "ok" ? "soc-dot--pulse" : ""}`} />
      </span>
      <span className="fleet-link__val">{value}</span>
    </div>
  );
}
