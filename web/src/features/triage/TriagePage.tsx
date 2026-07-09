import { Search } from "lucide-react";
import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import TriageDetail from "./TriageDetail";
import TriageTable from "./TriageTable";
import { TRIAGE_STALE_MS, useTriage } from "./useTriage";
import { useIncidentDetail } from "./useIncidentDetail";
import type { TriageRow } from "./model";

/** Facetas de severidad = CHECK de ``incidents.severity`` (no las del mockup). */
const SEVERITIES: { id: string | null; lbl: string }[] = [
  { id: null, lbl: "TODOS" },
  { id: "critical", lbl: "CRÍTICOS" },
  { id: "warning", lbl: "ADVERTENCIA" },
  { id: "watch", lbl: "VIGILANCIA" },
  { id: "info", lbl: "NORMAL" },
];

/**
 * T-1.29 · Triage Estructural e Historial (mockup 3, TriageHistory.jsx).
 *
 * Desviaciones honestas ratificadas frente al mockup:
 * - Sin selector de rango (7d/30d/90d/1y): `GET /incidents` no acepta rango de
 *   fechas. Filtrarlo en cliente sólo tocaría la página ya cargada e insinuaría que
 *   el servidor filtró. Se muestra la cuenta de lo realmente cargado.
 * - Sin "EXPORTAR LOTE": no existe endpoint de exportación por lotes.
 * - El buscador filtra por PREFIJO de `event_id` — es lo único que el servidor
 *   sabe buscar (`q`); no busca por epicentro.
 * - Sin cita normativa en el encabezado: "NOM-003-SCT" era una norma de transporte
 *   de materiales peligrosos y el blueprint §9 la retiró; el marco citable real
 *   está por confirmar.
 */
export default function TriagePage() {
  const [severity, setSeverity] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<TriageRow | null>(null);

  const triage = useTriage({ severity, q });
  const me = useSessionStore((s) => s.me);
  const now = useNow(5000);

  // La selección sobrevive a un refetch: se re-resuelve por id contra las filas.
  const current =
    triage.rows.find((r) => r.incident.incident_id === selected?.incident.incident_id) ??
    triage.rows[0] ??
    null;

  const detail = useIncidentDetail(
    current?.incident.incident_id ?? null,
    current?.incident.event_id ?? null,
  );

  const staleSince =
    !triage.loading &&
    !triage.error &&
    triage.dataUpdatedAt > 0 &&
    now - triage.dataUpdatedAt > TRIAGE_STALE_MS
      ? triage.dataUpdatedAt
      : null;

  return (
    <section className="triage" data-screen-label="03 Triage Estructural">
      <header className="triage__hd">
        <div>
          <span className="soc-meta">PROTECCIÓN CIVIL · EVIDENCIA INMUTABLE</span>
          <h1 className="triage__title">Triage Estructural e Historial</h1>
        </div>
        <div className="triage__filters">
          <div className="triage__search">
            <Search size={14} aria-hidden />
            <input
              type="text"
              aria-label="Buscar por prefijo de EVENT_ID"
              placeholder="Buscar por prefijo de EVENT_ID…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <div className="triage__segment">
            {SEVERITIES.map((o) => (
              <button
                type="button"
                key={o.lbl}
                className={`triage__seg-btn${severity === o.id ? " is-active" : ""}`}
                aria-pressed={severity === o.id}
                onClick={() => setSeverity(o.id)}
              >
                {o.lbl}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="triage__grid">
        <div className="triage__tablewrap">
          <div className="triage__tablehd">
            <span className="soc-meta">
              {triage.rows.length} INCIDENTES CARGADOS · MÁS RECIENTES PRIMERO
            </span>
          </div>
          <StateFrame
            label="HISTORIAL"
            loading={triage.loading}
            error={triage.error}
            onRetry={triage.refetch}
            empty={triage.rows.length === 0}
            emptyText="SIN INCIDENTES QUE COINCIDAN CON EL FILTRO"
            staleSince={staleSince}
          >
            <TriageTable
              rows={triage.rows}
              selectedId={current?.incident.incident_id ?? null}
              onSelect={setSelected}
            />
          </StateFrame>
        </div>

        {current && (
          <TriageDetail
            row={current}
            detail={detail}
            minNodes={triage.minNodesFor(current.incident.site_id)}
            canSign={me?.allowed_actions.sign_dictamen === true}
            canExport={me?.allowed_actions.export === true}
            canGenerateReport={me?.allowed_actions.generate_report === true}
          />
        )}
      </div>
    </section>
  );
}
