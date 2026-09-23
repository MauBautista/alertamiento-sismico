// Estado de sesión (zustand) — espejo del contrato de la consola:
// status + idToken (cache síncrono para el interceptor del SDK) + /me.
// Un 403 es autorización fina y NO expulsa.
//
// [T-8.04] Un 401 ya NO cierra la sesión por sí solo: antes se intenta renovar
// (`auth/refresh.ts`) y sólo una renovación MUERTA —o `sesion_expirada`, D-38—
// llega aquí. Por eso `signOut` lleva MOTIVO: la pantalla de login tiene que
// poder distinguir «usted cerró sesión» de «se cumplió el mes».
import type { MeResponse } from "@takab/sdk";
import { create } from "zustand";

import type { GateDenyReason, ProfileGroup } from "./profileGate";
import { clearSession } from "./secureTokens";

export type SessionStatus = "booting" | "anonymous" | "authenticated" | "denied";

/** Por qué terminó una sesión:
 * - `user`: la cerró la persona (botón);
 * - `expired`: el token ya no vale y no hubo forma de renovarlo (refresh
 *   revocado/vencido, o 4401 sin renovación posible);
 * - `max_age`: la sesión cumplió la edad máxima de su rol (D-38) — renovar no
 *   sirve, hay que volver a entrar con contraseña. */
export type SignOutReason = "user" | "expired" | "max_age";

const MOTIVOS: ReadonlySet<string> = new Set<SignOutReason>(["user", "expired", "max_age"]);

interface SessionState {
  status: SessionStatus;
  profile: ProfileGroup | null;
  idToken: string | null;
  me: MeResponse | null;
  deniedReason: GateDenyReason | null;
  /** [T-8.04 · D-38] epoch ms del login REAL; no cambia al renovar. */
  authAt: number | null;
  /** [T-8.04 · D-38] edad máxima de la sesión del rol (s), de `/me`. */
  maxAgeS: number | null;
  /** [T-8.04] Por qué terminó la última sesión; `null` si no terminó ninguna o
   * se volvió a entrar. Lo lee la pantalla de login. */
  signOutReason: SignOutReason | null;
  setAnonymous: () => void;
  setAuthenticated: (s: {
    profile: ProfileGroup;
    idToken: string;
    me: MeResponse | null;
    authAt?: number | null;
    maxAgeS?: number | null;
  }) => void;
  setDenied: (reason: GateDenyReason) => void;
  /** Cierre LOCAL: purga el almacén seguro y vuelve a anónimo, sin red ni
   * navegador (para eso está `logout()` en `auth/logout.ts`).
   *
   * La segunda firma existe porque `onPress={signOut}` le pasa el EVENTO del
   * toque: cualquier cosa que no sea un motivo cuenta como `user`. */
  signOut: {
    (reason?: SignOutReason): void;
    (event: object): void;
  };
}

export const useSessionStore = create<SessionState>((set, get) => ({
  status: "booting",
  profile: null,
  idToken: null,
  me: null,
  deniedReason: null,
  authAt: null,
  maxAgeS: null,
  signOutReason: null,

  setAnonymous: () =>
    set({
      status: "anonymous",
      profile: null,
      idToken: null,
      me: null,
      deniedReason: null,
      authAt: null,
      maxAgeS: null,
    }),

  setAuthenticated: ({ profile, idToken, me, authAt, maxAgeS }) =>
    set((s) => ({
      status: "authenticated",
      profile,
      idToken,
      me,
      deniedReason: null,
      authAt: authAt === undefined ? s.authAt : authAt,
      maxAgeS: maxAgeS === undefined ? s.maxAgeS : maxAgeS,
      signOutReason: null,
    })),

  setDenied: (reason) =>
    set({
      status: "denied",
      profile: null,
      idToken: null,
      me: null,
      deniedReason: reason,
      authAt: null,
      maxAgeS: null,
    }),

  signOut: (reason?: unknown) => {
    const prev = get();
    // La PRIMERA causa gana: tras un `sesion_expirada`, el socket vivo se entera
    // después (getToken ⇒ null ⇒ `expired`) y no debe reescribir el motivo. Y
    // quien ya era anónimo (p.ej. un login cuyo /me falló) no «pierde» una
    // sesión que nunca tuvo: no se le inventa motivo.
    const motivo: SignOutReason | null =
      prev.status === "anonymous"
        ? prev.signOutReason
        : typeof reason === "string" && MOTIVOS.has(reason)
          ? (reason as SignOutReason)
          : "user";
    // fire-and-forget: purgar el Keychain/Keystore no bloquea la UI
    void clearSession();
    set({
      status: "anonymous",
      profile: null,
      idToken: null,
      me: null,
      deniedReason: null,
      authAt: null,
      maxAgeS: null,
      signOutReason: motivo,
    });
  },
}));
