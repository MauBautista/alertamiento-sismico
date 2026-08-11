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
//  2. `alertActive`: de dónde salía «la sirena sigue activa» cuando el acuse no
//     lo traía — porque hasta T-2.116 NUNCA lo traía.
//
// [T-2.116] EL ACUSE YA TRAE EL RELÉ, y manda sobre todo lo demás.
//
// `sirenStillOn()` sondeaba `ack.siren ?? ack.relay_state ?? ack.state`: TRES
// campos que no existían en ningún contrato. El gabinete mandaba `{channel,
// action, success, latency_s, executed_at, detail, results}` con
// `detail="relay"`, así que esa rama era código muerto y lo que sostenía la
// pantalla era el respaldo (2), una INFERENCIA a partir de la fase del sitio.
//
// Desde el schema compartido 1.11.0 el acuse transporta `channel_state`: el
// estado del canal TRAS EL ARBITRAJE de demandas del gabinete
// (`edge/takab_edge/gpio/__init__.py::_desired_energized`), persistido por
// `handle_command_ack` en `commands.ack`. Es literalmente lo que pide la spec
// §2.2 — «el resultado real llega en el `command_ack` con el estado recalculado
// del relé»— y por eso se LEE en vez de deducirse.
//
// El respaldo (2) sigue vivo, y a propósito: un gabinete que aún no se ha
// re-desplegado no manda el campo, y entonces la pantalla explica lo que sí
// sabe (hay una alerta vigente) nombrando esa fuente, en lugar de afirmar un
// relé que nadie midió.
import type { ChannelState, CommandOut } from "@takab/sdk";

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

/**
 * [T-2.116] El estado del canal `siren` TRAS EL ARBITRAJE, tal cual lo declara
 * el gabinete. `null` = el acuse no lo trae (firmware anterior al schema
 * 1.11.0, ack de rechazo sin ejecución) — que NO es «el relé está en reposo».
 */
function sirenChannelState(ack: Record<string, unknown> | null): ChannelState | null {
  if (ack === null || typeof ack.channel_state !== "object" || ack.channel_state === null) {
    return null;
  }
  const state = ack.channel_state as Partial<ChannelState>;
  return typeof state.activated === "boolean" && state.channel === "siren"
    ? (state as ChannelState)
    : null;
}

/** POR QUÉ sigue energizada, con las palabras del gabinete (`SirenReason`). */
function sostenidaPor(reason: string | null): string {
  if (reason === "alert") {
    return "una alerta vigente";
  }
  if (reason === "test") {
    return "una prueba en curso";
  }
  if (reason === "safe_state") {
    return "el estado seguro del gabinete";
  }
  return "otra demanda del gabinete";
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
  // [T-2.116] acked: MANDA EL RELÉ que el gabinete recalculó, no la fase ni la
  // intención. Es el único hecho medido en el sitio, y llega dentro del acuse.
  const rele = sirenChannelState(command.ack);
  if (rele !== null) {
    if (silencing && rele.activated) {
      return {
        phase: "acked",
        title: "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
        detail: `El gabinete acusó el retiro de su demanda manual y, con el estado recalculado, declara el relé de la sirena TODAVÍA ENERGIZADO: lo sostiene ${sostenidaPor(rele.reason)}. Solo se apagará cuando esa demanda cese.`,
        tone: "warn",
      };
    }
    if (!silencing && !rele.activated) {
      // El otro lado del mismo hecho: la orden viajó y el relé NO quedó
      // energizado. Antes esto se pintaba «SIRENA ACTIVADA» sin más.
      return {
        phase: "acked",
        title: "EL COMANDO SE EJECUTÓ · LA SIRENA NO QUEDÓ ACTIVA",
        detail:
          "El gabinete acusó la ejecución, pero declara el relé de la sirena EN REPOSO. Verifique el estado real en el sitio: la alarma audible no está sonando.",
        tone: "crit",
      };
    }
    return {
      phase: "acked",
      title: silencing ? "SIRENA SILENCIADA" : "SIRENA ACTIVADA",
      detail: silencing
        ? "El gabinete confirmó el retiro de su demanda y declara el relé de la sirena EN REPOSO."
        : "El gabinete confirmó la ejecución y declara el relé de la sirena ENERGIZADO.",
      tone: silencing ? "ok" : "crit",
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
