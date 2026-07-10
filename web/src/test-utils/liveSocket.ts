// Stub de LiveSocketLike para tests: emite frames a demanda. Implementa
// también ConnectableLiveSocket para poder inyectarse al LiveSocketProvider
// del shell vía LiveSocketFactoryContext (renderRoutes).

import type { ReactElement } from "react";
import { createElement } from "react";

import type { ServerFrame } from "@takab/sdk";

import { LiveSocketContext, type LiveSocketLike } from "../features/console/socket";
import type { ConnectableLiveSocket } from "../live/socket";
import type { LiveStatus } from "../lib/ws";

export class FakeLiveSocket implements LiveSocketLike, ConnectableLiveSocket {
  status: LiveStatus = "ready";
  connectCalls = 0;
  closeCalls = 0;
  private readonly listeners = new Map<string, Set<(frame: ServerFrame) => void>>();
  private readonly statusListeners = new Set<(status: LiveStatus) => void>();
  private readonly lastFrame = new Map<string, number>();

  connect(): void {
    this.connectCalls += 1;
  }

  close(): void {
    this.closeCalls += 1;
  }

  subscribe(topic: string, listener: (frame: ServerFrame) => void): () => void {
    const set = this.listeners.get(topic) ?? new Set();
    set.add(listener);
    this.listeners.set(topic, set);
    return () => set.delete(listener);
  }

  lastFrameAt(topic: string): number | null {
    return this.lastFrame.get(topic) ?? null;
  }

  onStatus(listener: (status: LiveStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  // --- helpers de test ---
  emit(topic: string, frame: ServerFrame): void {
    this.lastFrame.set(topic, Date.now());
    for (const listener of this.listeners.get(topic) ?? []) {
      listener(frame);
    }
  }

  setStatus(status: LiveStatus): void {
    this.status = status;
    for (const listener of this.statusListeners) {
      listener(status);
    }
  }

  topics(): string[] {
    return [...this.listeners.keys()].filter((t) => (this.listeners.get(t)?.size ?? 0) > 0);
  }
}

/** Envuelve children con el contexto del socket (para wrappers de renderHook). */
export function withLiveSocket(socket: LiveSocketLike, children: ReactElement): ReactElement {
  return createElement(LiveSocketContext.Provider, { value: socket }, children);
}
