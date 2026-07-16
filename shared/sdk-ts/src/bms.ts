// Agrupación de la traza BMS (T-1.50, COMPARTIDA en T-2.08): la tabla
// incident_actions es un timeline append-only y un incidente SASMEX real
// dispara siren/strobe/gas/elevator/door VARIAS veces — pintarla plana se
// percibe como "duplicados". El design system pide UNA fila por actuador con
// su ÚLTIMO estado (+×N), expandible a la traza completa auditada. Funciones
// puras, sin DOM: consola y app móvil consumen EXACTAMENTE esta agrupación
// (criterio 2.1: cero transformaciones divergentes).

import type { IncidentActionOut } from './gen';

export interface ActionStateView {
  state: string;
  kind: 'critical' | 'warning' | 'ok';
}

/** Mapeo kind→estado visual (se comparte con la traza expandida). */
export const ACTION_STATE: Record<string, ActionStateView> = {
  siren_on: { state: 'ACTIVADA', kind: 'critical' },
  strobe_on: { state: 'ACTIVADO', kind: 'warning' },
  gas_valve_close: { state: 'CERRADAS', kind: 'warning' },
  elevator_recall: { state: 'RETORNADOS', kind: 'warning' },
  door_release: { state: 'LIBERADOS', kind: 'ok' },
  ack: { state: 'ACUSADO', kind: 'ok' },
  dictamen: { state: 'EMITIDO', kind: 'ok' },
  dictamen_request: { state: 'SOLICITADO', kind: 'ok' },
  epicenter_relocate: { state: 'REUBICADO', kind: 'ok' },
  notify_sent: { state: 'ENVIADA', kind: 'ok' },
  siren_test: { state: 'PROBADA', kind: 'ok' },
};

/** Etiqueta humana por canal/acción (fallback: el kind crudo en mayúsculas). */
export const CHANNEL_LABEL: Record<string, string> = {
  siren_on: 'SIRENA',
  strobe_on: 'ESTROBO',
  gas_valve_close: 'VÁLVULAS DE GAS',
  elevator_recall: 'ELEVADORES',
  door_release: 'RETENEDORES DE PUERTA',
  ack: 'ACUSES',
  dictamen: 'DICTAMEN AUTOMÁTICO',
  dictamen_request: 'DICTAMEN SOLICITADO',
  epicenter_relocate: 'EPICENTRO',
  notify_sent: 'NOTIFICACIONES',
  siren_test: 'PRUEBA DE SIRENA',
};

export interface ActuatorGroup {
  kind: string;
  label: string;
  view: ActionStateView;
  /** Acción MÁS RECIENTE del grupo (define estado, hora y actor mostrados). */
  last: IncidentActionOut;
  count: number;
  /** Traza completa del grupo, más reciente primero (auditoría expandible). */
  trace: IncidentActionOut[];
}

function viewOf(kind: string): ActionStateView {
  return ACTION_STATE[kind] ?? { state: kind.toUpperCase(), kind: 'ok' };
}

function labelOf(kind: string): string {
  return CHANNEL_LABEL[kind] ?? kind.replaceAll('_', ' ').toUpperCase();
}

/**
 * Agrupa la traza por `kind`: una fila por actuador/acción con el último
 * estado. Orden: grupos por recencia de su última acción (lo más nuevo
 * arriba); dentro del grupo la traza también va de más nueva a más vieja.
 */
export function groupActions(actions: IncidentActionOut[]): ActuatorGroup[] {
  const byKind = new Map<string, IncidentActionOut[]>();
  for (const action of actions) {
    const list = byKind.get(action.kind) ?? [];
    list.push(action);
    byKind.set(action.kind, list);
  }
  const groups: ActuatorGroup[] = [];
  for (const [kind, list] of byKind) {
    const trace = [...list].sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
    groups.push({
      kind,
      label: labelOf(kind),
      view: viewOf(kind),
      last: trace[0],
      count: trace.length,
      trace,
    });
  }
  return groups.sort((a, b) => Date.parse(b.last.ts) - Date.parse(a.last.ts));
}
