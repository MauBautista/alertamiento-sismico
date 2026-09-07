// [T-6.19] Qué dice la franja de simulacro — función PURA sobre el contrato.
//
// Medido el 2026-09-06 con un simulacro real: los dos gabinetes lo RECHAZARON
// (consola: «0/2 ACUSADOS · 2 RECHAZADO(S)») y el teléfono anunció «SIMULACRO
// EN CURSO» los tres minutos. `active` era una ventana de reloj. Desde T-6.17
// la nube dice qué hizo el gabinete de ESTE sitio (`execution`) y cuántos lo
// ejecutan (`sites_executing`/`sites_total`); la franja se deriva de eso y
// jamás de la ventana.
//
// «EN CURSO» sólo si el gabinete de este edificio acusó y no abortó. Todo lo
// demás es un ANUNCIO: se dice que hay un simulacro y se dice, con su razón,
// que aquí no está sonando. Un estado que no se reconoce cae en ANUNCIADO,
// nunca en EN CURSO (default-deny, igual que en la API).
import type { MobileDrillOut } from "@takab/sdk";

export type DrillNoticeKind = "executing" | "pending" | "not_executing" | "aborted";

/** Glifos de `@expo/vector-icons/Feather`: la FORMA que distingue sin matiz. */
export type NoticeGlyph = "volume-2" | "clock" | "slash" | "alert-triangle";

export interface DrillNotice {
  kind: DrillNoticeKind;
  title: string;
  detail: string;
  glyph: NoticeGlyph;
}

const REASON: Record<string, string> = {
  rejected: "El gabinete rechazó el comando",
  expired: "El comando venció sin respuesta del gabinete",
  no_gateway: "Este edificio no tiene gabinete comandable",
};

/** `execution` del contrato T-6.17; una nube anterior sólo manda `active`. */
export function drillExecution(drill: MobileDrillOut): string {
  if (typeof drill.execution === "string") {
    return drill.execution;
  }
  return drill.active ? "executing" : "none";
}

function conteo(drill: MobileDrillOut): string | null {
  const total = drill.sites_total ?? 0;
  if (total <= 1) {
    return null;
  }
  const ejecutan = drill.sites_executing ?? 0;
  return `${ejecutan} de ${total} gabinetes lo ejecutan`;
}

export function drillNotice(drill: MobileDrillOut): DrillNotice | null {
  const execution = drillExecution(drill);
  const cuenta = conteo(drill);
  switch (execution) {
    case "none":
      return null;
    case "executing":
      return {
        kind: "executing",
        title: "SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL",
        detail: cuenta ?? "El gabinete de su edificio lo está ejecutando",
        glyph: "volume-2",
      };
    case "pending":
      return {
        kind: "pending",
        title: "SIMULACRO ANUNCIADO — EL GABINETE AÚN NO CONFIRMA",
        detail: [cuenta, "Si no suena, su gabinete no lo ha aceptado"]
          .filter((s) => s !== null)
          .join(" · "),
        glyph: "clock",
      };
    case "aborted":
      return {
        kind: "aborted",
        title: "SIMULACRO ABORTADO — EL GABINETE ATENDIÓ UNA ALERTA REAL",
        detail: "Siga las indicaciones de la alerta, no las del ensayo",
        glyph: "alert-triangle",
      };
    default: {
      // rejected · expired · no_gateway · cualquier valor futuro.
      const otros = drill.sites_executing ?? 0;
      return {
        kind: "not_executing",
        title:
          otros > 0
            ? "SIMULACRO ANUNCIADO — SU GABINETE NO LO EJECUTA"
            : "SIMULACRO ANUNCIADO — NINGÚN GABINETE LO EJECUTA",
        detail: [cuenta, REASON[execution] ?? "El gabinete no lo está ejecutando"]
          .filter((s) => s !== null)
          .join(" · "),
        glyph: "slash",
      };
    }
  }
}

/**
 * Las pantallas de las dos pestañeras reservan esta banda superior para la
 * barra de estado (`paddingTop: 64` en cada `wrap`). La franja vive en el
 * navegador, ENCIMA de ellas, y solapa exactamente esa banda para no abrir un
 * hueco; lo que asoma bajo la franja es el inset real del aparato. Si una
 * pantalla deja de reservar 64, `tab-layouts-notices.test.ts` lo dice.
 */
export const TAB_SCREEN_TOP_RESERVE = 64;

export function stripOverlap(topInset: number): number {
  return Math.max(0, TAB_SCREEN_TOP_RESERVE - Math.max(0, topInset));
}
