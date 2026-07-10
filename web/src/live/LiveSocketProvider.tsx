// Dueño ÚNICO del LiveSocket (T-1.49): AppShell lo monta y todas las páginas
// (y la topbar) consumen el mismo canal. Antes cada página creaba el suyo y
// /fleet y /triage quedaban sin live — la topbar decía "SIN DATOS" para
// siempre. Conecta SOLO con sesión (idToken) y alimenta el store de salud con
// UNA suscripción a site_state para todo el árbol.

import { useContext, useEffect, useMemo, type ReactNode } from "react";

import { TOPIC_SITE_STATE } from "@takab/sdk";

import { getEnv } from "../app/env";
import { useSessionStore } from "../auth/session.store";
import { LiveSocket, liveWsUrl } from "../lib/ws";
import { useLiveHealthStore } from "./liveHealth.store";
import { LiveSocketContext, LiveSocketFactoryContext, type ConnectableLiveSocket } from "./socket";

export default function LiveSocketProvider({ children }: { children: ReactNode }) {
  const factory = useContext(LiveSocketFactoryContext);
  const idToken = useSessionStore((s) => s.idToken);

  const socket = useMemo<ConnectableLiveSocket>(() => {
    if (factory !== null) {
      return factory();
    }
    return new LiveSocket({
      url: liveWsUrl(getEnv().apiBaseUrl),
      getToken: () => useSessionStore.getState().idToken,
      onUnauthorized: () => {
        void useSessionStore.getState().logout();
      },
    });
  }, [factory]);

  // Cableado al store de salud: estado del canal + heartbeats de device_health.
  useEffect(() => {
    const store = useLiveHealthStore.getState();
    store.setStatus(socket.status);
    const offStatus = socket.onStatus((s) => useLiveHealthStore.getState().setStatus(s));
    const offFrames = socket.subscribe(TOPIC_SITE_STATE, (frame) =>
      useLiveHealthStore.getState().applyFrame(frame),
    );
    return () => {
      offStatus();
      offFrames();
    };
  }, [socket]);

  // Vida del socket atada a la sesión: sin token no se abre nada (y al cerrar
  // sesión se cierra). connect()/close() son idempotentes (StrictMode).
  useEffect(() => {
    if (idToken === null) {
      return;
    }
    socket.connect();
    return () => socket.close();
  }, [socket, idToken]);

  return <LiveSocketContext.Provider value={socket}>{children}</LiveSocketContext.Provider>;
}
