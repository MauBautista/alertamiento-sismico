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

/**
 * [T-2.75] El estado de una notificación SIMULADA: el canal no tiene proveedor
 * real, así que nadie recibió nada. Es `warning` y no `critical` a propósito —
 * no hay avería que atender, hay un canal que falta contratar.
 */
export const SIMULATED_VIEW: ActionStateView = { state: 'SIMULADA · SIN ENTREGAR', kind: 'warning' };

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
  // [T-2.75] Tres desenlaces, tres reacciones del operador: nada / falta
  // contratar el canal / el proveedor está caído AHORA. Pintarlos iguales fue
  // el tablero que decía "notificado" sin haber notificado a nadie.
  notify_simulated: SIMULATED_VIEW,
  notify_failed: { state: 'NO ENTREGADA', kind: 'critical' },
  siren_test: { state: 'PROBADA', kind: 'ok' },
};

/**
 * [T-2.75] ¿Esta acción declara que NO hubo entrega? Se lee del payload que
 * escribe el orquestador, no de una lista de `kind` — un rótulo que enumera se
 * queda ciego ante el canal siguiente, y ese canal caería en el fallback `ok`
 * (verde, "todo bien"), que es exactamente la mentira que esta tarea cierra.
 */
export function isSimulatedAction(action: Pick<IncidentActionOut, 'payload'>): boolean {
  return action.payload?.simulated === true;
}

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
  notify_simulated: 'NOTIFICACIONES SIMULADAS',
  notify_failed: 'NOTIFICACIONES NO ENTREGADAS',
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

function viewOf(action: IncidentActionOut): ActionStateView {
  // [T-2.75.a] La bandera del payload MANDA sobre el mapa, SIN excepción por
  // estar el `kind` dado de alta arriba. Esto decía lo mismo en el comentario y
  // hacía lo contrario: consultaba el mapa primero, así que un `notify_sent`
  // con `payload.simulated: true` se pintaba «ENVIADA», en verde, mientras la
  // bitácora del mismo incidente (`IncidentTimeline.kindLabel`) lo declaraba
  // simulado. Dos superficies leyendo la misma fila y contando cosas distintas.
  //
  // Y hay una tercera: el panel táctico móvil deriva de esta vista si la sirena
  // está sonando (`mobile/src/app/(brigadista)/panel.tsx`, `view.state ===
  // 'ACTIVADA'`) para habilitar el preflight de SILENCIAR. Una acción que se
  // declara simulada no sonó, así que tampoco hay nada que silenciar: con la
  // regla uniforme esa precondición deja de darse por satisfecha sola.
  //
  // La regla se ancla en `web/src/simulatedRule.test.ts`, que la exige a las dos
  // implementaciones para TODOS los kinds conocidos.
  if (isSimulatedAction(action)) {
    return SIMULATED_VIEW;
  }
  return ACTION_STATE[action.kind] ?? { state: action.kind.toUpperCase(), kind: 'ok' };
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
      view: viewOf(trace[0]),
      last: trace[0],
      count: trace.length,
      trace,
    });
  }
  return groups.sort((a, b) => Date.parse(b.last.ts) - Date.parse(a.last.ts));
}
