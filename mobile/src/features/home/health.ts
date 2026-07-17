// Banner del edificio (1.1) — mapeo PURO del estado que sirve el servidor
// (verdad única de Flota Edge: OPERATIVO/DEGRADADO/SIN ENLACE). El teléfono
// jamás calcula el estado; solo lo traduce a la copy del ocupante.
import type { MobileSiteHealthOut } from "@takab/sdk";

import { timeAgoLabel } from "@/ui/timeAgo";

export type HealthTone = "ok" | "warn" | "crit";

export type HealthBanner = {
  label: string;
  tone: HealthTone;
  detail: string;
};

export function healthBanner(h: MobileSiteHealthOut, nowMs: number): HealthBanner {
  if (h.status === "OPERATIVO") {
    return { label: "SEGURO", tone: "ok", detail: "Monitoreo sísmico activo." };
  }
  if (h.status === "DEGRADADO") {
    return {
      label: "DEGRADADO",
      tone: "warn",
      detail: "El gabinete reporta con métricas fuera de rango.",
    };
  }
  return {
    label: "SIN ENLACE",
    tone: "crit",
    detail:
      h.heartbeat_at !== null
        ? `El gabinete no reporta (último contacto ${timeAgoLabel(Date.parse(h.heartbeat_at), nowMs)}).`
        : "Sin gabinete reportando en este inmueble.",
  };
}

/** Chip SASMEX honesto: el WR-1 no expone supervisión de línea (solo el
 *  Relevador 2 está cableado — fase 1.9), así que lo VERIFICABLE es: receptor
 *  WR-1 declarado en el alta + gabinete reportando. Sin enlace del gabinete o
 *  sin WR-1 ⇒ sin chip; jamás un "ENLAZADO" que nadie mide. */
export function wr1Chip(h: MobileSiteHealthOut): string | null {
  if (!h.has_wr1 || h.status === "SIN ENLACE") {
    return null;
  }
  return "SASMEX WR-1 · GABINETE ENLAZADO";
}
