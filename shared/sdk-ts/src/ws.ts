// Cliente tipado del canal WebSocket /ws (T-1.22 · gate #5).
//
// Los tipos de cada frame los genera el OpenAPI (src/gen/types.gen.ts a partir de
// ws/protocol.py). Aqui va SOLO lo que no cabe en el contrato REST: el parser que
// estrecha el frame entrante por su discriminante `type` y los builders de los
// frames que el cliente manda (auth/subscribe).

import type {
  AuthFrame,
  ErrorFrame,
  FeaturesFrame,
  IncidentActionFrame,
  IncidentFrame,
  ReadyFrame,
  SiteStateFrame,
  SubscribeFrame,
} from './gen';

// Union de todo lo que el servidor puede empujar al cliente.
export type ServerFrame =
  | ReadyFrame
  | ErrorFrame
  | IncidentFrame
  | IncidentActionFrame
  | SiteStateFrame
  | FeaturesFrame;

// Discriminantes validos (el servidor siempre setea `type`).
export type ServerFrameType = NonNullable<ServerFrame['type']>;

const SERVER_FRAME_TYPES: ReadonlySet<string> = new Set<ServerFrameType>([
  'ready',
  'error',
  'incident',
  'incident_action',
  'site_state',
  'features',
]);

// Topics de suscripcion.
export const TOPIC_INCIDENTS = 'incidents';
export const TOPIC_SITE_STATE = 'site_state';

/** Topic de features de un sitio: `features:<site_id>`. */
export function featuresTopic(siteId: string): string {
  return `features:${siteId}`;
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
