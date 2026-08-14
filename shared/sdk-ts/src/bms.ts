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

/**
 * [T-2.119] LOS CINCO CANALES DE ACTUACIÓN, con su polaridad y su vocabulario.
 *
 * Esto sustituye a cinco entradas sueltas de `ACTION_STATE` que se pintaban
 * crudas y no se cancelaban entre sí. `T-2.110` cerró la sirena y dejó dicho el
 * hallazgo que gobierna esto: **el kind de la traza es la ORDEN EJECUTADA, no
 * el relé** — un `deactivate` arbitrado escribe `siren_off` con la sirena
 * sonando. En gas y puertas la misma confusión es peor: «GAS CERRADO» porque
 * alguien mandó la orden, con la válvula abierta, es una mentira en la pantalla
 * de la que depende una decisión de seguridad de vida.
 *
 * POLARIDAD — el punto donde esto podía introducir una mentira nueva. Cada
 * canal tiene SU modo fail-safe (`edge/takab_edge/config/settings.py ·
 * DEFAULT_FAILSAFE`): la sirena y el estrobo son `NO`, el gas es `FAIL_CLOSE` y
 * el retenedor de puerta es `NC`. En los dos últimos, `energized` significa lo
 * CONTRARIO que en la sirena: el gas DESENERGIZADO está CERRADO, que es su
 * estado seguro, no su estado inactivo. Por eso aquí no se lee `energized`
 * jamás: se lee `activated`, que el contrato define como «¿está protegiendo?» y
 * es agnóstica de la polaridad (`ChannelState`, `edge/takab_edge/contracts.py`).
 *
 * `tieBreakActivated` NO es uniforme, y aplanarlo habría sido el defecto: ante
 * dos hechos indistinguibles gana **la lectura que no tranquiliza**. Para la
 * sirena eso es «sigue sonando» (T-2.110). Para el gas es exactamente lo
 * contrario — «sigue ABIERTO»—, porque afirmar sin certeza que el gas está
 * cortado es la frase que hace que nadie vaya a cerrar la válvula.
 */
export interface ActuatorChannelSpec {
  /** Canal del contrato del edge (`ActuatorChannel`). Es la identidad de la fila. */
  channel: string;
  label: string;
  /** Modo fail-safe del canal: documenta POR QUÉ `energized` no es legible sin él. */
  failSafe: 'NO' | 'NC' | 'fail_close';
  /** Vista cuando el canal ESTÁ en su estado de protección (`activated`). */
  protecting: ActionStateView;
  /** Vista cuando NO lo está. */
  atRest: ActionStateView;
  /**
   * `kind` de `incident_actions` → lo que ese VERBO afirma sobre `activated`.
   * Espejo de `ACK_KIND` (`api/src/takab_api/ingest/handlers.py`), que es el
   * único productor. `web/src/features/console/bmsChannels.test.ts` lo lee de
   * ese fichero y exige que no falte ninguno.
   */
  kinds: Record<string, boolean>;
  /**
   * Nombres que ESTE MAPA daba de alta y que ningún productor escribió nunca
   * (`gas_valve_close`, `elevator_recall`, `door_release`). Se conservan —
   * `incident_actions` es append-only y exenta de poda— para que una fila
   * antigua no regrese al fallback crudo. No se inventan más.
   */
  legacyKinds: Record<string, boolean>;
  /** Valor de `activated` que gana un empate EXACTO de `ts`. Ver arriba. */
  tieBreakActivated: boolean;
}

export const ACTUATOR_CHANNELS: Record<string, ActuatorChannelSpec> = {
  siren: {
    channel: 'siren',
    label: 'SIRENA',
    failSafe: 'NO',
    protecting: { state: 'ACTIVADA', kind: 'critical' },
    // [T-2.110] El contrario de `siren_on`, que faltaba. NO es un kind inventado
    // para poder cancelar el anterior: lo escribe el ingest desde un ACK REAL del
    // gabinete — `ACK_KIND[('siren','deactivate')] = 'siren_off'` — y la bitácora
    // del incidente ya lo rotulaba («SIRENA SILENCIADA»).
    atRest: { state: 'SILENCIADA', kind: 'ok' },
    kinds: { siren_on: true, siren_off: false },
    legacyKinds: {},
    // Una alerta en curso: minimizarla es peor que exagerarla, y es además la
    // precondición de SILENCIAR (spec móvil §2.2).
    tieBreakActivated: true,
  },
  strobe: {
    channel: 'strobe',
    label: 'ESTROBO',
    failSafe: 'NO',
    protecting: { state: 'ACTIVADO', kind: 'warning' },
    atRest: { state: 'APAGADO', kind: 'ok' },
    kinds: { strobe_on: true, strobe_off: false },
    legacyKinds: {},
    tieBreakActivated: true, // misma doctrina que la sirena: el aviso sigue vivo
  },
  gas_valve: {
    channel: 'gas_valve',
    label: 'VÁLVULAS DE GAS',
    failSafe: 'fail_close',
    protecting: { state: 'CERRADAS', kind: 'warning' },
    atRest: { state: 'ABIERTAS', kind: 'ok' },
    kinds: { gas_closed: true, gas_open: false },
    legacyKinds: { gas_valve_close: true },
    // INVERTIDO respecto a la sirena, a propósito: la lectura que no tranquiliza
    // es «el gas SIGUE ABIERTO». Decir «CERRADAS» sin certeza manda a nadie a
    // cerrar la válvula.
    tieBreakActivated: false,
  },
  elevator: {
    channel: 'elevator',
    label: 'ELEVADORES',
    failSafe: 'NO',
    protecting: { state: 'RETORNADOS', kind: 'warning' },
    atRest: { state: 'LIBERADOS', kind: 'ok' },
    kinds: { elevator_recalled: true, elevator_released: false },
    legacyKinds: { elevator_recall: true },
    // Igual que el gas: «no retornados» significa que puede haber gente en una
    // cabina, y es lo que hay que ir a comprobar.
    tieBreakActivated: false,
  },
  door_retainer: {
    channel: 'door_retainer',
    label: 'RETENEDORES DE PUERTA',
    failSafe: 'NC',
    protecting: { state: 'LIBERADOS', kind: 'ok' },
    atRest: { state: 'RETENIDOS', kind: 'ok' },
    kinds: { door_released: true, door_retained: false },
    legacyKinds: { door_release: true },
    // La lectura que no tranquiliza es «la puerta SIGUE retenida»: la salida no
    // está garantizada mientras no conste que se liberó.
    tieBreakActivated: false,
  },
};

/** `kind` → canal que lo emitió. Derivado del registro, nunca escrito a mano. */
const CHANNEL_OF_KIND: Record<string, ActuatorChannelSpec> = {};
for (const spec of Object.values(ACTUATOR_CHANNELS)) {
  for (const kind of [...Object.keys(spec.kinds), ...Object.keys(spec.legacyKinds)]) {
    CHANNEL_OF_KIND[kind] = spec;
  }
}

/** ¿Qué afirma este VERBO sobre `activated`? `undefined` = no es de actuador. */
function verbSaysActivated(kind: string): boolean | undefined {
  const spec = CHANNEL_OF_KIND[kind];
  if (spec === undefined) {
    return undefined;
  }
  return kind in spec.kinds ? spec.kinds[kind] : spec.legacyKinds[kind];
}

/** Vistas de los kinds de actuador, DERIVADAS del registro (no duplicadas). */
function actuatorViews(): Record<string, ActionStateView> {
  const views: Record<string, ActionStateView> = {};
  for (const [kind, spec] of Object.entries(CHANNEL_OF_KIND)) {
    views[kind] = verbSaysActivated(kind) === true ? spec.protecting : spec.atRest;
  }
  return views;
}

/**
 * Mapeo kind→estado visual (se comparte con la traza expandida).
 *
 * Es lo que ese VERBO afirma por sí solo. El estado de una FILA del checklist
 * no sale de aquí cuando el gabinete declara el relé: sale de `groupActions`,
 * que prefiere `payload.channel_state`.
 */
export const ACTION_STATE: Record<string, ActionStateView> = {
  ...actuatorViews(),
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
  // [T-2.133] EL CUARTO VERBO, que faltaba. `T-2.109` lo añadió al orquestador
  // —el proveedor existe y entrega, pero en ese inmueble no hay UN SOLO teléfono
  // registrado al que despertar— y ninguna superficie lo rotulaba: el checklist
  // lo pintaba «NOTIFY_NO_RECIPIENTS» y, lo grave, con `kind: 'ok'` — VERDE, la
  // misma mentira que `T-2.75` cerró para los otros tres.
  //
  // `warning` y no `critical`, con la misma doctrina que `SIMULATED_VIEW`: no hay
  // avería que atender ni a quién reintentar, hay teléfonos que registrar con su
  // inmueble. Lo que NO puede ser es verde.
  notify_no_recipients: { state: 'SIN DESTINATARIOS', kind: 'warning' },
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

/** Etiquetas de los kinds de actuador, DERIVADAS del registro. */
function actuatorLabels(): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const [kind, spec] of Object.entries(CHANNEL_OF_KIND)) {
    labels[kind] = spec.label;
  }
  return labels;
}

/** Etiqueta humana por canal/acción (fallback: el kind crudo en mayúsculas). */
export const CHANNEL_LABEL: Record<string, string> = {
  ...actuatorLabels(),
  ack: 'ACUSES',
  dictamen: 'DICTAMEN AUTOMÁTICO',
  dictamen_request: 'DICTAMEN SOLICITADO',
  epicenter_relocate: 'EPICENTRO',
  notify_sent: 'NOTIFICACIONES',
  notify_simulated: 'NOTIFICACIONES SIMULADAS',
  notify_failed: 'NOTIFICACIONES NO ENTREGADAS',
  notify_no_recipients: 'NOTIFICACIONES SIN DESTINATARIOS',
};

/*
 * [T-2.133] `siren_test` SE RETIRÓ DE LOS DOS MAPAS DE ARRIBA. La razón, escrita
 * para que nadie lo devuelva "por si acaso":
 *
 * Vivía aquí desde `T-1.50` con vista («PROBADA») y rótulo («PRUEBA DE SIRENA»),
 * y **ningún productor escribe jamás ese `kind` en `incident_actions`**. Medido
 * sobre los ocho ficheros de `api/src` que insertan en la tabla —el censo lo
 * deriva `web/src/test-utils/incidentActionKinds.ts` y lo exige
 * `bmsChannels.test.ts`—:
 *
 *   · en `api/src` `siren_test` sólo existe como **acción de la matriz RBAC**
 *     (`allowed_actions.siren_test`, el permiso para mandar comandos de
 *     actuador) y como verbo de `audit_log`, nunca como `kind`;
 *   · en el edge es la prueba LOCAL del panel LAN
 *     (`local_api::run_siren_test` → `_record_action("siren_test")`), que se
 *     queda en un **deque en RAM del gabinete** —lo borra un reinicio— y no sube
 *     a la nube;
 *   · el `command_ack` de esa prueba tampoco puede llegar: `handle_command_ack`
 *     toca `commands` y `audit_log`, **jamás `incident_actions`**; y `ACK_KIND`
 *     sólo mapea `activate`/`deactivate`, así que un `self_test` ni siquiera
 *     tiene `kind` (el ingest lo rechaza con «(channel, action) sin mapeo»).
 *
 * NO se conserva como `legacyKind`, y la diferencia con `gas_valve_close`,
 * `elevator_recall` y `door_release` importa: aquéllos son nombres de CANAL, y
 * el registro tiene que poder rotular una fila antigua de un canal. `siren_test`
 * no pertenece a ningún canal —`T-2.119` lo dejó fuera del canal `siren` a
 * propósito, para que una prueba no cancelara ni sostuviera la fila de una
 * alerta real—, así que conservarlo no protege ninguna fila: protege una
 * hipótesis. Si algún día se decide subir la prueba de sirena a la nube, el
 * `kind` se da de alta **junto con su productor**, no antes.
 *
 * La guardia que impide que vuelva —y que caza al siguiente— es el censo inverso
 * de `web/src/features/console/bmsChannels.test.ts`: todo kind de estos dos mapas
 * tiene que tener quien lo escriba en `api/src`.
 */

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

/**
 * Lo que se sabe de UN canal de actuación, y DE DÓNDE se sabe.
 *
 * La forma es EXACTAMENTE `{active, fromRelay, at}` y no lleva el canal: móvil
 * la compara con `toEqual` (`mobile/src/features/control/estadoDelRele.test.tsx`),
 * y una clave de más la pondría en rojo. Quien pregunta ya sabe por qué canal
 * preguntó.
 */
export interface ChannelEvidence {
  /** ¿El canal está en su estado de PROTECCIÓN? (sonando, gas cerrado, puerta liberada) */
  active: boolean;
  /** `true` = lo declara el RELÉ recalculado; `false` = sólo la última orden. */
  fromRelay: boolean;
  /** Momento de la evidencia (ts de la acción). */
  at: string;
}

/** [T-2.110] Alias histórico: la evidencia de la sirena es la de cualquier canal. */
export type SirenEvidence = ChannelEvidence;

function channelStateOf(action: IncidentActionOut, channel: string): ChannelState | null {
  const raw = action.payload?.channel_state;
  if (raw === null || typeof raw !== 'object') {
    // `channel_state: null` es «no pude preguntar» (firmware viejo, BACnet, ack
    // de rechazo), JAMÁS «en reposo». Devolver null aquí degrada al verbo — y
    // quien lo consuma se entera por `fromRelay: false`, no por un `false`
    // indistinguible de una medición.
    return null;
  }
  const state = raw as Partial<ChannelState>;
  // El censo de OTRO canal no decide por éste.
  return typeof state.activated === 'boolean' && state.channel === channel
    ? (state as ChannelState)
    : null;
}

/**
 * [T-2.110 · generalizada en T-2.119] ¿Este canal está protegiendo, según el
 * ÚLTIMO dato real del gabinete?
 *
 * `null` = no consta ninguna actuación del canal en la traza. Es un tercer
 * estado a propósito: «no lo sé» no es «está en reposo», y afirmar cualquiera
 * de las dos sin dato es la regla de oro 7 al revés.
 *
 * PRECEDENCIA, y es el corazón de la ficha:
 *
 *  1. `payload.channel_state` — el estado RECALCULADO del relé. Es lo que la
 *     spec §2.1 pide pintar: «el estado del relé recalculado por el arbitraje
 *     de demandas, **no la última orden enviada**». Se lee `activated`, nunca
 *     `energized`: en `gas_valve` (FAIL_CLOSE) y `door_retainer` (NC) el nivel
 *     eléctrico significa lo contrario que en la sirena.
 *  2. el `kind` (`gas_closed`/`gas_open`, …) — la ORDEN que se ejecutó. Es lo
 *     único que hay de un gabinete que aún no declara (1), y NO es equivalente:
 *     un `siren/deactivate` con la alerta vigente se ejecuta con éxito, escribe
 *     `siren_off` y deja la sirena sonando. Por eso (1) manda siempre que exista.
 *
 * Se descartan las acciones SIMULADAS (T-2.75.a): lo que no se ejecutó no puede
 * sostener ni desmentir el estado del canal.
 *
 * Empate exacto de `ts`: gana `spec.tieBreakActivated` — la lectura que NO
 * tranquiliza, que en la sirena es «sonando» y en el gas es «abierto».
 */
export function channelEvidence(
  actions: IncidentActionOut[],
  channel: string,
): ChannelEvidence | null {
  const spec = ACTUATOR_CHANNELS[channel];
  if (spec === undefined) {
    return null;
  }
  let mejor: ChannelEvidence | null = null;
  for (const action of actions) {
    const verbo = verbSaysActivated(action.kind);
    if (verbo === undefined || CHANNEL_OF_KIND[action.kind] !== spec || isSimulatedAction(action)) {
      continue;
    }
    const state = channelStateOf(action, channel);
    const evidencia: ChannelEvidence = {
      active: state !== null ? state.activated : verbo,
      fromRelay: state !== null,
      at: action.ts,
    };
    if (mejor === null) {
      mejor = evidencia;
      continue;
    }
    const delta = Date.parse(evidencia.at) - Date.parse(mejor.at);
    const desempata =
      delta === 0 &&
      evidencia.active === spec.tieBreakActivated &&
      mejor.active !== spec.tieBreakActivated;
    if (delta > 0 || desempata) {
      mejor = evidencia;
    }
  }
  return mejor;
}

/**
 * [T-2.110] ¿La sirena está sonando, según el ÚLTIMO dato real del gabinete?
 * Es `channelEvidence(_, 'siren')` — no una quinta copia que pueda derivar.
 */
export function sirenEvidence(actions: IncidentActionOut[]): SirenEvidence | null {
  return channelEvidence(actions, 'siren');
}

export interface ActuatorGroup {
  /**
   * [T-2.119] Identidad ESTABLE de la fila: el CANAL del actuador
   * (`siren`, `gas_valve`, …) o, si no es de actuador, el propio `kind`. Es lo
   * que hace que `gas_open` cancele la fila de `gas_closed` en vez de abrir
   * otra: dos órdenes del mismo canal son una sola fila con un solo estado.
   */
  id: string;
  /**
   * `kind` de la acción MÁS RECIENTE del grupo. Para un grupo de un solo verbo
   * es lo de siempre; para un canal es el último verbo ejecutado — que NO es el
   * estado (por eso existe `view`, que sale de `evidence`).
   */
  kind: string;
  label: string;
  view: ActionStateView;
  /** Acción MÁS RECIENTE del grupo (define estado, hora y actor mostrados). */
  last: IncidentActionOut;
  count: number;
  /** Traza completa del grupo, más reciente primero (auditoría expandible). */
  trace: IncidentActionOut[];
  /**
   * [T-2.119] Qué se sabe del canal y DE DÓNDE. `null` = el grupo no es de
   * actuador, o no consta ninguna actuación real (todas simuladas). La UI
   * DEBE declarar `fromRelay`: pintar la orden como si fuera el relé es
   * exactamente el defecto que esta ficha cierra.
   */
  evidence: ChannelEvidence | null;
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
 * Agrupa la traza por CANAL de actuación (y por `kind` lo que no es actuador):
 * una fila por actuador con su ESTADO, no con su última orden. Orden: grupos
 * por recencia de su última acción (lo más nuevo arriba); dentro del grupo la
 * traza también va de más nueva a más vieja.
 *
 * [T-2.119] Agrupaba por `kind` a secas, así que `gas_open` abría una fila
 * propia y no cancelaba la de `gas_closed`: el checklist mostraba las dos
 * órdenes y la más reciente ganaba por hora, con la palabra cruda
 * («GAS_OPEN», en verde) porque esos kinds ni siquiera estaban dados de alta.
 * Ahora la fila es el canal y su estado sale de `channelEvidence`, que prefiere
 * el relé recalculado y sólo cae al verbo cuando el gabinete no lo declara.
 */
export function groupActions(actions: IncidentActionOut[]): ActuatorGroup[] {
  const byId = new Map<string, IncidentActionOut[]>();
  for (const action of actions) {
    const id = CHANNEL_OF_KIND[action.kind]?.channel ?? action.kind;
    const list = byId.get(id) ?? [];
    list.push(action);
    byId.set(id, list);
  }
  const groups: ActuatorGroup[] = [];
  for (const [id, list] of byId) {
    const trace = [...list].sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
    const spec = ACTUATOR_CHANNELS[id];
    const evidence = spec === undefined ? null : channelEvidence(list, spec.channel);
    groups.push({
      id,
      kind: trace[0].kind,
      label: spec?.label ?? labelOf(trace[0].kind),
      // Sin evidencia real (no es actuador, o todo lo del canal es SIMULADO) se
      // cae a la vista de la acción más reciente, que es quien sabe declararse
      // simulada. Con evidencia manda el canal, no el verbo.
      view:
        spec !== undefined && evidence !== null
          ? evidence.active
            ? spec.protecting
            : spec.atRest
          : viewOf(trace[0]),
      last: trace[0],
      count: trace.length,
      trace,
      evidence,
    });
  }
  return groups.sort((a, b) => Date.parse(b.last.ts) - Date.parse(a.last.ts));
}
