// Banner del SIMULACRO (T-1.60): rotulado NO-real, jamás confundible con la
// alerta. PRECEDENCIA: con un incidente vivo el frame real domina — este banner
// se degrada a un badge discreto (lo real siempre gana, también visualmente).

import { AlertTriangle } from "lucide-react";

import { useSessionStore } from "../../auth/session.store";
import { utcClock } from "../../lib/time";
import { useActiveDrill } from "./useActiveDrill";

export default function DrillBanner({ hasLiveIncident }: { hasLiveIncident: boolean }) {
  const canStart = useSessionStore((s) => s.me?.allowed_actions.drill_start === true);
  const { drill, start, stop, pending, error } = useActiveDrill();

  if (drill === null) {
    // Sin drill: solo quien puede iniciarlo ve el control (gate de matriz).
    if (!canStart) return null;
    return (
      <div className="soc-drill soc-drill--idle" data-testid="drill-idle">
        {/* En reposo, un botón fantasma en una tira: el alto es del mapa. */}
        <button
          type="button"
          className="soc-btn soc-btn--ghost"
          disabled={pending}
          onClick={() => start(300)}
          title="Banner NO-real + voceo en todos los gabinetes del tenant; cero relés"
        >
          INICIAR SIMULACRO (5 MIN)
        </button>
        {error && <span className="soc-meta">{error}</span>}
      </div>
    );
  }

  const endsAt = Date.parse(drill.started_at) + drill.duration_s * 1000;
  if (hasLiveIncident) {
    return (
      <span className="soc-pill soc-pill--warn" data-testid="drill-badge">
        SIMULACRO EN CURSO (LA ALERTA REAL DOMINA)
      </span>
    );
  }
  return (
    <div className="soc-drill soc-drill--on" role="status" data-testid="drill-banner">
      <AlertTriangle size={16} aria-hidden />
      <span>
        🔶 SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL · {drill.sites.length} SITIO(S) · TERMINA{" "}
        {utcClock(endsAt)} UTC
      </span>
      {canStart && (
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={pending}
          onClick={() => stop(drill.drill_id)}
        >
          TERMINAR
        </button>
      )}
    </div>
  );
}
