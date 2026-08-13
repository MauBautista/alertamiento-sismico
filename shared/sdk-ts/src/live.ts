// Cliente WS live COMPARTIDO (T-2.08 — extraído de web/src/lib/ws.ts sin
// cambio de conducta): auth-first-frame → ready → subscribe(topic, cb);
// reconexión con backoff exponencial + jitter (1 s..30 s) y RE-subscribe al
// reabrir; close 4401 ⇒ onUnauthorized (sesión inválida — la app decide);
// staleness por topic vía lastFrameAt. Corre en navegador Y React Native
// (ambos exponen WebSocket global); los shapes de los frames vienen de
// ./ws (generados de ws/protocol.py) — aquí NO se inventan.
//
// [T-2.129] AQUÍ ESTABA EL AGUJERO, y no era «falta un tipo de frame».
//
// Este fichero tenía TRES desagües silenciosos: un `catch {}` que se tragaba
// todo lo que `parseServerFrame` no reconocía, un `if (frame.type === 'error')
// return` que borraba los errores de protocolo del servidor, y un `switch` con
// `default: return null`. Consecuencia: el ÚNICO canal servidor→pantalla era el
// estado del transporte, y por eso `T-2.121` tuvo que declarar la degradación
// **cerrando el socket** (4503) — el equivalente a arrancar el teléfono de la
// pared para avisar de que hay ruido en la línea.
//
// Ahora ningún camino termina en silencio: se reparte, o se avisa. La ruta sale
// de `SERVER_FRAME_ROUTES` (una tabla exhaustiva sobre la unión, en `./ws`), y
// lo que no encaje llama a `onUnknownFrame` — cuyo default escribe en consola,
// porque el defecto que cierra esta ficha es precisamente que nadie se enteraba.

import {
  authFrame,
  LOCAL_TOPICS,
  parseServerFrame,
  serializeFrame,
  subscribeFrame,
  topicOfFrame,
  type ServerFrame,
} from './ws';
import type { ErrorFrame } from './gen';

export type LiveStatus = 'connecting' | 'ready' | 'closed';
export type FrameListener = (frame: ServerFrame) => void;
export type StatusListener = (status: LiveStatus) => void;

export interface LiveSocketOptions {
  /** URL absoluta ws(s)://…/ws (la construye cada plataforma). */
  url: string;
  /** ID token vivo de la sesión; se lee EN CADA conexión (tokens renovados). */
  getToken: () => string | null;
  /** El servidor cerró con 4401 (token inválido/expirado): NO se reintenta. */
  onUnauthorized: () => void;
  /**
   * [T-2.129] Llegó algo que este cliente no sabe repartir: `type` desconocido
   * (servidor más nuevo), JSON corrupto, o un frame de protocolo sin manejador.
   * El default lo escribe en consola. NO lanza: un frame del futuro no puede
   * tumbar el canal — pero tampoco puede desaparecer sin dejar rastro, que es
   * exactamente como este cliente llevaba desde T-1.22.
   */
  onUnknownFrame?: (raw: string, reason: Error) => void;
  /**
   * [T-2.129] Error de PROTOCOLO del servidor (`ErrorFrame`: topic inválido,
   * JSON malo, rol sin acceso al topic). No cierra el socket y antes se
   * descartaba entero: una suscripción denegada se veía igual que una concedida
   * a la que nadie manda nada. El default lo escribe en consola.
   */
  onServerError?: (frame: ErrorFrame) => void;
  /** Base del backoff exponencial (default 1 s). */
  backoffBaseMs?: number;
  /** Tope del backoff (default 30 s). */
  backoffMaxMs?: number;
}

const WS_AUTH_FAILED = 4401;
const DEFAULT_BACKOFF_BASE_MS = 1_000;
const DEFAULT_BACKOFF_MAX_MS = 30_000;

function defaultOnUnknownFrame(raw: string, reason: Error): void {
  console.warn(`[takab/live] frame WS sin repartir: ${reason.message}`, raw.slice(0, 200));
}

function defaultOnServerError(frame: ErrorFrame): void {
  console.warn(`[takab/live] error de protocolo del servidor: ${frame.detail}`);
}

export class LiveSocket {
  private readonly options: Required<LiveSocketOptions>;

  private ws: WebSocket | null = null;
  private currentStatus: LiveStatus = 'closed';
  private readonly listeners = new Map<string, Set<FrameListener>>();
  private readonly lastFrame = new Map<string, number>();
  private readonly statusListeners = new Set<StatusListener>();
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;

  constructor(options: LiveSocketOptions) {
    this.options = {
      backoffBaseMs: DEFAULT_BACKOFF_BASE_MS,
      backoffMaxMs: DEFAULT_BACKOFF_MAX_MS,
      onUnknownFrame: defaultOnUnknownFrame,
      onServerError: defaultOnServerError,
      ...options,
    };
  }

  get status(): LiveStatus {
    return this.currentStatus;
  }

  /** Momento (epoch ms) del último frame de datos del topic, o null si no hubo. */
  lastFrameAt(topic: string): number | null {
    return this.lastFrame.get(topic) ?? null;
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  /** Alta de un listener; manda el subscribe si el socket ya está ready.
   *  Devuelve la función de baja (solo local: el protocolo no tiene unsubscribe).
   *
   *  [T-2.129] Los `LOCAL_TOPICS` (hoy `live_health`) NO viajan al servidor: son
   *  frames que el hub dirige a este socket por iniciativa propia. Mandar su
   *  `subscribe` sólo conseguiría un `ErrorFrame` de «topic inválido». */
  subscribe(topic: string, listener: FrameListener): () => void {
    const isNewTopic = !this.listeners.has(topic);
    const set = this.listeners.get(topic) ?? new Set<FrameListener>();
    set.add(listener);
    this.listeners.set(topic, set);
    if (isNewTopic && this.currentStatus === 'ready' && !LOCAL_TOPICS.has(topic)) {
      this.send(serializeFrame(subscribeFrame(topic)));
    }
    return () => {
      set.delete(listener);
      if (set.size === 0) this.listeners.delete(topic);
    };
  }

  connect(): void {
    if (this.ws !== null) return;
    this.closedByUser = false;
    this.openSocket();
  }

  /** Cierre intencional: sin reconexión. */
  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const ws = this.ws;
    this.ws = null;
    if (ws !== null && ws.readyState !== WebSocket.CLOSED) ws.close();
    this.setStatus('closed');
  }

  // ------------------------------------------------------------- internos

  private openSocket(): void {
    const token = this.options.getToken();
    if (token === null) {
      this.setStatus('closed');
      this.options.onUnauthorized();
      return;
    }
    this.setStatus('connecting');
    const ws = new WebSocket(this.options.url);
    this.ws = ws;
    ws.onopen = () => {
      ws.send(serializeFrame(authFrame(token)));
    };
    ws.onmessage = (event: { data: string }) => this.handleMessage(event.data);
    ws.onclose = (event: { code: number }) => this.handleClose(ws, event.code);
  }

  private handleMessage(data: string): void {
    let frame: ServerFrame;
    try {
      frame = parseServerFrame(data);
    } catch (reason) {
      // Forward-compat: no se lanza (un frame del futuro no tumba el canal),
      // pero SÍ deja rastro. Tragárselo era el defecto de T-2.129.
      const causa = reason instanceof Error ? reason : new Error(String(reason));
      this.options.onUnknownFrame(data, causa);
      return;
    }
    if (frame.type === 'ready') {
      this.attempt = 0;
      this.setStatus('ready');
      for (const topic of this.listeners.keys()) {
        if (!LOCAL_TOPICS.has(topic)) {
          this.send(serializeFrame(subscribeFrame(topic)));
        }
      }
      return;
    }
    if (frame.type === 'error') {
      this.options.onServerError(frame as ErrorFrame); // no cierra el socket
      return;
    }
    const topic = topicOfFrame(frame);
    if (topic === null) {
      // Un frame de PROTOCOLO que este cliente no maneja. Sólo puede pasar con
      // un servidor más nuevo; sin este aviso volvería a caer en el descarte
      // silencioso por la puerta de al lado.
      this.options.onUnknownFrame(
        data,
        new Error(`frame de protocolo sin manejador: ${String(frame.type)}`),
      );
      return;
    }
    this.lastFrame.set(topic, Date.now());
    for (const listener of this.listeners.get(topic) ?? []) {
      listener(frame);
    }
  }

  private handleClose(ws: WebSocket, code: number): void {
    if (this.ws !== ws) return; // cierre de un socket ya reemplazado
    this.ws = null;
    if (this.closedByUser) return; // close() ya fijó el estado
    if (code === WS_AUTH_FAILED) {
      this.setStatus('closed');
      this.options.onUnauthorized();
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    this.setStatus('connecting');
    const delay = Math.min(this.options.backoffBaseMs * 2 ** this.attempt, this.options.backoffMaxMs);
    const jitter = delay * 0.1 * Math.random(); // rompe rebaños tras un corte regional
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay + jitter);
  }

  private send(payload: string): void {
    if (this.ws !== null && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(payload);
    }
  }

  private setStatus(status: LiveStatus): void {
    if (status === this.currentStatus) return;
    this.currentStatus = status;
    for (const listener of this.statusListeners) {
      listener(status);
    }
  }
}
