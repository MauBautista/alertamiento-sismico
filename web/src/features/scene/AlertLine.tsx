// [T-6.01] La ALERTA en una línea, para las cinco rutas que no son el wall.
//
// `/console` tiene su tarjeta detallada (`AlertBanner`, con PGA y atribución
// completa) anclada al escenario. Pero un inspector en `/triage` o un
// administrador en `/tenants` no tenían rastro de que había una alerta abierta
// (U-04). Esta línea es ese rastro: el MISMO titular honesto que la tarjeta
// (`alertHeadline`, T-5.03 — el titular es una atribución, no un rótulo), el
// sitio, el EVENT_ID y el camino al monitoreo.
//
// Dos tipos y no uno, porque no son la misma cosa: `alert` es una fuente que
// AUTORIZA actuar (SASMEX, cuórum) y viste rojo crítico; `notice` es un aviso
// instrumental, una activación manual o un origen no reconocido, y viste el
// ámbar de aviso. Vestir un aviso de alerta es la mitad de U-28.

import { AlertOctagon } from "lucide-react";
import { Link } from "react-router";

import { alertHeadline } from "../console/alertHeadline";
import type { LiveIncident } from "../console/useLiveIncidents";

export default function AlertLine({
  incident,
  kind,
  siteName,
}: {
  incident: LiveIncident;
  kind: "alert" | "notice";
  siteName: string | null;
}) {
  const fuente = alertHeadline(incident.trigger);
  return (
    <div
      className="soc-scene__alert"
      role="alert"
      data-testid="scene-alert"
      data-kind={kind}
      data-trigger={incident.trigger ?? "desconocido"}
    >
      <AlertOctagon size={14} aria-hidden />
      <span className="soc-scene__alert-title">{fuente.title}</span>
      <span className="soc-scene__alert-site">
        {siteName ?? `SITIO ${incident.site_id.slice(0, 8)}`}
      </span>
      <span className="soc-scene__alert-meta">
        EVENT_ID {incident.event_id ?? incident.incident_id.slice(0, 8).toUpperCase()} ·{" "}
        {fuente.attribution}
      </span>
      <Link to="/console" className="soc-scene__alert-link">
        IR AL MONITOREO
      </Link>
    </div>
  );
}
