// Estado de sesión (zustand) — espejo del contrato de la consola:
// status + idToken (cache síncrono para el interceptor del SDK) + /me.
// El 401 del backend cierra sesión; un 403 es autorización fina y NO expulsa.
import type { MeResponse } from "@takab/sdk";
import { create } from "zustand";

import type { GateDenyReason, ProfileGroup } from "./profileGate";
import { clearSession } from "./secureTokens";

export type SessionStatus = "booting" | "anonymous" | "authenticated" | "denied";

interface SessionState {
  status: SessionStatus;
  profile: ProfileGroup | null;
  idToken: string | null;
  me: MeResponse | null;
  deniedReason: GateDenyReason | null;
  setAnonymous: () => void;
  setAuthenticated: (s: { profile: ProfileGroup; idToken: string; me: MeResponse | null }) => void;
  setDenied: (reason: GateDenyReason) => void;
  /** 401 del backend o logout explícito: purga el almacén seguro y vuelve a anónimo. */
  signOut: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  status: "booting",
  profile: null,
  idToken: null,
  me: null,
  deniedReason: null,

  setAnonymous: () =>
    set({ status: "anonymous", profile: null, idToken: null, me: null, deniedReason: null }),

  setAuthenticated: ({ profile, idToken, me }) =>
    set({ status: "authenticated", profile, idToken, me, deniedReason: null }),

  setDenied: (reason) =>
    set({ status: "denied", profile: null, idToken: null, me: null, deniedReason: reason }),

  signOut: () => {
    // fire-and-forget: purgar el Keychain/Keystore no bloquea la UI
    void clearSession();
    set({ status: "anonymous", profile: null, idToken: null, me: null, deniedReason: null });
  },
}));
