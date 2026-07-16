// Disparadores del drenaje: hidratación al autenticar, vuelta a foreground,
// recuperación de red (expo-network) y un tic periódico mientras haya
// pendientes (respeta next_attempt_at — el tic solo INTENTA, isDue decide).
import * as Network from "expo-network";
import { useEffect } from "react";
import { AppState } from "react-native";

import { useSessionStore } from "@/auth/session.store";

import { useQueueStore } from "./queue.store";
import { drainQueue } from "./sync";

const TICK_MS = 15_000;

export function OfflineSyncGate() {
  const status = useSessionStore((s) => s.status);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    void useQueueStore
      .getState()
      .hydrate()
      .then(() => drainQueue());

    const net = Network.addNetworkStateListener((state) => {
      if (state.isConnected) {
        void drainQueue();
      }
    });
    const app = AppState.addEventListener("change", (st) => {
      if (st === "active") {
        void drainQueue();
      }
    });
    const tick = setInterval(() => {
      if (useQueueStore.getState().items.some((i) => i.state === "pending")) {
        void drainQueue();
      }
    }, TICK_MS);

    return () => {
      net.remove();
      app.remove();
      clearInterval(tick);
    };
  }, [status]);

  return null;
}
