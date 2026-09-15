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

/** Epicentro localizado del evento, si el mapa ya lo tiene. Subconjunto de `MapEpicenter`. */
export interface EpicentroDeLaRevision {
  magnitude: number | null;
  source: string;
}

/**
 * Pasado esto sin que nadie clasifique, la línea habla EN PASADO.
 *
 * No cierra nada ni cambia ningún estado —eso es del servidor, siempre
 * (`incident_review_ttl_s`)—: cambia las PALABRAS. Un «ANALIZANDO» en presente
 * doce horas después del sismo dice que hay alguien mirando ahora mismo, y no lo
 * hay; con el TTL del servidor en su valor normal este caso ni se alcanza,
 * porque el registro ya estaría cerrado. Se alcanza justo cuando alguien puso el
 * TTL a cero para exigir cierre humano, que es cuando más importa no mentir.
 */
export const REVIEW_PASADO_MS = 6 * 3600_000;

/** `mm:ss` mientras cabe; `h:mm` en cuanto pasa de una hora. Sin decimales. */
export function transcurrido(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")} h`;
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

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
  const desde = Date.parse(incident.opened_at);
  const edad = Number.isNaN(desde) ? null : now - desde;
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
      <span className="soc-scene__alert-title">
        {enPasado ? "SISMO CONCLUIDO · SIN CLASIFICAR" : "SISMO CONCLUIDO · ANALIZANDO"}
      </span>
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
