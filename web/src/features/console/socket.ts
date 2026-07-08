// Contexto del canal live de la consola (T-1.27).
//
// ConsolePage crea UN LiveSocket por sesión y lo publica aquí; los hooks lo
// consumen por esta superficie mínima (fácil de stubear en tests). Un contexto
// null degrada a solo-REST: la consola sigue pintando con el poll de respaldo
// (regla de oro 2: la nube coordina, pero nada muere por perder el live).

import { createContext, useContext } from "react";

import type { ServerFrame } from "@takab/sdk";

import type { LiveStatus } from "../../lib/ws";

export interface LiveSocketLike {
  subscribe(topic: string, listener: (frame: ServerFrame) => void): () => void;
  lastFrameAt(topic: string): number | null;
  readonly status: LiveStatus;
  onStatus(listener: (status: LiveStatus) => void): () => void;
}

export const LiveSocketContext = createContext<LiveSocketLike | null>(null);

/** Socket live del árbol actual, o null si la consola corre solo-REST. */
export function useLiveSocket(): LiveSocketLike | null {
  return useContext(LiveSocketContext);
}
