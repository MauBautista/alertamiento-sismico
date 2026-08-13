// Cliente tipado del canal WebSocket /ws (T-1.22 · gate #5).
//
// Los tipos de cada frame los genera el OpenAPI (src/gen/types.gen.ts a partir de
// ws/protocol.py). Aqui va SOLO lo que no cabe en el contrato REST: el parser que
// estrecha el frame entrante por su discriminante `type`, LA TABLA DE RUTAS de
// esos frames y los builders de los frames que el cliente manda (auth/subscribe).
//
// [T-2.129] LA LISTA DE `type` VÁLIDOS YA NO SE ESCRIBE: SE DERIVA.
//
// Aquí había un `Set` a mano con siete cadenas y, en `live.ts`, un `switch` con
// `default: return null`. Entre los dos hacían que cualquier frame que el
// servidor aprendiera a mandar **desapareciera en silencio** — y esa es la razón
// de que `T-2.121` tuviera que decir «tu live está degradado» CERRANDO EL SOCKET:
// no había otro canal servidor→pantalla que el estado del transporte.
//
// La cura es que el censo y la ruta sean LA MISMA tabla:
//
//   · `SERVER_FRAME_ROUTES` es `Record<ServerFrameType, …>`, así que un miembro
//     nuevo de la unión `ServerFrame` que no declare su ruta **no compila**;
//   · `SERVER_FRAME_TYPES` se deriva de sus claves (no hay dónde divergir);
//   · y `web/src/serverFrameCensus.test.ts` lee `ws/protocol.py` —el productor—
//     y exige que todo frame servidor→cliente de allí tenga su ruta aquí.
//
// El precedente es `bms.ts`, cuyo censo lee `ACK_KIND` del propio ingest: la
// lista que se deriva no puede divergir; la escrita a mano siempre acaba
// divergiendo.

import type {
  AuthFrame,
  ErrorFrame,
  FeaturesFrame,
  IncidentActionFrame,
  IncidentFrame,
  LiveHealthFrame,
  ReadyFrame,
  RosterSignalFrame,
  SiteStateFrame,
  SubscribeFrame,
} from './gen';

/**
 * Campos del espejo, EN TIEMPO DE EJECUCIÓN. `Record<keyof …, true>` obliga a
 * `tsc` a exigirlos todos y a rechazar los de más, y el censo los compara con
 * los del modelo Pydantic. Sin esto, el espejo podría quedarse corto en silencio.
 */
export const LIVE_HEALTH_FIELDS: Record<keyof LiveHealthFrame, true> = {
  type: true,
  degraded: true,
  topic: true,
  detail: true,
};

// Union de todo lo que el servidor puede empujar al cliente.
export type ServerFrame =
  | ReadyFrame
  | ErrorFrame
  | LiveHealthFrame
  | IncidentFrame
  | IncidentActionFrame
  | SiteStateFrame
  | FeaturesFrame
  | RosterSignalFrame;

// Discriminantes validos (el servidor siempre setea `type`).
export type ServerFrameType = NonNullable<ServerFrame['type']>;

// Topics de suscripcion.
export const TOPIC_INCIDENTS = 'incidents';
export const TOPIC_SITE_STATE = 'site_state';

/**
 * [T-2.129] Topic LOCAL de la salud del canal. No se suscribe en el servidor: el
 * `live_health` es un frame que el hub dirige a ESE socket cuando le pasa algo,
 * no un flujo al que uno se apunta. `LiveSocket` lo reparte igual que un topic
 * de datos —de ahí que valga la pena que sea uno— pero sin mandar el
 * `{"type":"subscribe"}`, que el servidor rechazaría con «topic inválido».
 */
export const TOPIC_LIVE_HEALTH = 'live_health';

/** Topics que NUNCA viajan al servidor en un `subscribe` (ver arriba). */
export const LOCAL_TOPICS: ReadonlySet<string> = new Set<string>([TOPIC_LIVE_HEALTH]);

/** Topic de features de un sitio: `features:<site_id>`. */
export function featuresTopic(siteId: string): string {
  return `features:${siteId}`;
}

/**
 * Ruta de un frame servidor→cliente: el topic al que se reparte, o `'protocol'`
 * si lo consume el propio `LiveSocket` (handshake y salud del canal no son datos
 * de ningún topic de negocio).
 */
export type FrameRoute = 'protocol' | ((frame: ServerFrame) => string);

/**
 * LA TABLA. Es `Record<ServerFrameType, …>` a propósito: añadir un miembro a la
 * unión `ServerFrame` sin darle ruta aquí es un error de compilación, no un
 * frame que se cae por el `default` de un `switch`.
 */
export const SERVER_FRAME_ROUTES: Record<ServerFrameType, FrameRoute> = {
  ready: 'protocol',
  error: 'protocol',
  live_health: () => TOPIC_LIVE_HEALTH,
  incident: () => TOPIC_INCIDENTS,
  incident_action: () => TOPIC_INCIDENTS,
  roster: () => TOPIC_INCIDENTS,
  site_state: () => TOPIC_SITE_STATE,
  features: (frame) => featuresTopic(String((frame as FeaturesFrame).site_id)),
};

/** Discriminantes válidos, DERIVADOS de la tabla de rutas. */
export const SERVER_FRAME_TYPES: ReadonlySet<string> = new Set(Object.keys(SERVER_FRAME_ROUTES));

/**
 * Topic del suscriptor al que pertenece un frame; `null` = frame de PROTOCOLO.
 *
 * `null` ya no significa «no lo conozco» (eso lo rechaza `parseServerFrame`):
 * significa exactamente «lo maneja `LiveSocket`». La diferencia importa —
 * `live.ts` deja rastro de un `'protocol'` que no sepa manejar en vez de
 * tragárselo.
 */
export function topicOfFrame(frame: ServerFrame): string | null {
  const route = SERVER_FRAME_ROUTES[frame.type as ServerFrameType];
  if (route === undefined) {
    // Inalcanzable por `handleMessage` (parsea antes), pero `topicOfFrame` es
    // público: quien lo llame con un frame sin ruta merece el nombre del
    // culpable y no un «route is not a function» a 40 líneas de distancia.
    throw new Error(`marco WS sin ruta declarada: ${String(frame.type)}`);
  }
  return route === 'protocol' ? null : route(frame);
}

/** Primer frame obligatorio del handshake: autentica el socket con el ID token. */
export function authFrame(token: string): AuthFrame {
  return { type: 'auth', token };
}

/** Alta a un topic (`incidents` | `site_state` | `features:<site_id>`). */
export function subscribeFrame(topic: string): SubscribeFrame {
  return { type: 'subscribe', topic };
}

/** Serializa un frame de cliente a texto para `WebSocket.send`. */
export function serializeFrame(frame: AuthFrame | SubscribeFrame): string {
  return JSON.stringify(frame);
}

/**
 * Parsea y estrecha un frame entrante del servidor. Acepta el texto crudo del
 * `message` o un objeto ya deserializado. Lanza si falta o no reconoce `type`.
 */
export function parseServerFrame(data: string | Record<string, unknown>): ServerFrame {
  const obj: unknown = typeof data === 'string' ? JSON.parse(data) : data;
  if (obj === null || typeof obj !== 'object') {
    throw new Error('marco WS invalido: no es un objeto');
  }
  const type = (obj as { type?: unknown }).type;
  if (typeof type !== 'string' || !SERVER_FRAME_TYPES.has(type)) {
    throw new Error(`marco WS desconocido: ${String(type)}`);
  }
  return obj as ServerFrame;
}

/** True si el frame es del tipo dado (estrecha la union). */
export function isServerFrame<T extends ServerFrameType>(
  frame: ServerFrame,
  type: T,
): frame is Extract<ServerFrame, { type?: T }> {
  return frame.type === type;
}
