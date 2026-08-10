// Lectura HONESTA del ack del comando (spec 2.2): "silenciar" durante una
// alerta vigente NO apaga la sirena — la UI comunica el estado real del relé
// recalculado por el edge, jamás finge éxito. Lógica pura sobre CommandOut.
//
// [T-2.107] Dos añadidos, y los dos son de la regla de oro 7:
//
//  1. `unconfirmed`: la espera tiene TECHO. Un `pending` que nunca resuelve se
//     declara («sin confirmación tras N s»), y se distingue a propósito del
//     `expired` del servidor: uno es «el gabinete no acusó a tiempo, y consta»
//     y el otro es «esta app no pudo enterarse de nada». Pintarlos igual sería
//     atribuirle al gabinete un veredicto que nadie emitió.
//  2. `alertActive`: de dónde sale «la sirena sigue activa» cuando el acuse no
//     lo trae. El acuse REAL de hoy (`api/src/takab_api/ingest/handlers.py`,
//     `handle_command_ack`) persiste `{channel, action, success, latency_s,
//     executed_at, detail, results}` — SIN censo del relé, porque el gabinete
//     tampoco lo manda (`edge/takab_edge/dispatch`, `detail="relay"`). T-2.106
//     lo deja escrito: «la nube no sabe si el relé de la sirena está
//     energizado ahora mismo». Así que el hecho que SÍ se conoce es el otro
//     lado del arbitraje: hay una ALERTA VIGENTE, y su demanda no es la del
//     canal manual que esta persona acaba de retirar. Eso es exactamente lo
//     que la spec §2.2 manda comunicar, y se redacta nombrando su fuente.
import type { CommandOut } from "@takab/sdk";

export type AckPhase = "pending" | "acked" | "rejected" | "expired" | "unconfirmed";

export type AckView = {
  phase: AckPhase;
  title: string;
  detail: string;
  tone: "ok" | "warn" | "crit";
};

/** Lo que la pantalla sabe ADEMÁS del comando, y que el comando no trae. */
export type AckContext = {
  /** Venció el techo de la espera sin veredicto del servidor. */
  unconfirmed?: boolean;
  /** Techo declarado en segundos, para rotular la espera con un número. */
  waitCeilingS?: number;
  /** Hay una alerta vigente en el sitio (`mobile-state.phase ==
   *  "alert_active"`): su demanda de sirena es INDEPENDIENTE del canal manual. */
  alertActive?: boolean;
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

function segundos(ctx: AckContext): string {
  return ctx.waitCeilingS != null && ctx.waitCeilingS > 0 ? `${ctx.waitCeilingS} s` : "el TTL";
}

export function ackView(command: CommandOut, ctx: AckContext = {}): AckView {
  const status = command.status;
  const silencing = command.action === "deactivate";

  // El techo manda sobre el `pending`: la espera no se pinta viva pasado su
  // vencimiento (mostrar un dato congelado como "en curso" es la regla de oro
  // 7 al revés).
  if (ctx.unconfirmed === true && status === "pending") {
    return {
      phase: "unconfirmed",
      title: "SIN CONFIRMACIÓN DEL GABINETE",
      detail: `Pasaron ${segundos(ctx)} y el acuse de ejecución no llegó. NO se sabe si el gabinete ejecutó la orden: verifique el estado real en el sitio antes de repetir el comando.`,
      tone: "crit",
    };
  }
  if (status === "pending") {
    return {
      phase: "pending",
      title: "ESPERANDO CONFIRMACIÓN DEL GABINETE",
      detail: `El comando salió firmado; aguardando el acuse de ejecución del edge (hasta ${segundos(ctx)}).`,
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
  if (silencing && ctx.alertActive === true) {
    return {
      phase: "acked",
      title: "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
      detail:
        "El gabinete ejecutó el retiro de SU demanda manual, pero hay una ALERTA VIGENTE en el sitio y su demanda es otra: el arbitraje mantiene la sirena hasta que la alerta cese.",
      tone: "warn",
    };
  }
  return {
    phase: "acked",
    title: silencing ? "SIRENA SILENCIADA" : "SIRENA ACTIVADA",
    detail: silencing
      ? "El gabinete confirmó el retiro de su demanda y no hay alerta vigente que sostenga la sirena."
      : "El gabinete confirmó la ejecución.",
    tone: silencing ? "ok" : "crit",
  };
}
