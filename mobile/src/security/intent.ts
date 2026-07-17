// String CANÓNICO de la intención firmada (T-2.09 · spec §2.1-B). Espejo
// EXACTO de api/commands/intent.py::canonical_intent — cambiarlo aquí sin
// versionar el servidor rompe TODA verificación (v2, jamás mutar v1).
export const INTENT_V1 = "takab-intent-v1";

export function canonicalIntent(args: {
  keyId: string;
  siteId: string;
  channel: string;
  action: "activate" | "deactivate";
  nonce: string;
}): string {
  return `${INTENT_V1}:${args.keyId}:${args.siteId}:${args.channel}:${args.action}:${args.nonce}`;
}
