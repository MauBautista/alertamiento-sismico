// Bitácora del incidente (T-2.40).
//
// `incident_actions` es evidencia inmutable (blueprint §9) y la pantalla se limitaba a
// contarla: "12 ACCIONES REGISTRADAS". Doce acciones son doce decisiones —quién acusó,
// cuándo sonó la sirena, quién pidió el dictamen— y contarlas sin mostrarlas convierte
// el registro que existe precisamente para reconstruir lo ocurrido en un número.
//
// Orden cronológico del SERVIDOR: no se reordena en cliente. Una bitácora que el
// cliente reordena deja de ser una bitácora.

import { isSimulatedAction } from "@takab/sdk";

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
  // [T-2.75] Tres verbos, no uno. Un canal sin proveedor real no envió nada, y
  // un envío agotado tampoco: leerlos como "ENVIADA" en la bitácora que un
  // perito usa para reconstruir lo ocurrido es falsear la evidencia.
  notify_simulated: "NOTIFICACIÓN SIMULADA · NADIE LA RECIBIÓ",
  notify_failed: "NOTIFICACIÓN NO ENTREGADA",
  drill_start: "SIMULACRO INICIADO",
  drill_stop: "SIMULACRO TERMINADO",
};

export interface TimelineAction {
  action_id: string;
  ts: string;
  kind: string;
  actor: string;
  /** [T-2.75] Evidencia del desenlace; lleva la bandera `simulated`. */
  payload?: Record<string, unknown>;
}

/**
 * Verbo de la acción. La bandera `simulated` del payload manda sobre el mapa:
 * un rótulo que enumera se queda ciego ante el canal siguiente, y ese canal
 * caería en el fallback crudo sin decir que nadie lo recibió.
 */
export function kindLabel(action: TimelineAction): string {
  const base = KIND_LABEL[action.kind] ?? action.kind.toUpperCase();
  if (isSimulatedAction({ payload: action.payload ?? {} }) && !base.includes("SIMULAD")) {
    return `${base} · SIMULADA, NADIE LA RECIBIÓ`;
  }
  return base;
}

/** ¿Esta línea documenta algo que NO llegó a nadie? (marca visual propia) */
function isUndelivered(action: TimelineAction): boolean {
  return isSimulatedAction({ payload: action.payload ?? {} }) || action.kind === "notify_failed";
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
              <span
                className={`timeline__kind${isUndelivered(a) ? " timeline__kind--undelivered" : ""}`}
              >
                {kindLabel(a)}
              </span>
              <span className="timeline__actor soc-mono">{actorLabel(a.actor)}</span>
            </li>
          ))}
        </ol>
      </StateFrame>
    </div>
  );
}
