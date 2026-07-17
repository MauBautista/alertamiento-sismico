// Estado PURO del pánico por quórum-de-2 (1.9). Deriva la copy del resultado
// del voto — SIEMPRE deja claro que NO es la alerta sísmica (es una emergencia
// del inmueble: incendio, intrusión…). El quórum lo decide el SERVIDOR.
import type { PanicVoteOut } from "@takab/sdk";

export type PanicPhase = "idle" | "voting" | "counted" | "activated" | "discarded" | "error";

export type PanicStatus = {
  phase: PanicPhase;
  title: string;
  detail: string;
  tone: "muted" | "warn" | "crit" | "ok";
};

export const PANIC_DISCLAIMER =
  "Esto NO es la alerta sísmica. Es para una emergencia del inmueble (incendio, intrusión, fuga). Requiere la confirmación de una segunda persona.";

export function panicStatusFromVote(vote: PanicVoteOut): PanicStatus {
  if (vote.status === "activated") {
    return {
      phase: "activated",
      title: "ALARMA ACTIVADA",
      detail: "Dos personas confirmaron. La sirena del inmueble se activó.",
      tone: "crit",
    };
  }
  if (vote.status === "discarded") {
    return {
      phase: "discarded",
      title: "VOTO DESCARTADO",
      detail: "Su ubicación está fuera del inmueble; el voto no se contó.",
      tone: "warn",
    };
  }
  return {
    phase: "counted",
    title: `${vote.distinct_voters} DE 2 CONFIRMACIONES`,
    detail:
      vote.remaining > 0
        ? `Falta ${vote.remaining} confirmación de otra persona (ventana de ${vote.window_s} s).`
        : "Quórum alcanzado.",
    tone: "warn",
  };
}

/** Segundos restantes de la ventana desde que se contó el voto propio. */
export function windowRemaining(votedAtMs: number, windowS: number, nowMs: number): number {
  return Math.max(0, Math.ceil(windowS - (nowMs - votedAtMs) / 1000));
}
