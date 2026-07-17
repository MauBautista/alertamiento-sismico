// Precondiciones del control 2.2 con estado REAL prellenado (spec §2.2: "no
// checkbox ciego"). Se derivan del mismo mobile-state + traza del incidente;
// función PURA. Silenciar y activar tienen preflight distinto.
import type { MobileStateOut } from "@takab/sdk";

import type { Precondition } from "./ControlSheet";
import type { TacticalAction } from "./service";

export function preconditionsFor(
  action: TacticalAction,
  state: MobileStateOut,
  ctx: { sirenActive: boolean },
): Precondition[] {
  if (action === "deactivate") {
    // Retirar la demanda tiene sentido solo si la sirena suena por acción
    // manual; se declara que puede seguir activa por la alerta.
    return [
      {
        label: "La sirena está sonando",
        met: ctx.sirenActive,
        detail: ctx.sirenActive
          ? "El gabinete reporta la sirena activa."
          : "No hay sirena activa que silenciar.",
      },
    ];
  }
  // activate: disparo manual — evacuación en curso y sitio enlazado.
  const evacuating = state.phase === "alert_active" || state.phase === "shaking_concluded";
  const linked = state.site_health.status !== "SIN ENLACE";
  return [
    {
      label: "El edificio está en evacuación / post-sismo",
      met: evacuating,
      detail: evacuating
        ? "Hay un incidente vigente en el sitio."
        : "Sin incidente vigente: la activación manual es para emergencia real.",
    },
    {
      label: "El gabinete responde",
      met: linked,
      detail: linked
        ? `Gabinete ${state.site_health.status}.`
        : "SIN ENLACE: el comando podría no ejecutarse.",
    },
  ];
}
