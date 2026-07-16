// Vigilante global de crisis: la push DESPIERTA (invalida la query) y la fase
// del servidor ENRUTA — al entrar alert_active, toma de pantalla inmediata.
// Vive dentro del QueryClientProvider en el layout raíz; no pinta nada.
import * as Notifications from "expo-notifications";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "expo-router";
import { useEffect } from "react";

import { useWatchedSiteId } from "@/services/mySite";

import { MOBILE_STATE_KEY, useAlertState } from "./useAlertState";

// En primer plano las notificaciones también se muestran (la app puede estar
// abierta en otra pantalla cuando llegue la CRISIS).
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export function CrisisWatcher() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const siteId = useWatchedSiteId();
  const { state } = useAlertState(siteId);

  // Push recibida (primer plano o tap): invalidar mobile-state — el REST es la
  // verdad; el contenido de la push jamás enruta por sí solo.
  useEffect(() => {
    const invalidate = () => {
      void queryClient.invalidateQueries({ queryKey: [MOBILE_STATE_KEY] });
    };
    const received = Notifications.addNotificationReceivedListener(invalidate);
    const responded = Notifications.addNotificationResponseReceivedListener(invalidate);
    return () => {
      received.remove();
      responded.remove();
    };
  }, [queryClient]);

  useEffect(() => {
    if (state === "alert_active" && pathname !== "/crisis") {
      router.push("/crisis");
    }
  }, [state, pathname, router]);

  return null;
}
