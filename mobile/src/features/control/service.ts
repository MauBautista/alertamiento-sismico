// Orquestación del comando táctico (2.2): nonce del servidor JUSTO antes del
// deslizamiento → firma de la INTENCIÓN con la llave de hardware (prompt
// biométrico) → POST al pipeline existente. El teléfono jamás firma el
// comando ejecutable; cualquier fallo se declara con su causa real.
import {
  issueCommandNonceSitesSiteIdCommandNoncePost,
  issueCommandSitesSiteIdCommandsPost,
  type CommandOut,
} from "@takab/sdk";

import { ensureDeviceKey, signIntent } from "@/security/deviceKey";
import { canonicalIntent } from "@/security/intent";

export type TacticalAction = "activate" | "deactivate";

export type TacticalOutcome =
  | { ok: true; command: CommandOut }
  | { ok: false; reason: string };

const PROMPT: Record<TacticalAction, string> = {
  activate: "Confirme la ACTIVACIÓN MANUAL de la sirena",
  deactivate: "Confirme el retiro de su demanda de sirena",
};

function commandError(status: number | undefined): string {
  if (status === 409) {
    return "Intención repetida (replay rechazado). Solicite un nonce nuevo.";
  }
  if (status === 429) {
    return "Límite de comandos alcanzado. Espere un minuto (rate-limit de seguridad).";
  }
  if (status === 503) {
    return "El servidor no tiene configurada la intención firmada.";
  }
  if (status === 403) {
    return "El servidor rechazó la intención (rol, alcance o firma).";
  }
  return `El servidor rechazó el comando (HTTP ${status ?? "?"}).`;
}

export async function executeTacticalCommand(args: {
  siteId: string;
  action: TacticalAction;
}): Promise<TacticalOutcome> {
  try {
    const key = await ensureDeviceKey();
    if (!key.ok) {
      return { ok: false, reason: key.reason };
    }
    const nonceRes = await issueCommandNonceSitesSiteIdCommandNoncePost({
      path: { site_id: args.siteId },
    });
    if (!nonceRes.data) {
      return { ok: false, reason: commandError(nonceRes.response?.status) };
    }
    const canonical = canonicalIntent({
      keyId: key.keyId,
      siteId: args.siteId,
      channel: "siren",
      action: args.action,
      nonce: nonceRes.data.nonce,
    });
    const signed = await signIntent(canonical, PROMPT[args.action]);
    if (!signed.ok) {
      return { ok: false, reason: signed.reason };
    }
    const cmd = await issueCommandSitesSiteIdCommandsPost({
      path: { site_id: args.siteId },
      body: {
        channel: "siren",
        action: args.action,
        intent: {
          key_id: key.keyId,
          nonce: nonceRes.data.nonce,
          signature: signed.signature,
        },
      },
    });
    if (!cmd.data) {
      return { ok: false, reason: commandError(cmd.response?.status) };
    }
    return { ok: true, command: cmd.data };
  } catch {
    return { ok: false, reason: "Sin conexión con el servidor. El comando NO se emitió." };
  }
}
