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
  // [T-2.110] El contrario de `siren_on`, que faltaba. NO es un kind inventado
  // para poder cancelar el anterior: lo escribe el ingest desde un ACK REAL del
  // gabinete — `ACK_KIND[('siren','deactivate')] = 'siren_off'`
  // (`api/src/takab_api/ingest/handlers.py`) — y la bitácora del incidente ya lo
  // rotulaba («SIRENA SILENCIADA», `IncidentTimeline.KIND_LABEL`). Sin entrada
  // aquí caía en el fallback y se pintaba «SIREN_OFF» en verde, y —lo grave— el
  // panel táctico móvil derivaba `sirenActive` de que EXISTIERA un `siren_on`,
  // así que un `siren_on` histórico dejaba la precondición de silenciar
  // satisfecha el resto del incidente.
  siren_off: { state: 'SILENCIADA', kind: 'ok' },
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
  siren_off: 'SIRENA',
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

/**
 * [T-2.116] El estado del canal TRAS EL ARBITRAJE, tal y como lo declara el
 * gabinete en `ActuatorAck.channel_state` / `CommandAck.channel_state`
 * (`edge/takab_edge/contracts.py`, schema compartido 1.11.0). No se re-deriva
 * en el cliente: se lee.
 */
export interface ChannelState {
  channel: string;
  energized: boolean;
  activated: boolean;
  fail_safe: string;
  reason: string | null;
  alert_latched: boolean;
}

/** Lo que se sabe de la sirena, y DE DÓNDE se sabe. */
export interface SirenEvidence {
  /** ¿El canal está en su estado de protección (sonando)? */
  active: boolean;
  /** `true` = lo declara el RELÉ recalculado; `false` = sólo la última orden. */
  fromRelay: boolean;
  /** Momento de la evidencia (ts de la acción). */
  at: string;
}

/** Kinds que el ingest escribe para el canal `siren` desde un ACK del gabinete. */
const SIREN_KINDS: Record<string, boolean> = { siren_on: true, siren_off: false };

function channelStateOf(action: IncidentActionOut): ChannelState | null {
  const raw = action.payload?.channel_state;
  if (raw === null || typeof raw !== 'object') {
    return null;
  }
  const state = raw as Partial<ChannelState>;
  return typeof state.activated === 'boolean' && state.channel === 'siren'
    ? (state as ChannelState)
    : null;
}

/**
 * [T-2.110] ¿La sirena está sonando, según el ÚLTIMO dato real del gabinete?
 *
 * `null` = no consta ninguna actuación de sirena en la traza. Es un tercer
 * estado a propósito: «no lo sé» no es «está apagada», y afirmar cualquiera de
 * las dos sin dato es la regla de oro 7 al revés.
 *
 * PRECEDENCIA, y es el corazón de la ficha:
 *
 *  1. `payload.channel_state` — el estado RECALCULADO del relé. Es lo que la
 *     spec §2.1 pide pintar: «el estado del relé recalculado por el arbitraje
 *     de demandas, **no la última orden enviada**».
 *  2. el `kind` (`siren_on`/`siren_off`) — la ORDEN que se ejecutó. Es lo único
 *     que hay de un gabinete que aún no declara (1), y NO es equivalente: un
 *     `siren/deactivate` con la alerta vigente se ejecuta con éxito, escribe
 *     `siren_off` y deja la sirena sonando. Por eso (1) manda siempre que exista.
 *
 * Se descartan las acciones SIMULADAS (T-2.75.a): lo que no sonó no puede
 * sostener ni desmentir que esté sonando.
 *
 * Empate exacto de `ts`: gana SONANDO. Ante dos hechos indistinguibles, el que
 * no minimiza lo que está pasando — la misma doctrina que
 * `GpioController.siren_reason` cuando no puede explicar por qué suena.
 */
export function sirenEvidence(actions: IncidentActionOut[]): SirenEvidence | null {
  let mejor: SirenEvidence | null = null;
  for (const action of actions) {
    if (!(action.kind in SIREN_KINDS) || isSimulatedAction(action)) {
      continue;
    }
    const state = channelStateOf(action);
    const evidencia: SirenEvidence = {
      active: state !== null ? state.activated : SIREN_KINDS[action.kind],
      fromRelay: state !== null,
      at: action.ts,
    };
    if (mejor === null) {
      mejor = evidencia;
      continue;
    }
    const delta = Date.parse(evidencia.at) - Date.parse(mejor.at);
    if (delta > 0 || (delta === 0 && evidencia.active && !mejor.active)) {
      mejor = evidencia;
    }
  }
  return mejor;
}

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
