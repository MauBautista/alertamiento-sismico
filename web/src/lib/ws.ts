// [T-2.08] LiveSocket vive en @takab/sdk (compartido con la app móvil — misma
// reconexión backoff+jitter, re-subscribe y staleness). Aquí queda SOLO lo
// específico del navegador (la URL depende de window) y el re-export para que
// los consumidores de la consola no cambien de import.

export {
  LiveSocket,
  type FrameListener,
  type LiveSocketOptions,
  type LiveStatus,
  type StatusListener,
} from "@takab/sdk";

/** URL del canal live: base del API (relativa o absoluta) + `/ws`, ws(s) según origen. */
export function liveWsUrl(apiBaseUrl: string): string {
  const abs = new URL(apiBaseUrl, window.location.href);
  abs.protocol = abs.protocol === "https:" ? "wss:" : "ws:";
  const path = abs.pathname.endsWith("/") ? abs.pathname.slice(0, -1) : abs.pathname;
  return `${abs.protocol}//${abs.host}${path}/ws`;
}
