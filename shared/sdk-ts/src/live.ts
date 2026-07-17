// Cliente WS live COMPARTIDO (T-2.08 — extraído de web/src/lib/ws.ts sin
// cambio de conducta): auth-first-frame → ready → subscribe(topic, cb);
// reconexión con backoff exponencial + jitter (1 s..30 s) y RE-subscribe al
// reabrir; close 4401 ⇒ onUnauthorized (sesión inválida — la app decide);
// staleness por topic vía lastFrameAt. Corre en navegador Y React Native
// (ambos exponen WebSocket global); los shapes de los frames vienen de
// ./ws (generados de ws/protocol.py) — aquí NO se inventan.

import {
  authFrame,
  parseServerFrame,
  serializeFrame,
  subscribeFrame,
  TOPIC_INCIDENTS,
  TOPIC_SITE_STATE,
  featuresTopic,
  type ServerFrame,
} from './ws';

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
  /** Base del backoff exponencial (default 1 s). */
  backoffBaseMs?: number;
  /** Tope del backoff (default 30 s). */
  backoffMaxMs?: number;
}

const WS_AUTH_FAILED = 4401;
const DEFAULT_BACKOFF_BASE_MS = 1_000;
const DEFAULT_BACKOFF_MAX_MS = 30_000;

/** Topic del suscriptor al que pertenece un frame de datos (espejo del hub). */
function topicOf(frame: ServerFrame): string | null {
  switch (frame.type) {
    case 'incident':
    case 'incident_action':
    case 'roster':
      return TOPIC_INCIDENTS;
    case 'site_state':
      return TOPIC_SITE_STATE;
    case 'features':
      return featuresTopic(String(frame.site_id));
    default:
      return null; // ready/error: protocolo, no datos
  }
}

export class LiveSocket {
  private readonly options: Required<Omit<LiveSocketOptions, 'backoffBaseMs' | 'backoffMaxMs'>> & {
    backoffBaseMs: number;
    backoffMaxMs: number;
  };

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
   *  Devuelve la función de baja (solo local: el protocolo no tiene unsubscribe). */
  subscribe(topic: string, listener: FrameListener): () => void {
    const isNewTopic = !this.listeners.has(topic);
    const set = this.listeners.get(topic) ?? new Set<FrameListener>();
    set.add(listener);
    this.listeners.set(topic, set);
    if (isNewTopic && this.currentStatus === 'ready') {
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
    } catch {
      return; // frame desconocido/corrupto: se ignora (forward-compat)
    }
    if (frame.type === 'ready') {
      this.attempt = 0;
      this.setStatus('ready');
      for (const topic of this.listeners.keys()) {
        this.send(serializeFrame(subscribeFrame(topic)));
      }
      return;
    }
    if (frame.type === 'error') return; // error de protocolo: no cierra el socket
    const topic = topicOf(frame);
    if (topic === null) return;
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
