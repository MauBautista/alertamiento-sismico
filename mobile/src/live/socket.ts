// Socket live ÚNICO de la app (T-2.08): el MISMO LiveSocket de la consola
// (@takab/sdk — backoff+jitter, re-subscribe, staleness por topic). El token
// se lee del store EN CADA conexión; 4401 cierra la sesión (como el REST).
import { LiveSocket } from "@takab/sdk";

import { API_BASE_URL } from "@/auth/config";
import { useSessionStore } from "@/auth/session.store";

/** URL del canal live desde la base ABSOLUTA del API (sin window — RN). */
export function liveWsUrl(apiBaseUrl: string): string {
  const abs = new URL(apiBaseUrl);
  abs.protocol = abs.protocol === "https:" ? "wss:" : "ws:";
  const path = abs.pathname.endsWith("/") ? abs.pathname.slice(0, -1) : abs.pathname;
  return `${abs.protocol}//${abs.host}${path}/ws`;
}

let socket: LiveSocket | null = null;

export function getLiveSocket(): LiveSocket {
  if (socket === null) {
    socket = new LiveSocket({
      url: liveWsUrl(API_BASE_URL),
      getToken: () => useSessionStore.getState().idToken,
      onUnauthorized: () => useSessionStore.getState().signOut(),
    });
  }
  return socket;
}

/** Reset SOLO para tests. */
export function resetLiveSocketForTests(): void {
  socket?.close();
  socket = null;
}
