// [T-6.19] Contenedor de la franja: lee el MISMO `mobile-state` que las
// pestañas (misma clave de react-query: un solo sondeo, no dos), el inset del
// aparato y la preferencia de movimiento. No monta `StateFrame` a propósito:
// no es una pantalla, es un aviso que sólo existe cuando hay dato; los cuatro
// estados los declara la pestaña que está debajo.
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { useReduceMotion } from "@/ui/useReduceMotion";

import { SiteNoticeStrip } from "./SiteNoticeStrip";

export function SiteNotices() {
  const siteId = useWatchedSiteId();
  const { data } = useAlertState(siteId);
  const insets = useSafeAreaInsets();
  const reduceMotion = useReduceMotion();
  return <SiteNoticeStrip data={data} reduceMotion={reduceMotion} topInset={insets.top} />;
}
