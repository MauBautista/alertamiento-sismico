// Autodiagnóstico del gabinete (T-1.59 · cierra M-2). Mismo contrato de verdad
// que useSirenTest: un `201` significa "el comando firmado salió", NO "el test
// corrió" — solo el `command_ack` del edge (con `results` por relé) resuelve.
// El edge pulsa los relés NO audibles con readback; la sirena jamás suena.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import {
  issueCommandSitesSiteIdCommandsPost,
  listCommandsSitesSiteIdCommandsGet,
} from "@takab/sdk";
import type { CommandOut } from "@takab/sdk";

export const SELF_TEST_POLL_MS = 2_000;

export type SelfTestPhase = "idle" | "issued" | "acked" | "rejected" | "expired" | "failed";

export interface RelayCheck {
  pulsed: boolean;
  readback_ok: boolean;
}

export interface SelfTestData {
  phase: SelfTestPhase;
  command: CommandOut | null;
  /** Motivo cuando la fase es rejected/failed (p.ej. "alerta viva"). */
  detail: string | null;
  /** Chips por relé del ack (`ack.results.relays`); null hasta el acuse. */
  relays: Record<string, RelayCheck> | null;
  run: () => void;
  reset: () => void;
  pending: boolean;
}

function phaseOf(command: CommandOut | null): SelfTestPhase {
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

export function useSelfTest(siteId: string | null): SelfTestData {
  const queryClient = useQueryClient();
  const [commandId, setCommandId] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // Poll SOLO con un comando en vuelo (logging por evento, regla de oro 10).
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
      return mine && mine.status === "pending" ? SELF_TEST_POLL_MS : false;
    },
  });

  const command =
    commandId === null
      ? null
      : ((listing.data?.items ?? []).find((c) => c.command_id === commandId) ?? null);

  const mutation = useMutation({
    mutationFn: async () => {
      const { data, response } = await issueCommandSitesSiteIdCommandsPost({
        path: { site_id: siteId as string },
        body: { channel: "system", action: "self_test" },
      });
      if (data === undefined) {
        throw new Error(`El autodiagnóstico no salió (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: async (created) => {
      setFailure(null);
      setCommandId(created.command_id);
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

  const phase: SelfTestPhase = failure !== null ? "failed" : phaseOf(command);
  const ack = (command?.ack ?? null) as {
    results?: { relays?: Record<string, RelayCheck> };
  } | null;

  return {
    phase,
    command,
    detail: failure ?? (ack as { detail?: string } | null)?.detail ?? command?.error ?? null,
    relays: ack?.results?.relays ?? null,
    run: () => mutation.mutate(),
    reset,
    pending: mutation.isPending,
  };
}
