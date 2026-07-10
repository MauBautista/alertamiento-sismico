import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  FileDown,
  Printer,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import ConfirmButton from "../../components/ConfirmButton";
import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import QuorumNodes from "./QuorumNodes";
import {
  SIGNABLE_STATUS,
  chainHead,
  durationOf,
  insufficientData,
  isCorroborated,
  isPreliminary,
  magnitudeOf,
  miniseedOf,
  quorumView,
  verdictOf,
} from "./model";
import type { TriageRow } from "./model";
import type { IncidentDetailData, Resource } from "./useIncidentDetail";

const VERDICT_ICON = { crit: AlertOctagon, warn: AlertTriangle, ok: CheckCircle2 } as const;

function Metric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="triage-metric">
      <div className="triage-metric__lbl">{label}</div>
      <div className="triage-metric__val">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}

/** Estado del evento asociado, sin confundir "no hay" con "aún no cargó" o "falló". */
function eventStateOf(
  row: TriageRow,
  event: Resource<unknown>,
): "absent" | "loading" | "error" | "ready" {
  if (row.incident.event_id === null) {
    return "absent";
  }
  if (event.error) {
    return "error";
  }
  if (event.loading || event.data === undefined) {
    return "loading";
  }
  return "ready";
}

/** Cardinal de un recurso que puede no haber llegado: nunca 0 por ausencia. */
function countOf(res: Resource<unknown[]>): string {
  return res.data === undefined ? "S/D" : String(res.data.length);
}

export interface TriageDetailProps {
  row: TriageRow;
  detail: IncidentDetailData;
  minNodes: number | null;
  /** `me.allowed_actions` — server-driven, default-deny. */
  canSign: boolean;
  canExport: boolean;
  canGenerateReport: boolean;
}

/**
 * Detalle del incidente: veredicto, métricas, offsets del quórum, evidencia y
 * cadena de custodia. Port de `triage-detail` del mockup sobre datos reales.
 *
 * Cada panel pinta el estado de SU propia consulta (regla de oro 7): la evidencia,
 * la bitácora y el evento se piden por separado, y una que falle o siga en vuelo
 * jamás se presenta como "0 objetos" / "sin evento".
 *
 * Desviaciones honestas ratificadas:
 * - Sin traza `MiniWaveform` ni "CANAL Z · 200 Hz": el RS4D muestrea a 100 sps y el
 *   waveform crudo no se transmite (regla de oro 9). En su lugar, la evidencia
 *   miniSEED ARCHIVADA del evento confirmado, descargable.
 * - Sin "Firmado HSM": `signed_by` es un uuid de usuario Cognito, no un HSM. Y sin
 *   cita normativa: la etiqueta "NOM-003-SCT" del mockup era errónea (norma de
 *   transporte de materiales peligrosos) y el blueprint §9 la retiró. El marco
 *   citable sigue por confirmar, así que la UI no cita ninguno.
 * - `audit_log` no tiene endpoint de lectura: la bitácora visible es
 *   `incident_actions`, que §9 nombra como evidencia inmutable.
 */
export default function TriageDetail({
  row,
  detail,
  minNodes,
  canSign,
  canExport,
  canGenerateReport,
}: TriageDetailProps) {
  const [status, setStatus] = useState<string>("no_inhabit_inspect");
  const inc = row.incident;
  const { dictamens, actions, evidence, event } = detail;
  const head = chainHead(dictamens.data);
  const verdict = head ? verdictOf(head.status) : null;
  const Icon = verdict ? VERDICT_ICON[verdict.kind] : AlertTriangle;
  const quorum = quorumView(event.data?.quorum_votes);
  const miniseed = miniseedOf(evidence.data);
  const evidenceUnknown = evidence.data === undefined;

  const badge = dictamens.loading
    ? "CARGANDO DICTAMEN…"
    : dictamens.error
      ? "DICTAMEN NO DISPONIBLE"
      : head === null
        ? "SIN DICTAMEN"
        : isPreliminary(head)
          ? "DICTAMEN AUTOMÁTICO PRELIMINAR"
          : "DICTAMEN FIRMADO";

  const miniseedTitle = !canExport
    ? "Requiere la acción export"
    : evidence.loading
      ? "Cargando la evidencia del incidente"
      : evidence.error
        ? "No se pudo cargar la evidencia del incidente"
        : miniseed === null
          ? "No hay miniSEED archivado para este incidente"
          : undefined;

  return (
    <aside className="triage-detail">
      <header className="triage-detail__hd">
        <span className="soc-meta">{badge}</span>
        <h2 className="triage-detail__title">
          {magnitudeOf(row.event)} · {row.siteName}
        </h2>
        <div className="triage-detail__id">
          {inc.event_id ?? inc.incident_id} · {utcStamp(Date.parse(inc.opened_at))} UTC
        </div>
      </header>

      {/* HECHOS del incidente/evento (T-1.52): PGA/PGV/duración/profundidad,
          quórum y evidencia NO dependen de que exista dictamen — antes vivían
          dentro del gate y un incidente sin dictamen parecía "sin datos". */}
      <div className="triage-detail__metrics">
        <Metric
          label="PGA MÁX"
          value={inc.max_pga_g === null ? "—" : inc.max_pga_g.toFixed(3)}
          unit={inc.max_pga_g === null ? undefined : "g"}
        />
        <Metric
          label="PGV MÁX"
          value={inc.max_pgv_cms === null ? "—" : inc.max_pgv_cms.toFixed(1)}
          unit={inc.max_pgv_cms === null ? undefined : "cm/s"}
        />
        <Metric label="DURACIÓN DEL INCIDENTE" value={durationOf(inc)} />
        <Metric
          label="PROFUNDIDAD"
          value={row.event?.depth_km == null ? "—" : String(row.event.depth_km)}
          unit={row.event?.depth_km == null ? undefined : "km"}
        />
        <Metric label="NODOS" value={row.nodeCount === null ? "—" : String(row.nodeCount)} />
      </div>

      <QuorumNodes
        view={quorum}
        eventState={eventStateOf(row, event)}
        eventError={event.error}
        corroborated={isCorroborated(event.data)}
        minNodes={minNodes}
        onRetry={detail.refetch}
      />

      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div>Evidencia archivada</div>
            <div className="soc-card__sub">
              INMUTABLE · SIN PODA POR RETENCIÓN · SÓLO EVENTOS CONFIRMADOS
            </div>
          </div>
          <span className="soc-bacnet">⬢ {countOf(evidence)} OBJETOS</span>
        </div>
        <StateFrame
          label="EVIDENCIA"
          loading={evidence.loading}
          error={evidence.error}
          onRetry={detail.refetch}
          empty={evidence.data?.length === 0}
          emptyText="SIN EVIDENCIA ARCHIVADA PARA ESTE INCIDENTE"
          staleSince={null}
        >
          {miniseed === null ? (
            <p className="soc-meta">
              SIN miniSEED ARCHIVADO · el waveform crudo no se transmite en continuo
            </p>
          ) : (
            miniseed.sha256 && (
              <p className="soc-mono soc-meta">sha256 {miniseed.sha256.slice(0, 16)}…</p>
            )
          )}
        </StateFrame>
      </div>

      {detail.exportError && (
        <p className="soc-meta" role="alert">
          {detail.exportError}
        </p>
      )}

      <footer className="triage-detail__actions">
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={!canExport || evidenceUnknown || miniseed === null || detail.downloadPending}
          title={miniseedTitle}
          onClick={() => miniseed && detail.downloadEvidence(miniseed.evidence_id)}
        >
          <FileDown size={13} aria-hidden /> EXPORTAR miniSEED
        </button>
        <button
          type="button"
          className="soc-btn soc-btn--primary"
          disabled={!canGenerateReport || head === null || detail.pdfPending}
          title={
            !canGenerateReport
              ? "Requiere la acción generate_report"
              : head === null
                ? "Sin dictamen que imprimir"
                : undefined
          }
          onClick={() => detail.generatePdf()}
        >
          <Printer size={13} aria-hidden /> DICTAMEN PDF
        </button>
      </footer>

      <StateFrame
        label="DICTAMEN"
        loading={dictamens.loading}
        error={dictamens.error}
        onRetry={detail.refetch}
        empty={!dictamens.loading && !dictamens.error && head === null}
        emptyText="SIN DICTAMEN REGISTRADO PARA ESTE INCIDENTE"
        staleSince={null}
      >
        {verdict && head && (
          <>
            <div className={`triage-detail__verdict triage-detail__verdict--${verdict.kind}`}>
              <Icon size={18} aria-hidden />
              <div>
                <div className="triage-detail__verdict-lbl">VEREDICTO</div>
                <div className="triage-detail__verdict-val">{verdict.label}</div>
              </div>
            </div>

            {isPreliminary(head) && insufficientData(head) && (
              <p className="triage-detail__insufficient" role="note">
                SIN EVIDENCIA INSTRUMENTAL — DICTAMEN POR SEVERIDAD DE ALERTA (basis v2)
              </p>
            )}

            <div className="soc-card">
              <div className="soc-card__hd">
                <div>
                  <div>Firma del dictamen</div>
                  <div className="soc-card__sub">
                    ACTO PROFESIONAL DEL INSPECTOR · INSERTA UNA VERSIÓN NUEVA
                  </div>
                </div>
              </div>
              <select
                className="soc-select"
                aria-label="Status del dictamen a firmar"
                value={status}
                disabled={!canSign}
                onChange={(e) => setStatus(e.target.value)}
              >
                {SIGNABLE_STATUS.map((s) => (
                  <option key={s} value={s}>
                    {verdictOf(s).label}
                  </option>
                ))}
              </select>
              <ConfirmButton
                label="FIRMAR DICTAMEN"
                icon={<ShieldCheck size={13} aria-hidden />}
                disabled={!canSign || detail.signing}
                onConfirm={() => detail.sign(status, null)}
              />
              {detail.signError && (
                <p className="soc-meta" role="alert">
                  {detail.signError}
                </p>
              )}
            </div>

            <div className="triage-detail__chain">
              <ShieldCheck size={11} aria-hidden />
              CADENA DE CUSTODIA · {countOf(dictamens)} VERSIÓN(ES) APPEND-ONLY · {countOf(actions)}{" "}
              ACCIONES REGISTRADAS
              {actions.error && " (bitácora no disponible)"}
              {head.signed_by && ` · firmó ${head.signed_by.slice(0, 8)}`}
            </div>
          </>
        )}
      </StateFrame>
    </aside>
  );
}
