// Sitio VIGILADO por este dispositivo (a quién le pedimos mobile-state).
// occupant: el sitio de su enrolamiento (se sella al vincular, R2 server-side).
// tácticos: el primero de su site_scope; con "*" (todo el tenant) no hay sitio
// único que vigilar — el selector llega con el dashboard (T-2.08) y mientras
// tanto se DECLARA (null), sin adivinar.
import * as SecureStore from "expo-secure-store";
import { useEffect, useState } from "react";

import { useSessionStore } from "@/auth/session.store";

export const WATCHED_SITE_KEY = "takab.watched_site.v1";

export async function setWatchedSite(siteId: string): Promise<void> {
  await SecureStore.setItemAsync(WATCHED_SITE_KEY, siteId);
}

export async function getStoredWatchedSite(): Promise<string | null> {
  return await SecureStore.getItemAsync(WATCHED_SITE_KEY);
}

/** Resolución PURA del fallback por claims (testeable). */
export function siteFromScope(siteScope: "*" | string[] | null | undefined): string | null {
  if (Array.isArray(siteScope) && siteScope.length > 0) {
    return siteScope[0];
  }
  return null;
}

export function useWatchedSiteId(): string | null {
  const me = useSessionStore((s) => s.me);
  const status = useSessionStore((s) => s.status);
  const [siteId, setSiteId] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    let alive = true;
    void getStoredWatchedSite().then((stored) => {
      if (alive) {
        setSiteId(stored ?? siteFromScope(me?.site_scope));
      }
    });
    return () => {
      alive = false;
    };
  }, [status, me]);

  return siteId;
}
