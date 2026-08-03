// [T-2.32] Resumen puro del burst de actuación del quórum de red.

import { describe, expect, it } from "vitest";

import type { CommandOut } from "@takab/sdk";

import { QUORUM_ACTOR_UUID, summarizeQuorumCommands } from "./useQuorumCommands";

function cmd(over: Partial<CommandOut> = {}): CommandOut {
  return {
    ack: null,
    action: "activate",
    channel: "siren",
    command_id: "c-1",
    error: null,
    event_id: "EVT-1",
    expires_at: "2026-08-03T12:01:00Z",
    gateway_id: "g-1",
    issued_at: "2026-08-03T12:00:00Z",
    issued_by: QUORUM_ACTOR_UUID,
    nonce: "n-1",
    site_id: "s-1",
    status: "pending",
    tenant_id: "t-1",
    ...over,
  };
}

describe("summarizeQuorumCommands", () => {
  it("filtra por actor quórum + evento, dedupe canales ordenados y cuenta acks", () => {
    const commands = [
      cmd({ channel: "siren", status: "acked" }),
      cmd({ channel: "strobe", command_id: "c-2", nonce: "n-2" }),
      cmd({ channel: "siren", command_id: "c-3", nonce: "n-3", gateway_id: "g-2" }),
      // comando MANUAL de un operador: jamás se rotula como quórum
      cmd({ channel: "gas_valve", command_id: "c-4", nonce: "n-4", issued_by: "user-uuid" }),
      // otro evento: fuera del resumen
      cmd({ channel: "elevator", command_id: "c-5", nonce: "n-5", event_id: "EVT-2" }),
    ];
    expect(summarizeQuorumCommands(commands, "EVT-1")).toEqual({
      channels: ["siren", "strobe"],
      acked: 1,
      total: 3,
    });
  });

  it("null sin evento enfocado, sin datos o sin burst del actor", () => {
    expect(summarizeQuorumCommands(undefined, "EVT-1")).toBeNull();
    expect(summarizeQuorumCommands([cmd()], null)).toBeNull();
    expect(summarizeQuorumCommands([cmd({ issued_by: "user-x" })], "EVT-1")).toBeNull();
  });
});
