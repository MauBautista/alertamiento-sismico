// Sitio VIGILADO por este dispositivo (a quién le pedimos mobile-state).
// occupant: el sitio de su enrolamiento (se sella al vincular, R2 server-side).
// tácticos: el primero de su site_scope; con "*" (todo el tenant) no hay sitio
// único que vigilar — el selector llega con el dashboard (T-2.08) y mientras
// tanto se DECLARA (null), sin adivinar.
import * as SecureStore from "expo-secure-store";
import { useEffect } from "react";
import { create } from "zustand";

import { useSessionStore } from "@/auth/session.store";

export const WATCHED_SITE_KEY = "takab.watched_site.v1";

/** El sitio vigilado, en un store OBSERVABLE y no en estado local del hook.
 *
 * [T-2.103] SecureStore no notifica a nadie cuando cambia. Con el sitio en un
 * `useState` por instancia del hook, `setWatchedSite` escribía el disco y NINGÚN
 * componente ya montado se enteraba: el efecto solo se re-ejecutaba al cambiar
 * `status` o `me`, y enrolarse no toca ninguno de los dos.
 *
 * El daño no era cosmético. `CrisisWatcher` se monta en el layout RAÍZ, antes del
 * onboarding, así que resolvía `siteId = null` (recién instalada, SecureStore
 * vacío) y **se quedaba así toda la sesión**: sin sitio no hay `mobile-state`,
 * sin `mobile-state` no hay fase, y sin fase NO HAY TOMA DE PANTALLA DE CRISIS.
 * Un ocupante que se enrolaba y sufría un sismo antes de reiniciar la app no
 * recibía la instrucción de evacuar — y esa es, para todo edificio nuevo, la
 * primera sesión de todo el mundo. Medido en un Pixel 8 Pro el 2026-08-09: con
 * el servidor en `alert_active`, la app mostraba SEGURO hasta reiniciarla.
 */
interface SitioVigilado {
  siteId: string | null;
  fijar: (siteId: string | null) => void;
}

const useSitioVigilado = create<SitioVigilado>((set) => ({
  siteId: null,
  fijar: (siteId) => set({ siteId }),
}));

export async function setWatchedSite(siteId: string): Promise<void> {
  await SecureStore.setItemAsync(WATCHED_SITE_KEY, siteId);
  // Lo que faltaba: avisar. El disco es la persistencia; esto es la propagación.
  useSitioVigilado.getState().fijar(siteId);
}

/** Sólo para tests: deja el store como recién arrancada la app. */
export function resetWatchedSiteForTests(): void {
  useSitioVigilado.getState().fijar(null);
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
  const siteId = useSitioVigilado((s) => s.siteId);

  // Hidratación desde disco al autenticar. El valor vive en el store, así que
  // cualquier componente ya montado —`CrisisWatcher` el primero— ve el sitio en
  // cuanto el enrolamiento lo fija, sin esperar a un reinicio.
  useEffect(() => {
    if (status !== "authenticated") {
      useSitioVigilado.getState().fijar(null);
      return;
    }
    let alive = true;
    void getStoredWatchedSite().then((stored) => {
      if (alive) {
        useSitioVigilado.getState().fijar(stored ?? siteFromScope(me?.site_scope));
      }
    });
    return () => {
      alive = false;
    };
  }, [status, me]);

  return siteId;
}
