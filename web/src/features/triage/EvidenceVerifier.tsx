/** [T-7.48] El verificador de una evidencia, sacado de `StructuralTriage`.
 *
 * Vivía anidado allí y no se exportaba, así que el único documento verificable
 * desde la consola era una foto de daños. El dictamen pericial —que es el papel
 * que sale del sistema EN LA MANO de un perito, y el único que alguien va a
 * querer comprobar contra un `sha256sum`— no tenía botón.
 *
 * Sigue siendo el mismo componente y el mismo endpoint; lo único que cambió es
 * que ahora tiene dos consumidores.
 */
import { useState } from "react";

import { useVerifyEvidence } from "./useDamageReports";
import { verifyLabel, type VerifyState } from "./structural";

export default function EvidenceVerifier({ evidenceId }: { evidenceId: string }) {
  const verify = useVerifyEvidence();
  const [state, setState] = useState<VerifyState>("idle");

  const run = () => {
    setState("verifying");
    verify.mutate(evidenceId, {
      onSuccess: (res) =>
        // [T-7.48] Tres desenlaces, no dos. `actual_sha256: null` es «no hay
        // objeto que hashear», no «alguien lo alteró»: ver `verifyLabel`.
        setState(
          res.verified ? "verified" : res.actual_sha256 == null ? "sin-objeto" : "tampered",
        ),
      onError: () => setState("error"),
    });
  };

  // `sin-objeto` NO pinta crítico: no hay nada roto, hay algo que todavía no ha
  // llegado. Pintarlo en rojo sería la misma acusación con otro lenguaje.
  const cls =
    state === "verified" ? "ok" : state === "tampered" || state === "error" ? "crit" : "muted";

  return (
    <button
      className={`structural-verify structural-verify--${cls}`}
      disabled={state === "verifying"}
      title={
        state === "verifying"
          ? "Verificando la evidencia…"
          : "Verifica la integridad de esta evidencia"
      }
      onClick={run}
      type="button"
      data-testid={`verify-${evidenceId}`}
    >
      <span className="structural-verify__id">{evidenceId.slice(0, 8)}</span>
      <span className="structural-verify__state">{verifyLabel(state)}</span>
    </button>
  );
}
