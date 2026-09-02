import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import CatalogPanel from "./CatalogPanel";
import { FalsePositiveRate } from "./ClassificationPanel";
import InspectionMatrix from "./InspectionMatrix";
import TriageDetail from "./TriageDetail";
import TriageTable from "./TriageTable";
import { inspectionMatrix } from "./priority";
import { useCctv } from "./useCctv";
import { useForensics } from "./useForensics";
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
 * T-1.29 · Evaluación Estructural Post-Sismo (mockup 3, TriageHistory.jsx).
 *
 * Desviaciones honestas ratificadas frente al mockup:
 * - Rango de fechas REAL del servidor (T-1.57/58: `GET /incidents?from&to`) con
 *   date-pickers, en vez de los presets 7d/30d/90d del mockup. La cuenta muestra
 *   lo realmente cargado y "CARGAR MÁS" pagina por keyset (`next_cursor`).
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
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const [selected, setSelected] = useState<TriageRow | null>(null);

  const triage = useTriage({ severity, q, from, to });
  const me = useSessionStore((s) => s.me);
  const now = useNow(5000);

  // T-1.51: deep-link ?incident=<id> desde la consola (SOLICITAR DICTAMEN):
  // preselecciona esa fila UNA vez cuando el historial carga. Si no está en la
  // página cargada se avisa (el endpoint pagina a 50) y se cae a la más reciente.
  const [searchParams] = useSearchParams();
  const wantedIncident = searchParams.get("incident");
  const appliedDeepLink = useRef(false);
  const deepLinkMiss =
    wantedIncident !== null &&
    triage.rows.length > 0 &&
    !triage.rows.some((r) => r.incident.incident_id === wantedIncident);
  useEffect(() => {
    if (appliedDeepLink.current || wantedIncident === null || triage.rows.length === 0) {
      return;
    }
    appliedDeepLink.current = true;
    const row = triage.rows.find((r) => r.incident.incident_id === wantedIncident);
    if (row !== undefined) {
      setSelected(row);
    }
  }, [wantedIncident, triage.rows]);

  // La selección sobrevive a un refetch: se re-resuelve por id contra las filas.
  const current =
    triage.rows.find((r) => r.incident.incident_id === selected?.incident.incident_id) ??
    triage.rows[0] ??
    null;

  const detail = useIncidentDetail(
    current?.incident.incident_id ?? null,
    current?.incident.event_id ?? null,
  );
  const forensics = useForensics(current?.incident.incident_id ?? null);
  // [T-3.12.c] CCTV: misma cadencia y mismo reloj de frescura que forensics.
  const cctv = useCctv(current?.incident.incident_id ?? null);

  // [T-2.40] Sitios del MISMO evento, ordenados por prioridad. Se derivan de las
  // filas YA cargadas —incidentes del propio tenant, ya filtrados por RLS—: un
  // endpoint nuevo podría discrepar de lo que la tabla está mostrando.
  const matrix = useMemo(
    () =>
      inspectionMatrix(triage.rows, current?.incident.event_id ?? null, (siteId) =>
        triage.criticalityOf(siteId),
      ),
    [triage, current],
  );

  const staleSince =
    !triage.loading &&
    !triage.error &&
    triage.dataUpdatedAt > 0 &&
    now - triage.dataUpdatedAt > TRIAGE_STALE_MS
      ? triage.dataUpdatedAt
      : null;

  return (
    <section className="triage" data-screen-label="03 Evaluación Estructural">
      <header className="triage__hd">
        <div>
          <span className="soc-meta">PROTECCIÓN CIVIL · EVIDENCIA INMUTABLE</span>
          <h1 className="triage__title">Evaluación Estructural Post-Sismo</h1>
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
          <div className="triage__dates">
            <input
              type="date"
              aria-label="Desde (fecha de apertura)"
              value={from ?? ""}
              max={to ?? undefined}
              onChange={(e) => setFrom(e.target.value || null)}
            />
            <span aria-hidden>—</span>
            <input
              type="date"
              aria-label="Hasta (fecha de apertura)"
              value={to ?? ""}
              min={from ?? undefined}
              onChange={(e) => setTo(e.target.value || null)}
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
            {/* [T-2.59] El rótulo se pinta FUERA del StateFrame, así que sin esta
                puerta anunciaba "0 INCIDENTES CARGADOS" junto al propio mensaje
                de error. Cero incidentes tras un sismo es la afirmación más
                tranquilizadora de esta pantalla: no se hace sin dato (G7). */}
            <span className="soc-meta">
              {triage.loading || triage.error !== null
                ? "SIN DATO · HISTORIAL NO DISPONIBLE"
                : `${triage.rows.length} INCIDENTES CARGADOS · MÁS RECIENTES PRIMERO`}
            </span>
            {deepLinkMiss && (
              <span className="soc-meta triage__deeplink-miss" role="status">
                EL INCIDENTE SOLICITADO NO ESTÁ EN LA PÁGINA CARGADA
              </span>
            )}
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
          {triage.hasMore && (
            <button
              type="button"
              className="soc-btn soc-btn--secondary triage__more"
              onClick={triage.loadMore}
              disabled={triage.loadingMore}
            >
              {triage.loadingMore ? "CARGANDO MÁS…" : "CARGAR MÁS"}
            </button>
          )}
          <InspectionMatrix
            rows={matrix}
            selectedId={current?.incident.incident_id ?? null}
            onSelect={(id) => {
              const row = triage.rows.find((r) => r.incident.incident_id === id);
              if (row) setSelected(row);
            }}
          />
          {/* [T-5.12] La métrica que decide si el cliente renueva, y que hasta
              hoy no era calculable ni a mano sobre la base. */}
          <FalsePositiveRate />
          <CatalogPanel />
        </div>

        {current && (
          <TriageDetail
            row={current}
            detail={detail}
            forensics={forensics}
            cctv={cctv}
            minNodes={triage.minNodesFor(current.incident.site_id)}
            // [T-2.82.a] La misma edad que fecha el HISTORIAL: la fila del
            // incidente sale de esa consulta y de ninguna otra, así que el panel
            // del quórum —que sin evento asociado no habla del evento sino del
            // incidente— tiene que fechar con este reloj y no inventarse otro.
            incidentStaleSince={staleSince}
            canSign={me?.allowed_actions.sign_dictamen === true}
            canExport={me?.allowed_actions.export === true}
            canDownloadClip={me?.allowed_actions.cctv_video === true}
            canGenerateReport={me?.allowed_actions.generate_report === true}
          />
        )}
      </div>
    </section>
  );
}
