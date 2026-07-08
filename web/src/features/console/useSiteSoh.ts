// SOH (state of health) del gabinete del sitio enfocado: último frame
// site_state kind=device_health. Logging por transición + heartbeat (regla de
// oro 10): sin frame aún ⇒ null, el panel muestra S/D — jamás inventa salud.

import { useEffect, useState } from "react";

import { TOPIC_SITE_STATE } from "@takab/sdk";
import type { SiteStateFrame } from "@takab/sdk";

import { useLiveSocket } from "./socket";

export function useSiteSoh(siteId: string | null): SiteStateFrame | null {
  const socket = useLiveSocket();
  const [soh, setSoh] = useState<SiteStateFrame | null>(null);

  useEffect(() => {
    setSoh(null); // cambio de sitio: la salud del anterior no aplica
    if (!socket || siteId === null) return undefined;
    return socket.subscribe(TOPIC_SITE_STATE, (frame) => {
      if (frame.type !== "site_state") return;
      const state = frame as SiteStateFrame;
      if (state.site_id !== siteId || state.kind !== "device_health") return;
      setSoh(state);
    });
  }, [socket, siteId]);

  return soh;
}
