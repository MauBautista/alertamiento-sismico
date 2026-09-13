// [T-7.29] Contenedor de la franja de alerta viva.
//
// Va aparte de la vista por la misma razón que `SiteNotices` está aparte de
// `SiteNoticeStrip`: importar `expo-router` en el módulo de la vista deja la
// vista sin poder probarse (jest no transforma ese paquete), y la pieza que
// hay que poder probar es justo la que pinta.
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useWatchedSiteId } from "@/services/mySite";

import { AlertaVivaStrip } from "./AlertaVivaStrip";
import { useAlertState } from "./useAlertState";

/** Mismo sondeo que las pestañas (una sola consulta, no dos). */
export function AlertaViva() {
  const siteId = useWatchedSiteId();
  const { state } = useAlertState(siteId);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  return (
    <AlertaVivaStrip
      onVolver={() => router.push("/crisis")}
      topInset={insets.top}
      visible={state === "alert_active"}
    />
  );
}
