// Sitio VIGILADO por este dispositivo (a quién le pedimos mobile-state).
// occupant: el sitio de su enrolamiento (R2, server-side).
// tácticos: el primero de su site_scope; con "*" (todo el tenant) no hay sitio
// único que vigilar — el selector llega con el dashboard (T-2.08) y mientras
// tanto se DECLARA (null), sin adivinar.
//
// [T-2.114] El SERVIDOR es la fuente de verdad. `/me` devuelve `enrolled_sites`
// desde `user_zone_assignments`, así que el teléfono dejó de ser la única
// memoria del edificio de un ocupante. Consecuencias:
//   1. el caché se suelta al cerrar sesión (lo borra `clearSession`), y
//   2. lo que queda en disco va MARCADO con el `sub` que lo fijó, para que un
//      cierre de sesión que no llegó a completarse (app muerta a media salida)
//      tampoco pueda filtrar el edificio al siguiente usuario del aparato.
// El defecto que cierra: un usuario distinto en el mismo teléfono heredaba el
// inmueble del anterior, y `CrisisWatcher` vigilaba un edificio ajeno.
import type { MeResponse } from "@takab/sdk";
import * as SecureStore from "expo-secure-store";
import { useEffect } from "react";
import { create } from "zustand";

import { WATCHED_SITE_KEY } from "@/auth/secureTokens";
import { useSessionStore } from "@/auth/session.store";

export { WATCHED_SITE_KEY };

/** Lo que se guarda en disco: el sitio Y de quién es. Sin el dueño no se puede
 *  distinguir "mi edificio" de "el edificio del que usó el teléfono antes". */
interface SitioEnDisco {
  sub: string | null;
  site_id: string;
}

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

/** El sujeto de la sesión viva, o null si todavía no hay `/me` (arranque sin
 *  red). Se lee del store en el momento de escribir/leer, no se pasa por
 *  parámetro, para no cambiar la firma que ya usa `enrolamiento.tsx`. */
function subActual(): string | null {
  return (useSessionStore.getState().me as MeResponse | null)?.sub ?? null;
}

async function leerDisco(): Promise<SitioEnDisco | null> {
  const raw = await SecureStore.getItemAsync(WATCHED_SITE_KEY);
  if (raw == null) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as SitioEnDisco).site_id === "string"
    ) {
      const v = parsed as SitioEnDisco;
      return { sub: typeof v.sub === "string" ? v.sub : null, site_id: v.site_id };
    }
  } catch {
    // Cae abajo: valor sin forma reconocible.
  }
  // Cadena suelta bajo la clave nueva (no debería ocurrir; si ocurre, se trata
  // como caché SIN dueño y por tanto solo sirve al arranque offline).
  return { sub: null, site_id: raw };
}

async function escribirDisco(siteId: string, sub: string | null): Promise<void> {
  await SecureStore.setItemAsync(WATCHED_SITE_KEY, JSON.stringify({ sub, site_id: siteId }));
}

export async function setWatchedSite(siteId: string): Promise<void> {
  await escribirDisco(siteId, subActual());
  // Lo que faltaba: avisar. El disco es la persistencia; esto es la propagación.
  useSitioVigilado.getState().fijar(siteId);
}

/** Sólo para tests: deja el store como recién arrancada la app. */
export function resetWatchedSiteForTests(): void {
  useSitioVigilado.getState().fijar(null);
}

export async function getStoredWatchedSite(): Promise<string | null> {
  return (await leerDisco())?.site_id ?? null;
}

/** Resolución PURA del fallback por claims (testeable). */
export function siteFromScope(siteScope: "*" | string[] | null | undefined): string | null {
  if (Array.isArray(siteScope) && siteScope.length > 0) {
    return siteScope[0];
  }
  return null;
}

/** [T-2.114] Resolución PURA desde el SERVIDOR: el enrolamiento manda sobre el
 *  claim, porque es el dato que el ocupante no lleva en su token. */
export function siteFromMe(me: MeResponse | null | undefined): string | null {
  if (!me) {
    return null;
  }
  const enrolado = me.enrolled_sites?.[0]?.site_id;
  return enrolado ?? siteFromScope(me.site_scope);
}

export function useWatchedSiteId(): string | null {
  const me = useSessionStore((s) => s.me);
  const status = useSessionStore((s) => s.status);
  const siteId = useSitioVigilado((s) => s.siteId);

  // Hidratación al autenticar. El valor vive en el store, así que cualquier
  // componente ya montado —`CrisisWatcher` el primero— ve el sitio en cuanto el
  // enrolamiento lo fija, sin esperar a un reinicio.
  useEffect(() => {
    if (status !== "authenticated") {
      useSitioVigilado.getState().fijar(null);
      return;
    }
    let alive = true;
    void (async () => {
      const guardado = await leerDisco();
      if (!alive) {
        return;
      }
      // Sin `/me` (arranque OFFLINE con sesión en el Keychain) el portador es,
      // por construcción, el mismo que guardó ese valor: nadie más pudo abrir
      // esa sesión. Quitarle el edificio aquí lo dejaría sin pantalla de
      // crisis justo cuando no hay red (regla de oro 2).
      const sub = (me as MeResponse | null)?.sub ?? null;
      if (me == null) {
        useSitioVigilado.getState().fijar(guardado?.site_id ?? null);
        return;
      }
      // Caché de ESTA identidad: manda, porque puede ser más fresco que `/me`
      // (el enrolamiento recién canjeado no está en el `me` del login).
      if (guardado != null && guardado.sub === sub) {
        useSitioVigilado.getState().fijar(guardado.site_id);
        return;
      }
      // Caché ajeno o sin dueño: se IGNORA y decide el servidor.
      const delServidor = siteFromMe(me);
      useSitioVigilado.getState().fijar(delServidor);
      if (delServidor !== null) {
        // Se re-sella con el dueño correcto: así el próximo arranque sin red lo
        // encuentra, y el registro del push (T-2.109) sigue teniendo su sitio.
        await escribirDisco(delServidor, sub);
      }
    })();
    return () => {
      alive = false;
    };
  }, [status, me]);

  return siteId;
}
