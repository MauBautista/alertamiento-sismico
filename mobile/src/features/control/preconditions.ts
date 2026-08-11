// Precondiciones del control 2.2 con estado REAL prellenado (spec §2.2: "no
// checkbox ciego"). Se derivan del mismo mobile-state + traza del incidente;
// función PURA. Silenciar y activar tienen preflight distinto.
//
// [T-2.110] LA PRECONDICIÓN DE SILENCIAR YA NO SE AUTORIZA SOLA.
//
// Recibía un `sirenActive: boolean` que el panel derivaba de que EXISTIERA un
// `siren_on` en la traza del incidente. `siren_off` no estaba dado de alta en
// `ACTION_STATE`, así que nada lo cancelaba: bastaba una activación histórica
// para que la precondición quedara satisfecha el resto del incidente, y el
// detalle afirmara «El gabinete reporta la sirena activa» sin que el gabinete
// hubiera reportado nada.
//
// Ahora entra la EVIDENCIA, no un booleano: qué se sabe y DE DÓNDE se sabe
// (`sirenEvidence`, `@takab/sdk`). Tres desenlaces, tres frases distintas —
// «el gabinete midió el relé», «esto es la última ORDEN, no el relé» y «no
// consta nada»—, porque decirlas iguales es lo que convirtió una inferencia en
// una afirmación del gabinete.
import type { MobileStateOut, SirenEvidence } from "@takab/sdk";

import type { Precondition } from "./ControlSheet";
import type { TacticalAction } from "./service";

/** Lo que la pantalla sabe de la sirena y no cabe en `mobile-state`. */
export type SirenContext = {
  /** Último dato REAL del canal en la traza del incidente; `null` = no consta. */
  siren: SirenEvidence | null;
  /** [T-2.106] Alarma del inmueble vigente: el quórum de pánico enciende la
   *  sirena SIN abrir incidente, así que la traza está vacía por diseño. */
  buildingAlarm?: boolean;
};

function sirenaSonando(action: TacticalAction, ctx: SirenContext): Precondition {
  const evidencia = ctx.siren;
  if (evidencia !== null && evidencia.fromRelay) {
    // El gabinete MIDIÓ el relé tras arbitrar las demandas: es lo más fuerte
    // que hay, y es lo único que autoriza a decir «el gabinete reporta».
    return {
      label: "La sirena está sonando",
      met: evidencia.active,
      detail: evidencia.active
        ? "El gabinete reporta el relé de la sirena ENERGIZADO tras arbitrar sus demandas."
        : "El gabinete reporta el relé de la sirena EN REPOSO: no hay nada que silenciar.",
    };
  }
  if (evidencia !== null) {
    // Sólo el verbo de la traza. Se usa, y se dice que es la ORDEN: un
    // `deactivate` ejecutado con una alerta vigente escribe `siren_off` y deja
    // la sirena sonando (spec §2.1 — «no la última orden enviada»).
    return {
      label: "La sirena está sonando",
      met: evidencia.active,
      detail: evidencia.active
        ? "La última orden ejecutada sobre la sirena fue de ACTIVACIÓN; este gabinete no reporta el estado del relé."
        : "La última orden ejecutada sobre la sirena fue de SILENCIO; este gabinete no reporta el estado del relé.",
    };
  }
  if (ctx.buildingAlarm === true) {
    return {
      label: "La sirena está sonando",
      met: true,
      detail:
        "Hay una alarma del inmueble vigente en el sitio (sin incidente sísmico): el servidor la corrobora contra el gabinete que la ejecutó.",
    };
  }
  return {
    label: "La sirena está sonando",
    met: false,
    detail:
      action === "deactivate"
        ? "No consta ninguna actuación de sirena en este incidente: no hay demanda que retirar."
        : "No consta ninguna actuación de sirena en este incidente.",
  };
}

export function preconditionsFor(
  action: TacticalAction,
  state: MobileStateOut,
  ctx: SirenContext,
): Precondition[] {
  if (action === "deactivate") {
    // Retirar la demanda tiene sentido solo si la sirena suena; se declara que
    // puede seguir activa por la alerta (el acuse lo dirá, spec §2.2).
    return [sirenaSonando(action, ctx)];
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
