// Triage Estructural (T-2.10): los reportes de daños que el táctico levantó en
// campo (2.4), con sus evidencias forenses y la verificación de hash bajo
// demanda. "Personas en riesgo" se resalta y ordena al frente.
import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import EvidenceVerifier from "./EvidenceVerifier";
import { orderedDamageReports } from "./structural";
import { useDamageReports } from "./useDamageReports";

export default function StructuralTriage({ incidentId }: { incidentId: string }) {
  const { reports, loading, error, staleSince } = useDamageReports(incidentId);
  const ordered = reports ? orderedDamageReports(reports) : [];

  return (
    <section className="structural" data-testid="structural-triage">
      <h3 className="structural__title">EVALUACIÓN DE CAMPO · REPORTES DEL TÁCTICO</h3>
      <StateFrame
        label="Evaluación de campo"
        loading={loading}
        error={error}
        empty={reports !== undefined && ordered.length === 0}
        emptyText="Sin reportes de daños para este incidente."
        // [T-2.82.a] Era el único marco de esta pantalla que ni siquiera
        // DECLARABA la entrada, y callarse que un dato puede envejecer es
        // afirmar que no puede. Estos reportes son los únicos que siguen
        // llegando durante la emergencia: «sin reportes de daños» dicho en
        // presente sobre una lista de hace un cuarto de hora puede significar
        // que nadie ha podido mandarlos.
        staleSince={staleSince}
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
