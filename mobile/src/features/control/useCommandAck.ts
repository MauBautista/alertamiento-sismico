// [T-2.107] SEGUIMIENTO DEL ACUSE hasta un estado terminal, con TECHO.
//
// El `CommandOut` de la respuesta 201 SIEMPRE nace `pending`
// (`api/src/takab_api/queries/commands.py` — el INSERT no lleva `status`, así
// que toma el default de la tabla). Quedarse con esa fila y no volver a
// preguntar es pintar «esperando» para siempre: la regla de oro 7 al revés.
//
// POR QUÉ SONDEO REST Y NO UN CANAL NUEVO. El acuse no viaja por el WS: la
// unión `ServerFrame` (`shared/sdk-ts/src/ws.ts`) es
// `ready|error|incident|incident_action|site_state|features|roster` — no hay
// `command_ack`. Y no hace falta inventarlo: `GET /sites/{site_id}/commands`
// YA existe (`api/src/takab_api/routers/commands.py`), ya está en el SDK, y
// además hace de lápida: en cada consulta ejecuta el `EXPIRE_SITE` que marca
// `expired` a los pendientes vencidos. O sea que preguntar es justo lo que
// hace que el servidor resuelva la espera, en vez de dejarla colgada.
//
// DE DÓNDE SALE EL TECHO. Del TTL REAL del propio comando, medido en tiempo
// del SERVIDOR: `expires_at - issued_at` (hoy 30 s —
// `api/src/takab_api/settings.py`, `command_ttl_s`). Se restan dos instantes
// del mismo reloj, así que el desfase entre el teléfono y el servidor no entra
// en la cuenta; luego esa DURACIÓN se cuenta desde el instante local en que
// llegó la 201. Encima se añade una gracia de un par de sondeos, porque el
// servidor sólo marca `expired` cuando alguien pregunta. Pasado el techo sin
// respuesta terminal, la espera se DECLARA vencida — jamás un giro eterno.
import { listCommandsSitesSiteIdCommandsGet, type CommandOut } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

/** Cadencia del sondeo del acuse. Un comando de sirena se vive de pie frente
 *  al gabinete: 2 s es lo que tarda la pantalla en enterarse, y con un TTL de
 *  30 s son ~17 consultas como mucho — acotadas por el techo, no infinitas. */
export const ACK_POLL_MS = 2_000;

/** Gracia sobre el TTL: el `expired` lo escribe el servidor cuando alguien
 *  pregunta, así que hay que dejar pasar un par de sondeos DESPUÉS del
 *  vencimiento para que la lápida llegue de vuelta antes de rendirse. */
export const ACK_GRACE_MS = 5_000;

/** Sólo si el comando no trae marcas de tiempo legibles (contrato roto). Es el
 *  mismo 30 s de `Settings.command_ttl_s`, y se declara aquí por qué. */
export const ACK_FALLBACK_TTL_MS = 30_000;

export type CommandAckTracking = {
  /** El comando MÁS FRESCO que se conoce: el del servidor si ya contestó, y
   *  si no la 201 (que es verdad: se emitió y está pendiente). */
  command: CommandOut;
  /** Venció el techo sin estado terminal. NO es «expiró»: eso lo dice el
   *  servidor. Esto es «la app no pudo confirmar nada», y se pinta distinto. */
  unconfirmed: boolean;
  /** Techo declarado, en segundos, para que la espera se pueda ROTULAR. */
  waitCeilingS: number;
};

/** Techo de la espera en ms, derivado del TTL del propio comando. */
export function ackCeilingMs(command: CommandOut): number {
  const ttl = Date.parse(command.expires_at) - Date.parse(command.issued_at);
  const usable = Number.isFinite(ttl) && ttl > 0 ? ttl : ACK_FALLBACK_TTL_MS;
  return usable + ACK_GRACE_MS;
}

function isTerminal(command: CommandOut): boolean {
  return command.status !== "pending";
}

/**
 * Sigue el acuse del comando recién emitido hasta `acked`/`rejected`/`expired`
 * o hasta el techo. `null` mientras no se haya emitido nada.
 */
export function useCommandAck(args: {
  siteId: string | null;
  issued: CommandOut | null;
}): CommandAckTracking | null {
  const issued = args.issued;
  const siteId = args.siteId;
  const commandId = issued?.command_id ?? null;
  const ceilingMs = issued === null ? 0 : ackCeilingMs(issued);

  // El techo se ata AL COMANDO, no a un booleano suelto: así emitir otro
  // comando reinicia la espera sin `setState` síncrono en el effect (regla
  // react-hooks v6) y sin arrastrar el veredicto del anterior.
  const [waitOverFor, setWaitOverFor] = useState<string | null>(null);
  useEffect(() => {
    if (commandId === null) {
      return;
    }
    const t = setTimeout(() => setWaitOverFor(commandId), ceilingMs);
    return () => clearTimeout(t);
  }, [commandId, ceilingMs]);
  const waitOver = waitOverFor !== null && waitOverFor === commandId;

  const seguimiento = useQuery({
    queryKey: ["command-ack", siteId, commandId],
    enabled: commandId !== null && siteId !== null && !waitOver,
    queryFn: async () => {
      const res = await listCommandsSitesSiteIdCommandsGet({
        path: { site_id: siteId as string },
      });
      if (!res.data) {
        throw new Error("no se pudo consultar el acuse del comando");
      }
      // `null` = el servidor no lo lista (aún). No es un estado terminal:
      // se sigue esperando con lo que se sabe, hasta el techo.
      return res.data.items.find((c) => c.command_id === commandId) ?? null;
    },
    // Se deja de sondear en cuanto hay veredicto: no se martillea al servidor
    // por un comando que ya terminó su ciclo.
    refetchInterval: (query) =>
      query.state.data != null && isTerminal(query.state.data) ? false : ACK_POLL_MS,
    // El techo manda sobre cualquier política de reintento: un fallo de red
    // se vuelve a intentar en el sondeo siguiente, y si nunca cede, la espera
    // vence y se declara.
    retry: false,
  });

  if (issued === null) {
    return null;
  }
  const command = seguimiento.data ?? issued;
  return {
    command,
    unconfirmed: waitOver && !isTerminal(command),
    waitCeilingS: Math.round(ceilingMs / 1000),
  };
}
