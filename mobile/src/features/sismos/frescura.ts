// [T-9.62 · D-46] ¿Está al día el CATÁLOGO que sirve la nube? (regla de oro 7)
//
// Son dos edades distintas y no se mezclan:
//   · la del DATO EN EL TELÉFONO —cuándo le preguntó la app a la nube— la
//     pinta `StateFrame` («DATOS RETENIDOS»), derivada del reloj en `useSismos`;
//   · la del CATÁLOGO EN LA NUBE —cuándo la nube le preguntó a USGS— sale de
//     `sync_estado` y `actualizado`, y es ésta.
// Con red perfecta, la app puede tener una respuesta de hace un segundo que
// describe un catálogo de hace tres días: eso también es un dato congelado.
import type { SismosDelSitioOut } from "@takab/sdk";

import { fechaLocal } from "./fecha";

/** Más de media hora sin sincronizar y el catálogo deja de estar al día. */
export const MAX_EDAD_CATALOGO_MS = 30 * 60_000;

const MOTIVO: Record<SismosDelSitioOut["sync_estado"], string> = {
  ok: "",
  fallido: " · la última consulta a la fuente falló",
  apagado: " · la sincronización está apagada",
  nunca: "",
};

/**
 * `null` si el catálogo está al día; si no, el texto de la franja. Sin fecha de
 * actualización NUNCA está al día: afirmar frescura sin reloj es inventarla.
 */
export function catalogoSinActualizar(r: SismosDelSitioOut, nowMs: number): string | null {
  const actualizadoMs = r.actualizado ? Date.parse(r.actualizado) : NaN;
  const reciente =
    Number.isFinite(actualizadoMs) && nowMs - actualizadoMs <= MAX_EDAD_CATALOGO_MS;
  if (r.sync_estado === "ok" && reciente) {
    return null;
  }
  if (!Number.isFinite(actualizadoMs)) {
    return `CATÁLOGO SIN ACTUALIZAR · NUNCA SINCRONIZADO${MOTIVO[r.sync_estado]}`;
  }
  return `CATÁLOGO SIN ACTUALIZAR DESDE ${fechaLocal(r.actualizado as string)}${MOTIVO[r.sync_estado]}`;
}
