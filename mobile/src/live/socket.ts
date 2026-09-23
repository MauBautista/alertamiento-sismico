// Socket live ÚNICO de la app (T-2.08): el MISMO LiveSocket de la consola
// (@takab/sdk — backoff+jitter, re-subscribe, staleness por topic). El token
// se lee del store EN CADA conexión.
//
// [T-8.04 · A-002 §4] El servidor cierra con 4401 al vencer el `exp` del token
// del handshake (60 min) aunque el REST ya lo haya renovado. Hasta esta ficha
// ese cierre RUTINARIO hacía `signOut()`: el panel del brigadista echaba a su
// dueño cada hora. Ahora:
//   · 4401 ⇒ `renewToken` (UNA vez por conexión, lo gobierna LiveSocket) y se
//     reconecta con el token nuevo; sólo una renovación `dead` cierra la sesión;
//   · renovación `offline` ⇒ la sesión SE QUEDA y el canal se APARCA: se reanuda
//     solo en cuanto el store tenga un token nuevo (REST, primer plano…);
//   · 4440 (D-38) ⇒ fuera con motivo `max_age`, sin renovar;
//   · la sesión se cierra ⇒ el socket se cierra (no reintenta con un token que
//     ya no existe).
import { LiveSocket, type SessionEndReason } from "@takab/sdk";

import { API_BASE_URL } from "@/auth/config";
import {
  ensureFreshToken,
  type RefreshOutcome,
  refreshSession,
  secondsLeft,
  signOutDead,
} from "@/auth/refresh";
import { useSessionStore } from "@/auth/session.store";

/** Antes de conectar, el token tiene que durar al menos esto; si no, se renueva
 * primero (un handshake con un token a punto de vencer es un 4401 seguro). */
const MARGEN_AL_CONECTAR_S = 60;

/** URL del canal live desde la base ABSOLUTA del API (sin window — RN). */
export function liveWsUrl(apiBaseUrl: string): string {
  const abs = new URL(apiBaseUrl);
  abs.protocol = abs.protocol === "https:" ? "wss:" : "ws:";
  const path = abs.pathname.endsWith("/") ? abs.pathname.slice(0, -1) : abs.pathname;
  return `${abs.protocol}//${abs.host}${path}/ws`;
}

/** `connect()` renueva primero si hace falta. Un `close()` —o otro `connect()`—
 * mientras tanto invalida la conexión pendiente. */
class MobileLiveSocket extends LiveSocket {
  private connectSeq = 0;

  override connect(): void {
    const seq = ++this.connectSeq;
    void ensureFreshToken(MARGEN_AL_CONECTAR_S)
      .catch(() => undefined)
      .then(() => {
        if (seq === this.connectSeq) {
          super.connect();
        }
      });
  }

  override close(): void {
    this.connectSeq += 1;
    super.close();
  }
}

let socket: MobileLiveSocket | null = null;
/** Token del último handshake: distingue «el 4401 es del token viejo y otro
 * camino ya renovó» de «el token vigente fue rechazado». */
let tokenDelHandshake: string | null = null;
/** Resultado de la última renovación pedida por el socket. */
let ultimaRenovacion: RefreshOutcome | null = null;
/** Canal parado por falta de red al renovar; se reanuda con el próximo token. */
let aparcado = false;
let soltarStore: (() => void) | null = null;

async function renovarParaSocket(): Promise<string | null> {
  const actual = useSessionStore.getState().idToken;
  const yaRenovado =
    actual !== null && actual !== tokenDelHandshake && secondsLeft(actual) > MARGEN_AL_CONECTAR_S;
  if (yaRenovado) {
    ultimaRenovacion = "ok"; // el REST ya renovó: basta con reconectar
    return actual;
  }
  ultimaRenovacion = await refreshSession();
  return ultimaRenovacion === "ok" ? useSessionStore.getState().idToken : null;
}

function alTerminarSesion(reason?: SessionEndReason): void {
  if (reason === "max_age") {
    useSessionStore.getState().signOut("max_age");
    return;
  }
  const renovacion = ultimaRenovacion;
  ultimaRenovacion = null;
  if (renovacion === "offline" && useSessionStore.getState().status === "authenticated") {
    aparcado = true; // sin red: la sesión sigue; el canal vuelve con el token nuevo
    return;
  }
  signOutDead();
}

function vigilarSesion(): () => void {
  return useSessionStore.subscribe((estado, previo) => {
    if (estado.status !== "authenticated" && previo.status === "authenticated") {
      aparcado = false;
      socket?.close();
      return;
    }
    if (aparcado && estado.idToken !== null && estado.idToken !== previo.idToken) {
      aparcado = false;
      socket?.connect();
    }
  });
}

export function getLiveSocket(): LiveSocket {
  if (socket === null) {
    socket = new MobileLiveSocket({
      url: liveWsUrl(API_BASE_URL),
      getToken: () => {
        tokenDelHandshake = useSessionStore.getState().idToken;
        return tokenDelHandshake;
      },
      renewToken: renovarParaSocket,
      onUnauthorized: alTerminarSesion,
    });
    soltarStore = vigilarSesion();
  }
  return socket;
}

/** Reset SOLO para tests. */
export function resetLiveSocketForTests(): void {
  socket?.close();
  socket = null;
  soltarStore?.();
  soltarStore = null;
  tokenDelHandshake = null;
  ultimaRenovacion = null;
  aparcado = false;
}
