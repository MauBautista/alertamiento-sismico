// [T-7.16] SISMO CONCLUIDO · ANALIZANDO — la escena de revisión.
//
// Hasta `T-7.13` un incidente se quedaba en «la alerta» para siempre: nada lo
// movía de `open`, así que la consola tenía un banner rojo indefinido y el
// operador aprendía a no leerlo. Ahora el worker lo pasa a `in_review` cuando el
// último tier del sitio vuelve a `normal` y ha pasado el retén (`D-33`), y esta
// línea es lo que se pinta entonces.
//
// **Quieta, y en la casilla que no domina.** La sacudida terminó: nadie tiene
// que evacuar, así que no hay rojo, no hay animación (T-7.19 anima la alerta,
// no esto) y no se degrada el simulacro que el equipo retomó.
//
// ⚠️ EL CONTADOR CUENTA HACIA ARRIBA, y es a propósito. La ficha pedía «DICTAMEN
// PRELIMINAR EN 00:47», pero ese contador es imposible por construcción: el
// incidente entra en revisión cuando han pasado `max(dictamen_settle_s,
// alert_hold_min_s)` desde la apertura, y el dictamen preliminar se emite al
// cumplirse `dictamen_settle_s` — o sea, ANTES. Pintar una cuenta atrás hacia un
// plazo ya vencido sería inventar una espera que no existe. Lo que el cliente sí
// puede afirmar con dato del servidor es cuánto hace que empezó el sismo.

import { Activity } from "lucide-react";
import { Link } from "react-router";

import SiteLabel from "../../components/SiteLabel";
import type { LiveIncident } from "../console/useLiveIncidents";
import { REVIEW_PASADO_MS, edadDelSismo, tituloRevision, transcurrido } from "./revision";

/** Epicentro localizado del evento, si el mapa ya lo tiene. Subconjunto de `MapEpicenter`. */
export interface EpicentroDeLaRevision {
  magnitude: number | null;
  source: string;
}

// `REVIEW_PASADO_MS` y `transcurrido` se mudaron a `revision.ts` cuando la
// tarjeta del muro tuvo que decir lo mismo que esta línea. Se re-exportan para
// no partir a quien ya las importaba de aquí.
export { REVIEW_PASADO_MS, transcurrido } from "./revision";

export default function ReviewLine({
  incident,
  siteName,
  siteCode,
  epicentro,
  now,
}: {
  incident: LiveIncident;
  siteName: string | null;
  /** [T-6.04] `sites.code`: la línea pinta la cinta DEMO si el sitio es simulado. */
  siteCode: string | null;
  epicentro: EpicentroDeLaRevision | null;
  /** Milisegundos. Se inyecta para que el reloj del test no sea el del navegador. */
  now: number;
}) {
  const edad = edadDelSismo(incident.opened_at, now);
  const enPasado = edad !== null && edad > REVIEW_PASADO_MS;

  return (
    <div
      className="soc-scene__alert"
      role="status"
      data-testid="scene-review"
      data-kind="review"
      data-past={String(enPasado)}
    >
      <Activity size={14} aria-hidden />
      <span className="soc-scene__alert-title">{tituloRevision(edad)}</span>
      <SiteLabel
        className="soc-scene__alert-site"
        name={siteName ?? `SITIO ${incident.site_id.slice(0, 8)}`}
        code={siteCode}
      />
      <span className="soc-scene__alert-meta">
        {edad === null
          ? "SIN HORA DE APERTURA"
          : enPasado
            ? `SISMO HACE ${transcurrido(edad)} · NADIE LO HA CLASIFICADO`
            : `SISMO HACE ${transcurrido(edad)}`}
        {epicentro !== null &&
          ` · EPICENTRO ${epicentro.magnitude === null ? "SIN MAGNITUD" : `M${epicentro.magnitude.toFixed(1)}`}`}
      </span>
      {/* El mismo enlace profundo que usa la consola al SOLICITAR DICTAMEN
          (`?incident=`, T-1.51). Un segundo formato de URL a triage sería una
          segunda forma de llegar al mismo sitio, y una se quedaría atrás. */}
      <Link to={`/triage?incident=${incident.incident_id}`} className="soc-scene__alert-link">
        VER DICTAMEN
      </Link>
    </div>
  );
}
