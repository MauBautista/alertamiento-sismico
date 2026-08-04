// Bitácora del incidente (T-2.40).
//
// `incident_actions` es evidencia inmutable (blueprint §9) y la pantalla se limitaba a
// contarla: "12 ACCIONES REGISTRADAS". Doce acciones son doce decisiones —quién acusó,
// cuándo sonó la sirena, quién pidió el dictamen— y contarlas sin mostrarlas convierte
// el registro que existe precisamente para reconstruir lo ocurrido en un número.
//
// Orden cronológico del SERVIDOR: no se reordena en cliente. Una bitácora que el
// cliente reordena deja de ser una bitácora.

import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";

/** Etiquetas de `incident_actions.kind` (espejo de los verbos que escribe la API). */
const KIND_LABEL: Record<string, string> = {
  siren_on: "SIRENA ACTIVADA",
  siren_off: "SIRENA SILENCIADA",
  ack: "ACUSE DE OPERADOR",
  dictamen: "DICTAMEN EMITIDO",
  dictamen_request: "DICTAMEN SOLICITADO",
  epicenter_relocate: "EPICENTRO REUBICADO",
  headcount_closed: "PASE DE LISTA CERRADO",
  headcount_notify: "AVISO A NO REPORTADOS",
  notify_sent: "NOTIFICACIÓN ENVIADA",
  drill_start: "SIMULACRO INICIADO",
  drill_stop: "SIMULACRO TERMINADO",
};

export interface TimelineAction {
  action_id: string;
  ts: string;
  kind: string;
  actor: string;
}

export interface IncidentTimelineProps {
  actions: { data: TimelineAction[] | undefined; loading: boolean; error: string | null };
  onRetry: () => void;
}

/** Actor legible: `user:<uuid>` es ruido; `system:*` sí dice algo. */
export function actorLabel(actor: string): string {
  if (actor.startsWith("user:")) {
    return `OPERADOR ${actor.slice(5, 13)}`;
  }
  if (actor.startsWith("system:")) {
    return actor.slice(7).toUpperCase();
  }
  return actor.toUpperCase();
}

export default function IncidentTimeline({ actions, onRetry }: IncidentTimelineProps) {
  return (
    <div className="soc-card timeline" data-testid="incident-timeline">
      <div className="soc-card__hd">
        <div>
          <div>Bitácora del incidente</div>
          <div className="soc-card__sub">APPEND-ONLY · SIN PODA POR RETENCIÓN</div>
        </div>
        {/* `?? 0` habría dicho "0 ACCIONES REGISTRADAS" con la consulta fallida:
            afirmar que no pasó nada cuando lo que ocurre es que no se sabe es
            exactamente lo que prohíbe la regla de oro 7. */}
        <span className="soc-bacnet">
          ⬢ {actions.data === undefined ? "S/D" : actions.data.length} ACCIONES REGISTRADAS
        </span>
      </div>
      <StateFrame
        label="BITÁCORA"
        loading={actions.loading}
        error={actions.error}
        onRetry={onRetry}
        empty={actions.data?.length === 0}
        emptyText="SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE"
        staleSince={null}
      >
        <ol className="timeline__list">
          {(actions.data ?? []).map((a) => (
            <li key={a.action_id} className="timeline__item">
              <span className="timeline__ts soc-mono">{utcStamp(Date.parse(a.ts))}</span>
              <span className="timeline__kind">{KIND_LABEL[a.kind] ?? a.kind.toUpperCase()}</span>
              <span className="timeline__actor soc-mono">{actorLabel(a.actor)}</span>
            </li>
          ))}
        </ol>
      </StateFrame>
    </div>
  );
}
