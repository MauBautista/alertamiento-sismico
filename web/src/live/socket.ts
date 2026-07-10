// Superficie del canal live COMPARTIDO por el shell (T-1.49).
//
// LiveSocketLike/LiveSocketContext nacieron en features/console/socket.ts
// (T-1.27) cuando cada página poseía su socket. Ahora el dueño es AppShell
// (la topbar necesita estado de conexión y latencia MQTT en TODAS las
// páginas), así que la superficie vive aquí; el archivo original queda como
// re-export para que ningún hook consumidor cambie. Un contexto null degrada
// a solo-REST (regla de oro 2: nada muere por perder el live).

import { createContext, useContext } from "react";

import type { ServerFrame } from "@takab/sdk";

import type { LiveStatus } from "../lib/ws";

export interface LiveSocketLike {
  subscribe(topic: string, listener: (frame: ServerFrame) => void): () => void;
  lastFrameAt(topic: string): number | null;
  readonly status: LiveStatus;
  onStatus(listener: (status: LiveStatus) => void): () => void;
}

/** Lo que el provider necesita además de la superficie de lectura. */
export interface ConnectableLiveSocket extends LiveSocketLike {
  connect(): void;
  close(): void;
}

export const LiveSocketContext = createContext<LiveSocketLike | null>(null);

/** Socket live del árbol actual, o null si la app corre solo-REST. */
export function useLiveSocket(): LiveSocketLike | null {
  return useContext(LiveSocketContext);
}

/** Fábrica inyectable SOLO para tests (renderRoutes): sin ella, montar
 * AppShell con sesión sembrada abriría un WebSocket REAL de jsdom con timers
 * de reconexión colgando entre tests. */
export const LiveSocketFactoryContext = createContext<(() => ConnectableLiveSocket) | null>(null);
