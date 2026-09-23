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
      // [T-8.03 · A-004] El servidor cierra el canal con 4401 al vencer el `exp`
      // del token del handshake (60 min). Sin renovación, ese cierre RUTINARIO
      // terminaba la sesión aunque la renovación silenciosa ya tuviera un token
      // nuevo: la consola se cerraba a la hora. Ahora el socket pide UNA
      // renovación —la misma, de vuelo único, que usan los 401 del REST— y
      // reconecta con el token nuevo.
      renewToken: () => useSessionStore.getState().renewToken(),
      // 4440 ⇒ la sesión cumplió el tope de su rol (D-38): fin con esa causa.
      // 4401 sin renovación posible ⇒ fin como expirada, CON causa: antes era
      // `logout()`, que borraba la causa y mandaba al /logout del Hosted UI, así
      // que el operador aparecía en un login mudo (el silencio que T-6.07 cerró
      // para el REST seguía abierto aquí).
      onUnauthorized: (reason) => {
        useSessionStore.getState().handleUnauthorized(reason === "max_age" ? "max_age" : "expired");
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
