// Triage Estructural (T-2.10): los reportes de daños que el táctico levantó en
// campo (2.4), con sus evidencias forenses y la verificación de hash bajo
// demanda. "Personas en riesgo" se resalta y ordena al frente.
import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import { orderedDamageReports, verifyLabel, type VerifyState } from "./structural";
import { useDamageReports, useVerifyEvidence } from "./useDamageReports";

function EvidenceVerifier({ evidenceId }: { evidenceId: string }) {
  const verify = useVerifyEvidence();
  const [state, setState] = useState<VerifyState>("idle");

  const run = () => {
    setState("verifying");
    verify.mutate(evidenceId, {
      onSuccess: (res) => setState(res.verified ? "verified" : "tampered"),
      onError: () => setState("error"),
    });
  };

  const cls =
    state === "verified" ? "ok" : state === "tampered" || state === "error" ? "crit" : "muted";

  return (
    <button
      className={`structural-verify structural-verify--${cls}`}
      disabled={state === "verifying"}
      onClick={run}
      type="button"
      data-testid={`verify-${evidenceId}`}
    >
      <span className="structural-verify__id">{evidenceId.slice(0, 8)}</span>
      <span className="structural-verify__state">{verifyLabel(state)}</span>
    </button>
  );
}

export default function StructuralTriage({ incidentId }: { incidentId: string }) {
  const { reports, loading, error } = useDamageReports(incidentId);
  const ordered = reports ? orderedDamageReports(reports) : [];

  return (
    <section className="structural" data-testid="structural-triage">
      <h3 className="structural__title">TRIAGE ESTRUCTURAL · REPORTES DE CAMPO</h3>
      <StateFrame
        label="Triage estructural"
        loading={loading}
        error={error}
        empty={reports !== undefined && ordered.length === 0}
        emptyText="Sin reportes de daños para este incidente."
      >
        <ul className="structural__list">
          {ordered.map((r) => (
            <li
              className={`structural-card${r.urgent ? " structural-card--urgent" : ""}`}
              key={r.reportId}
              data-testid={`report-${r.reportId}`}
            >
              {r.urgent && (
                <div className="structural-card__urgent" data-testid={`urgent-${r.reportId}`}>
                  PERSONAS EN RIESGO · SOC NOTIFICADO
                </div>
              )}
              <div className="structural-card__cats">
                {r.categories.map((c) => (
                  <span className={`structural-cat structural-cat--${c.severity}`} key={c.key}>
                    {c.label} · {c.severity.toUpperCase()}
                  </span>
                ))}
              </div>
              {r.notes && <p className="structural-card__notes">{r.notes}</p>}
              <div className="structural-card__meta">{utcStamp(Date.parse(r.createdAt))} UTC</div>
              {r.evidenceIds.length > 0 ? (
                <div className="structural-card__evidence">
                  {r.evidenceIds.map((id) => (
                    <EvidenceVerifier evidenceId={id} key={id} />
                  ))}
                </div>
              ) : (
                <div className="structural-card__noevidence">Sin evidencia fotográfica.</div>
              )}
            </li>
          ))}
        </ul>
      </StateFrame>
    </section>
  );
}
