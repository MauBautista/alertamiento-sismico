// Prueba de sirena desde la nube (T-1.35). Superficie MÁS sensible del sistema.
//
// Regla de oro 8: el comando va firmado (HMAC), con nonce y TTL, y **no vale nada
// hasta que el gabinete responde**. Un `201 Created` significa "el comando salió",
// NO "la sirena sonó". Este hook nunca colapsa esos dos hechos: mientras el edge no
// mande su `command_ack`, el estado es EMITIDO, no SONANDO.
//
// Si el gabinete está sin enlace, el comando expira por TTL y la UI lo dice. Pintar
// "SIRENA ACTIVADA" en ese caso sería mentirle al operador sobre un actuador de vida.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import {
  issueCommandSitesSiteIdCommandsPost,
  listCommandsSitesSiteIdCommandsGet,
} from "@takab/sdk";
import type { CommandOut } from "@takab/sdk";

/** Cadencia del sondeo mientras hay un comando en vuelo. */
export const COMMAND_POLL_MS = 2_000;

export type SirenPhase =
  | "idle"
  /** El comando salió firmado; el gabinete todavía no ha acusado. */
  | "issued"
  /** El edge confirmó la ejecución: la sirena está sonando de verdad. */
  | "acked"
  /** El edge rechazó el comando (nonce repetido, canal deshabilitado…). */
  | "rejected"
  /** Venció el TTL sin acuse: el gabinete no respondió. */
  | "expired"
  /** No pudimos ni emitirlo (403, rate-limit, sin clave HMAC…). */
  | "failed";

export interface SirenTestData {
  phase: SirenPhase;
  /** El comando en vuelo o el último resuelto. */
  command: CommandOut | null;
  /** Motivo cuando `phase` es `rejected` o `failed`. */
  detail: string | null;
  activate: () => void;
  deactivate: () => void;
  reset: () => void;
  pending: boolean;
}

function phaseOf(command: CommandOut | null): SirenPhase {
  if (command === null) return "idle";
  switch (command.status) {
    case "pending":
      return "issued";
    case "acked":
      return "acked";
    case "rejected":
      return "rejected";
    case "expired":
      return "expired";
    default:
      return "issued";
  }
}

export function useSirenTest(siteId: string | null): SirenTestData {
  const queryClient = useQueryClient();
  const [commandId, setCommandId] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // Solo sondeamos mientras hay un comando en vuelo: logging por evento, no por
  // intervalo (regla de oro 10). En cuanto se resuelve, el polling se apaga.
  const listing = useQuery({
    queryKey: ["siteCommands", siteId],
    queryFn: async () => {
      const { data, response } = await listCommandsSitesSiteIdCommandsGet({
        path: { site_id: siteId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /sites/${siteId}/commands falló (${response.status})`);
      }
      return data;
    },
    enabled: siteId !== null && commandId !== null,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const mine = items.find((c) => c.command_id === commandId);
      return mine && mine.status === "pending" ? COMMAND_POLL_MS : false;
    },
  });

  const command =
    commandId === null
      ? null
      : ((listing.data?.items ?? []).find((c) => c.command_id === commandId) ?? null);

  const mutation = useMutation({
    mutationFn: async (action: "activate" | "deactivate") => {
      const { data, response } = await issueCommandSitesSiteIdCommandsPost({
        path: { site_id: siteId as string },
        body: { channel: "siren", action },
      });
      if (data === undefined) {
        throw new Error(`El comando no salió (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: async (created) => {
      setFailure(null);
      setCommandId(created.command_id);
      // Sembramos la fila recién creada para no depender del primer poll.
      await queryClient.invalidateQueries({ queryKey: ["siteCommands", siteId] });
    },
    onError: (err: Error) => {
      setCommandId(null);
      setFailure(err.message);
    },
  });

  const reset = useCallback(() => {
    setCommandId(null);
    setFailure(null);
  }, []);

  const phase: SirenPhase = failure !== null ? "failed" : phaseOf(command);

  return {
    phase,
    command,
    detail: failure ?? command?.error ?? null,
    activate: () => mutation.mutate("activate"),
    deactivate: () => mutation.mutate("deactivate"),
    reset,
    pending: mutation.isPending,
  };
}
