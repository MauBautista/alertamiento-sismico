// [T-2.32] Actuación comandada por el quórum de red, visible en consola.
//
// Política ratificada 2026-08-03: al confirmar quórum ≥3 el IncidentEngine
// emite comandos de actuación FIRMADOS a los gateways miembro con el actor
// sistema QUORUM_ACTOR_UUID. Este hook resume esos comandos para el incidente
// enfocado; la consola solo PINTA (el estado acked/pending lo transiciona el
// ack real del edge por la ingesta).

import { useQuery } from "@tanstack/react-query";

import { listCommandsSitesSiteIdCommandsGet } from "@takab/sdk";
import type { CommandOut } from "@takab/sdk";

/** Actor sistema del quórum (espejo de api/commands/quorum_actuation.py y 0023). */
export const QUORUM_ACTOR_UUID = "00000000-0000-4000-8000-00000000c092";

export const QUORUM_COMMANDS_POLL_MS = 15_000;

export interface QuorumCommandSummary {
  channels: string[];
  acked: number;
  total: number;
}

/** Resumen puro (exportado para tests sin DOM). null = sin burst de quórum. */
export function summarizeQuorumCommands(
  commands: CommandOut[] | undefined,
  eventId: string | null,
): QuorumCommandSummary | null {
  if (!commands || !eventId) {
    return null;
  }
  const mine = commands.filter((c) => c.issued_by === QUORUM_ACTOR_UUID && c.event_id === eventId);
  if (mine.length === 0) {
    return null;
  }
  return {
    channels: [...new Set(mine.map((c) => c.channel))].sort(),
    acked: mine.filter((c) => c.status === "acked").length,
    total: mine.length,
  };
}

export function useQuorumCommands(
  siteId: string | null,
  eventId: string | null,
): QuorumCommandSummary | null {
  const query = useQuery({
    queryKey: ["site-commands", siteId],
    queryFn: async () => {
      const { data, response } = await listCommandsSitesSiteIdCommandsGet({
        path: { site_id: siteId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /sites/{id}/commands falló (${response.status})`);
      }
      return data.items;
    },
    // Solo con incidente enfocado CON evento: cero polling de fondo.
    enabled: siteId !== null && eventId !== null,
    refetchInterval: QUORUM_COMMANDS_POLL_MS,
  });
  return summarizeQuorumCommands(query.data, eventId);
}
