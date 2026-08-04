// ¿Llegó la configuración firmada a este gabinete? (T-2.37)
//
// El estado ya lo deriva el servidor (`GET /fleet/config-state`), con el MISMO
// predicado que usa el worker de publicación — no es una segunda opinión. Aquí solo
// se pinta, y sobre todo se distingue "no ha llegado" de "no puede llegar":
//
//   PENDIENTE            → el worker lo publicará (≤60 s)
//   NO SINCRONIZABLE     → le falta el iot_thing; NUNCA llegará hasta vincularlo
//   SIN CONFIG EDGE      → el rule_set activo no trae bloque `edge`; tampoco llegará
//   DESCONOCIDO          → la consulta falló; NO se asume que esté sincronizado
//
// Los tres últimos se veían iguales ("pendiente para siempre") y el operador no tenía
// forma de saber a quién llamar.

import type { GatewayConfigStateOut } from "@takab/sdk";

export interface SyncBadgeProps {
  /** `undefined` = aún no se sabe (query en vuelo o fallida). */
  state: GatewayConfigStateOut | undefined;
}

type Tone = "ok" | "warn" | "crit" | "idle";

export function syncView(state: GatewayConfigStateOut | undefined): {
  label: string;
  tone: Tone;
  title: string;
} {
  if (state === undefined) {
    return {
      label: "SYNC S/D",
      tone: "idle",
      title: "No se pudo leer el estado del config firmado; no se asume nada.",
    };
  }
  if (!state.is_syncable) {
    return {
      label: "NO SINCRONIZABLE",
      tone: "crit",
      title:
        "El gabinete no tiene iot_thing (o está retirado): el worker lo excluye y " +
        "nunca recibirá configuración firmada.",
    };
  }
  if (!state.has_edge_config) {
    return {
      label: "SIN CONFIG EDGE",
      tone: "warn",
      title:
        "El rule_set activo no trae bloque 'edge': no hay nada que publicar. " +
        "Publica umbrales desde Multi-Tenant.",
    };
  }
  if (state.in_sync) {
    return {
      label: `SINCRONIZADO v${state.version ?? "?"}`,
      tone: "ok",
      title: `Huella de la firma: ${state.sig_fingerprint ?? "s/d"}`,
    };
  }
  return {
    label: "PENDIENTE",
    tone: "warn",
    title: "Hay un cambio sin publicar; el worker lo firma y entrega en menos de un minuto.",
  };
}

export default function SyncBadge({ state }: SyncBadgeProps) {
  const view = syncView(state);
  return (
    <span
      className={`fleet-sync fleet-sync--${view.tone}`}
      title={view.title}
      data-testid="sync-badge"
    >
      {view.label}
    </span>
  );
}
