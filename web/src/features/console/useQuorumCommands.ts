// [T-2.32] Actuación comandada por el quórum de red, visible en consola.
//
// Política ratificada 2026-08-03: al confirmar quórum ≥3 el IncidentEngine
// emite comandos de actuación FIRMADOS a los gateways miembro con el actor
// sistema QUORUM_ACTOR_UUID. Este hook resume esos comandos para el incidente
// enfocado; la consola solo PINTA (el estado acked/pending lo transiciona el
// ack real del edge por la ingesta).

import { useQuery } from "@tanstack/react-query";

import { listCommandsSitesSiteIdCommandsGet } from "@takab/sdk";
import type { CommandOut, MeActions } from "@takab/sdk";

import { useSessionStore } from "../../auth/session.store";

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

/**
 * [T-8.08 · A-090 / A-130] ¿Puede este rol LEER los comandos de un sitio?
 *
 * Espejo de `COMMAND_ROLES` (`api/.../routers/commands.py`), la guarda de
 * `GET /sites/{id}/commands`: los roles con ALGUNA acción de comando. Hoy, en la
 * consola, `takab_superadmin`, `tenant_admin`, `building_admin` e `inspector`;
 * NO `soc_operator`, `gov_operator` ni `takab_support`, a los que el hook les
 * disparaba un 403 cada 15 s. No se amplía nada: se deja de pedir lo condenado.
 *
 * Sin sesión, `false` (default-deny).
 */
export function puedeLeerComandos(actions: MeActions | null | undefined): boolean {
  if (!actions) return false;
  return (
    actions.siren_test === true ||
    actions.self_test === true ||
    actions.manual_activate === true ||
    actions.siren_silence === true
  );
}

/**
 * Lo que la consola sabe de la actuación por quórum de un sitio, con la razón
 * cuando no sabe nada. `null` a secas mezclaba tres cosas distintas —«no hubo
 * burst», «tu rol no lo puede leer» y «la lectura falló»— y las tres se pintaban
 * igual: sin fila. Aquí cada una tiene su nombre para que la pantalla que la
 * consuma pueda DECLARARLA.
 */
export type QuorumCommandsView =
  /** El rol no tiene ninguna acción de comando: la petición ni se lanza. */
  | { kind: "sin-permiso" }
  /** Sin sitio o sin evento en foco: no hay burst que buscar. */
  | { kind: "sin-evento" }
  | { kind: "cargando" }
  | { kind: "error"; error: string }
  /** `summary: null` = leído y SIN burst del actor quórum para ese evento. */
  | { kind: "listo"; summary: QuorumCommandSummary | null };

export function useQuorumCommandsView(
  siteId: string | null,
  eventId: string | null,
): QuorumCommandsView {
  const permitido = useSessionStore((s) => puedeLeerComandos(s.me?.allowed_actions));
  const hayQueBuscar = siteId !== null && eventId !== null;
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
    // Solo con incidente enfocado CON evento, y solo si el rol puede leerlo:
    // cero polling de fondo y cero peticiones condenadas a 403.
    enabled: permitido && hayQueBuscar,
    refetchInterval: QUORUM_COMMANDS_POLL_MS,
  });
  if (!permitido) return { kind: "sin-permiso" };
  if (!hayQueBuscar) return { kind: "sin-evento" };
  if (query.data !== undefined) {
    return { kind: "listo", summary: summarizeQuorumCommands(query.data, eventId) };
  }
  if (query.error) return { kind: "error", error: query.error.message };
  return { kind: "cargando" };
}

/**
 * El resumen o `null`, como siempre lo consumió `DetailPanel` (pinta la fila
 * QUÓRUM RED sólo con resumen). Para DECLARAR por qué no hay fila —sin permiso,
 * error— está `useQuorumCommandsView`.
 */
export function useQuorumCommands(
  siteId: string | null,
  eventId: string | null,
): QuorumCommandSummary | null {
  const view = useQuorumCommandsView(siteId, eventId);
  return view.kind === "listo" ? view.summary : null;
}
