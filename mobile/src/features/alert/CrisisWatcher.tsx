// Vigilante global de crisis: la push DESPIERTA (invalida la query) y la fase
// del servidor ENRUTA — al entrar alert_active, toma de pantalla inmediata.
// Vive dentro del QueryClientProvider en el layout raíz; no pinta nada.
import * as Notifications from "expo-notifications";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "expo-router";
import { useEffect, useRef } from "react";

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
  const { state, data } = useAlertState(siteId);
  // [T-2.106] Instante de la alarma del inmueble YA anunciada. La toma sísmica
  // se re-impone en cada render porque de una evacuación no se sale con el dedo;
  // la alarma del inmueble se anuncia UNA VEZ por activación, porque la pantalla
  // le pide al ocupante que atienda a su brigada y devolverlo a la fuerza le
  // impediría abrir el directorio para llamarla. Una activación NUEVA (otro
  // `since`) vuelve a anunciarse.
  const alarmaAnunciada = useRef<string | null>(null);

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

  const alarmaDesde = data?.building_alarm?.since ?? null;
  useEffect(() => {
    if (state === "alert_active" && pathname !== "/crisis") {
      router.push("/crisis");
      return;
    }
    // [T-2.06] Sacudida concluida sin check-in propio ⇒ toma de pantalla 1.4.
    if (state === "checkin_pending" && pathname !== "/checkin") {
      router.push("/checkin");
      return;
    }
    // [T-2.106] Alarma del inmueble: se anuncia al ENTRAR en ella (y de nuevo
    // si es otra activación), jamás en bucle. El servidor ya resolvió la
    // precedencia, así que llegar aquí significa que NO hay sismo en curso.
    if (state === "building_alarm" && alarmaDesde !== null) {
      if (alarmaAnunciada.current !== alarmaDesde) {
        alarmaAnunciada.current = alarmaDesde;
        if (pathname !== "/alarma-inmueble") {
          router.push("/alarma-inmueble");
        }
      }
      return;
    }
    if (state !== null && state !== "building_alarm") {
      alarmaAnunciada.current = null; // la próxima activación vuelve a anunciarse
    }
  }, [state, alarmaDesde, pathname, router]);

  return null;
}
