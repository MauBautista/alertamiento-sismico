// Banner de alerta del live wall (T-1.27, criterio #5).
//
// Desviación RATIFICADA vs mockup (plan maestro §B.3): el WR-1 entrega un
// booleano — NO hay magnitud preliminar ni T-MINUS. El banner dice el titular
// que le corresponde a la FUENTE + sitio + EVENT_ID + PGA MAX medido.
//
// [T-5.03] El titular y la atribución ya no están escritos a fuego: los deriva
// `alertHeadline(trigger)`. Hasta el 2026-09-02 esta caja decía «ALERTA SÍSMICA ·
// PROTÉJASE» y «EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO» para las cuatro
// fuentes, así que un quórum de pánico —que abre incidente `trigger='manual'` con
// severidad crítica por D-11— salía en el videowall como un sismo detectado por
// el sensor, mientras la app móvil decía «NO ES UNA ALERTA SÍSMICA» para el mismo
// incidente. Los literales viven en `shared/glossary/estados.json`.

import { AlertOctagon } from "lucide-react";

import { alertHeadline } from "./alertHeadline";
import type { LiveIncident } from "./useLiveIncidents";

export interface AlertBannerProps {
  /** Incidente crítico abierto más relevante, o null (sin banner). */
  incident: LiveIncident | null;
  siteName: string | null;
}

export default function AlertBanner({ incident, siteName }: AlertBannerProps) {
  if (incident === null) return null;
  const fuente = alertHeadline(incident.trigger);
  return (
    <div
      className="soc-alert"
      role="alert"
      aria-live="assertive"
      data-testid="alert-banner"
      data-trigger={incident.trigger ?? "desconocido"}
      data-seismic={String(fuente.seismic)}
    >
      <div className="soc-alert__strip">
        <AlertOctagon size={16} aria-hidden />
        {fuente.title}
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
        <span>{fuente.attribution}</span>
        <span style={{ color: "var(--tk-status-normal)" }}>{fuente.pill}</span>
      </div>
    </div>
  );
}
