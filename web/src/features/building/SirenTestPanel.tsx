// Prueba de sirena (T-1.35). El único control del SOC que toca un actuador de vida.
//
// Cuatro invariantes, en orden de importancia:
//  1. El botón solo existe si `me.allowed_actions.siren_test` (RBAC §2).
//  2. Confirmación en dos pasos (ConfirmButton, RBAC §4.3).
//  3. **Nunca se afirma que la sirena suena sin el `command_ack` del edge.** Un 201
//     dice "el comando salió", no "el actuador se movió" (regla de oro 8).
//  4. Sin acuse en el TTL, se dice SIN RESPUESTA DEL GABINETE — no "activada".

import { Siren } from "lucide-react";

import ConfirmButton from "../../components/ConfirmButton";
import { utcClock } from "../../lib/time";
import type { SirenPhase, SirenTestData } from "./useSirenTest";

/** Lo que el operador puede creer en cada fase. Nada de esto es decorativo. */
const PHASE_COPY: Record<SirenPhase, { text: string; kind: string }> = {
  idle: { text: "SIRENA EN REPOSO", kind: "soc-pill--edge" },
  issued: { text: "COMANDO EMITIDO · ESPERANDO ACUSE DEL GABINETE", kind: "soc-pill--warn" },
  acked: { text: "SIRENA SONANDO · ACUSADA POR EL EDGE", kind: "soc-pill--crit" },
  rejected: { text: "COMANDO RECHAZADO POR EL GABINETE", kind: "soc-pill--warn" },
  expired: { text: "SIN RESPUESTA DEL GABINETE · LA SIRENA NO SE ACTIVÓ", kind: "soc-pill--warn" },
  failed: { text: "EL COMANDO NO SALIÓ", kind: "soc-pill--warn" },
};

export interface SirenTestPanelProps {
  siren: SirenTestData;
  /** `me.allowed_actions.siren_test`. Sin él, el panel no se monta. */
  canTest: boolean;
}

export default function SirenTestPanel({ siren, canTest }: SirenTestPanelProps) {
  if (!canTest) return null;
  const copy = PHASE_COPY[siren.phase];
  const acked = siren.phase === "acked";

  return (
    <section className="bld__card" data-testid="siren-panel">
      <header className="bld__cardhd">
        <Siren size={13} />
        <h2>PRUEBA DE SIRENA</h2>
      </header>

      <p className={`soc-pill ${copy.kind}`} data-testid="siren-phase" role="status">
        {copy.text}
      </p>

      {siren.detail !== null && (
        <p className="soc-stateframe__error" data-testid="siren-detail">
          {siren.detail}
        </p>
      )}

      {siren.command !== null && (
        <p className="soc-mono soc-screen__sub">
          {siren.command.action.toUpperCase()} · nonce {siren.command.nonce.slice(0, 8)} ·{" "}
          {utcClock(Date.parse(siren.command.issued_at))} UTC
        </p>
      )}

      <div className="bld__actions">
        {acked ? (
          <ConfirmButton
            label="SILENCIAR SIRENA"
            variant="secondary"
            disabled={siren.pending}
            onConfirm={siren.deactivate}
          />
        ) : (
          <ConfirmButton
            label="PROBAR SIRENA"
            icon={<Siren size={13} />}
            disabled={siren.pending || siren.phase === "issued"}
            onConfirm={siren.activate}
          />
        )}
        {(siren.phase === "expired" || siren.phase === "rejected" || siren.phase === "failed") && (
          <button type="button" className="soc-btn soc-btn--secondary" onClick={siren.reset}>
            DESCARTAR
          </button>
        )}
      </div>
    </section>
  );
}
