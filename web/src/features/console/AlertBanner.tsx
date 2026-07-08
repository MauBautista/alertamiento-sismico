// Banner de alerta del live wall (T-1.27, criterio #5).
//
// Desviación RATIFICADA vs mockup (plan maestro §B.3): el WR-1 entrega un
// booleano — NO hay magnitud preliminar ni T-MINUS. El banner dice
// "ALERTA SÍSMICA · PROTÉJASE" + sitio + EVENT_ID + PGA MAX medido.

import { AlertOctagon } from "lucide-react";

import type { LiveIncident } from "./useLiveIncidents";

export interface AlertBannerProps {
  /** Incidente crítico abierto más relevante, o null (sin banner). */
  incident: LiveIncident | null;
  siteName: string | null;
}

export default function AlertBanner({ incident, siteName }: AlertBannerProps) {
  if (incident === null) return null;
  return (
    <div className="soc-alert" role="alert" aria-live="assertive" data-testid="alert-banner">
      <div className="soc-alert__strip">
        <AlertOctagon size={16} aria-hidden />
        ALERTA SÍSMICA · PROTÉJASE
      </div>

      <div className="soc-alert__site">{siteName ?? `SITIO ${incident.site_id.slice(0, 8)}`}</div>
      <div className="soc-alert__sub">
        EVENT_ID {incident.event_id ?? incident.incident_id.slice(0, 8).toUpperCase()}
      </div>

      <div className="soc-alert__pga">
        <span className="soc-alert__pga-label">PGA MAX</span>
        <span className="soc-alert__pga-value">
          {incident.max_pga_g === null ? "—" : incident.max_pga_g.toFixed(3)}
          <span className="unit">g</span>
        </span>
      </div>

      <div className="soc-alert__ack">
        <span>EDGE · RS4D · REGLAS LOCALES EJECUTADAS</span>
        <span style={{ color: "var(--tk-status-normal)" }}>● AUTO</span>
      </div>
    </div>
  );
}
