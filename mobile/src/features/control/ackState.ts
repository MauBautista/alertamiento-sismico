// Lectura HONESTA del ack del comando (spec 2.2): "silenciar" durante una
// alerta vigente NO apaga la sirena — la UI comunica el estado real del relé
// recalculado por el edge, jamás finge éxito. Lógica pura sobre CommandOut.
import type { CommandOut } from "@takab/sdk";

export type AckView = {
  phase: "pending" | "acked" | "rejected" | "expired";
  title: string;
  detail: string;
  tone: "ok" | "warn" | "crit";
};

/** ¿El relé de sirena quedó realmente sonando tras el ack? El edge devuelve
 *  el estado recalculado del arbitraje en el payload del ack. */
function sirenStillOn(ack: Record<string, unknown> | null): boolean {
  if (ack === null) {
    return false;
  }
  const relay = ack.siren ?? ack.relay_state ?? ack.state;
  return relay === "on" || relay === true || relay === "active";
}

export function ackView(command: CommandOut): AckView {
  const status = command.status;
  const silencing = command.action === "deactivate";

  if (status === "pending") {
    return {
      phase: "pending",
      title: "ESPERANDO CONFIRMACIÓN DEL GABINETE",
      detail: "El comando salió firmado; aguardando el acuse de ejecución del edge.",
      tone: "warn",
    };
  }
  if (status === "rejected") {
    return {
      phase: "rejected",
      title: "EL GABINETE RECHAZÓ EL COMANDO",
      detail: command.error ?? "El edge no ejecutó la acción (revise el estado del sitio).",
      tone: "crit",
    };
  }
  if (status === "expired") {
    return {
      phase: "expired",
      title: "COMANDO EXPIRADO SIN ACUSE",
      detail: "El gabinete no confirmó a tiempo. Vuelva a intentar si sigue siendo necesario.",
      tone: "crit",
    };
  }
  // acked: distinguir "silenciar" que NO apagó por alerta vigente.
  if (silencing && sirenStillOn(command.ack)) {
    return {
      phase: "acked",
      title: "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
      detail:
        "El edge quitó su demanda manual, pero otra demanda (alerta vigente) mantiene la sirena. Solo se apagará cuando cese la alerta.",
      tone: "warn",
    };
  }
  return {
    phase: "acked",
    title: silencing ? "SIRENA SILENCIADA" : "SIRENA ACTIVADA",
    detail: "El gabinete confirmó la ejecución.",
    tone: silencing ? "ok" : "crit",
  };
}
