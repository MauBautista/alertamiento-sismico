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
//
// [T-6.01 · U-28] La CARCASA tampoco: `.soc-alert` era una sola clase y un
// aviso instrumental —«SOLO AVISO, SIN ACTUACIÓN»— salía vestido con el rojo
// crítico y la sombra de la alerta. `data-authorizes` lo deriva de la tabla de
// escena (`authorizes`: SASMEX o cuórum) y la hoja viste el aviso de ámbar.

import { Activity, AlertOctagon } from "lucide-react";

import { alertKind, authorizes } from "../scene/scene";
import { edadDelSismo, tituloRevision, transcurrido } from "../scene/revision";
import { alertaViva } from "./alertaViva";
import { alertHeadline } from "./alertHeadline";
import type { LiveIncident } from "./useLiveIncidents";
import SiteLabel from "../../components/SiteLabel";

export interface AlertBannerProps {
  /** Incidente crítico abierto más relevante, o null (sin banner). */
  incident: LiveIncident | null;
  siteName: string | null;
  /** [T-6.04] `sites.code`: la tarjeta pinta la cinta DEMO si el sitio es simulado. */
  siteCode?: string | null;
  /**
   * [T-7.20] Milisegundos, para fechar la revisión. Se inyecta —como en
   * `ReviewLine`— para que el reloj de la prueba no sea el del navegador.
   */
  now?: number;
}

export default function AlertBanner({
  incident,
  siteName,
  siteCode = null,
  now = Date.now(),
}: AlertBannerProps) {
  if (incident === null) return null;
  // [T-7.20] EL MURO TAMBIÉN TIENE QUE DEJAR DE GRITAR.
  //
  // `T-7.16` dio la escena de revisión a la franja del shell, y la franja NO se
  // pinta en el muro (`SceneStrip`: `{!wall && …}`, porque aquí la alerta ya
  // tiene su tarjeta). Así que con el sismo ya concluido esta caja seguía
  // diciendo «ALERTA SÍSMICA · PROTÉJASE» en la pantalla que alguien mira de
  // pie, y lo único que cambiaba era que el halo se paraba. Pintar como vigente
  // lo que el servidor ya no sostiene es la regla de oro 7, y aquí costaba más
  // que en ningún otro sitio.
  //
  // La clase la decide `alertKind`, que es el ÚNICO sitio donde se decide, y las
  // palabras salen de `revision.ts`, que es el único sitio donde se escriben.
  const kind = alertKind(incident);
  const revision = kind === "review";
  const edad = edadDelSismo(incident.opened_at, now);
  const fuente = alertHeadline(incident.trigger);
  return (
    <div
      className="soc-alert"
      role="alert"
      aria-live="assertive"
      data-testid="alert-banner"
      data-trigger={incident.trigger ?? "desconocido"}
      data-seismic={String(fuente.seismic)}
      data-authorizes={String(authorizes(incident.trigger))}
      // La carcasa deja de ser la de la alerta: la hoja la viste de revisión.
      data-kind={kind ?? "none"}
      // [T-7.19 · D-30] La carcasa respira mientras el SERVIDOR sostiene la
      // alerta. En `in_review` y `closed` la animación no existe — no se apaga
      // por un cronómetro del cliente, deja de existir porque el estado cambió.
      data-alive={String(alertaViva(incident))}
    >
      <div className="soc-alert__strip">
        {revision ? <Activity size={16} aria-hidden /> : <AlertOctagon size={16} aria-hidden />}
        {revision ? tituloRevision(edad) : fuente.title}
      </div>

      <div className="soc-alert__site">
        <SiteLabel name={siteName ?? `SITIO ${incident.site_id.slice(0, 8)}`} code={siteCode} />
      </div>
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
        {/* En revisión, el sello «● AUTO» se cambia por la edad del sismo: lo que
            aquella píldora afirma —que la actuación está en curso— dejó de ser
            cierto, y la edad sí sale del dato del servidor. */}
        <span style={{ color: "var(--tk-status-normal)" }}>
          {revision
            ? edad === null
              ? "SIN HORA DE APERTURA"
              : `SISMO HACE ${transcurrido(edad)}`
            : fuente.pill}
        </span>
      </div>
    </div>
  );
}
