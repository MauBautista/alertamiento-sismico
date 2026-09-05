import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  FileDown,
  Printer,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import ConfirmButton from "../../components/ConfirmButton";
import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import ComplianceDeclared from "./ComplianceDeclared";
import IncidentTimeline from "./IncidentTimeline";
import NotifyChain from "./NotifyChain";
import CctvPanel from "./CctvPanel";
import { ClassificationPanel } from "./ClassificationPanel";
import PostEventSummary from "./PostEventSummary";
import QuorumNodes from "./QuorumNodes";
import StructuralTriage from "./StructuralTriage";
import {
  SIGNABLE_STATUS,
  chainHead,
  durationOf,
  epicenterKindOf,
  feltLabelOf,
  insufficientData,
  isCorroborated,
  isPreliminary,
  magnitudeOf,
  miniseedOf,
  miniseedState,
  quorumView,
  verdictOf,
} from "./model";
import type { TriageRow } from "./model";
import type { CctvState } from "./useCctv";
import type { ForensicsState } from "./useForensics";
import type { IncidentDetailData, Resource } from "./useIncidentDetail";

const VERDICT_ICON = { crit: AlertOctagon, warn: AlertTriangle, ok: CheckCircle2 } as const;

function Metric({
  label,
  value,
  unit,
  title,
}: {
  label: string;
  value: string;
  unit?: string;
  /** Por qué el dato falta o qué significa exactamente. */
  title?: string;
}) {
  return (
    <div className="triage-metric" title={title}>
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
  /** [T-2.40] Hechos medidos; el MISMO objeto que consume el dictamen PDF. */
  forensics: ForensicsState;
  cctv: CctvState;
  minNodes: number | null;
  /**
   * [T-2.82.a] Edad de la FILA del incidente (la lista de `/incidents` que
   * `TriagePage` ya fecha), no la de ninguna consulta de este panel.
   *
   * Baja hasta aquí porque el quórum, cuando el incidente no referencia evento,
   * está afirmando algo que sale de esa fila y de ninguna otra parte. El resto
   * de los marcos usan la edad de SU propio recurso.
   */
  incidentStaleSince: number | null;
  /** `me.allowed_actions` — server-driven, default-deny. */
  canSign: boolean;
  canExport: boolean;
  /** `cctv_video` del token: sin ella no se pinta el botón de descargar el clip. */
  canDownloadClip: boolean;
  onDownloadClip?: (clipId: string) => void;
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
  forensics,
  cctv,
  minNodes,
  incidentStaleSince,
  canSign,
  canExport,
  canDownloadClip,
  onDownloadClip,
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
  const mag = magnitudeOf(row.event);
  const epi = epicenterKindOf(row.event);
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

  // [T-2.43] Seis estados distinguibles en lugar de un botón gris sin explicación.
  // `evidenceUnknown` (data === undefined) cuenta como carga —una consulta que aún no
  // resolvió no puede presentarse como "no hay"—, PERO una consulta fallida también
  // deja `data` en undefined, y ahí lo honesto es decir que falló, no que sigue en
  // vuelo. De ahí el `&& !evidence.error`.
  const mseed = miniseedState({
    canExport,
    loading: evidence.loading || (evidenceUnknown && !evidence.error),
    error: Boolean(evidence.error),
    miniseed,
    openedAt: Date.parse(inc.opened_at),
    now: Date.now(),
  });

  return (
    <aside className="triage-detail">
      <header className="triage-detail__hd">
        <span className="soc-meta">{badge}</span>
        {/* [T-2.39] El título era `M — · Sitio`: la magnitud es SIEMPRE null (no hay
            ingesta de catálogo), así que el encabezado del panel se abría con un
            guion. Ahora encabeza el HECHO MEDIDO —la sacudida que registró el
            sensor— y la magnitud baja a métrica, rotulada como lo que es. */}
        <h2 className="triage-detail__title">
          {feltLabelOf(inc.max_pga_g)} · {row.siteName}
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
        <Metric label="MAGNITUD (CATÁLOGO)" value={mag.label} title={mag.title} />
        <Metric
          label="PROFUNDIDAD"
          value={row.event?.depth_km == null ? "—" : String(row.event.depth_km)}
          unit={row.event?.depth_km == null ? undefined : "km"}
        />
        <Metric label="NODOS" value={row.nodeCount === null ? "—" : String(row.nodeCount)} />
        <Metric label="EPICENTRO" value={epi.label} title={epi.note} />
      </div>
      {epi.kind !== "none" && (
        <p className="triage-detail__epinote" data-testid="epicenter-note">
          {epi.note}
        </p>
      )}

      {/* [T-2.40] Desempeño de la red, al estilo del post-mortem que USGS publica
          tras cada sismo relevante: tiempo de aviso, estaciones que contribuyeron y
          contraste con el catálogo. Convierte "el sistema funcionó" en algo
          verificable. */}
      {/* [T-5.12] Qué FUE este incidente. Va junto al resumen post-evento porque
          contesta la última pregunta del mismo bloque: el resumen dice cómo se
          comportó el sistema, y esto dice si hacía falta que se comportara. */}
      <ClassificationPanel incidentId={row.incident.incident_id} />
      <PostEventSummary forensics={forensics} />
      {/* [T-3.12.c] La ÚNICA superficie de CCTV de la consola. Va junto al resumen
          post-evento porque responde a la misma pregunta —cómo se comportó el
          inmueble— con la otra mitad del dato: la gente. */}
      <CctvPanel cctv={cctv} canDownloadClip={canDownloadClip} onDownloadClip={onDownloadClip} />

      <QuorumNodes
        view={quorum}
        eventState={eventStateOf(row, event)}
        eventError={event.error}
        corroborated={isCorroborated(event.data)}
        minNodes={minNodes}
        // [T-2.82.a] Dos ramas, dos datos, dos edades: la del evento para los
        // votos que sostienen si hubo corroboración, la del incidente para la
        // rama que afirma que no hay evento ninguno.
        eventStaleSince={event.staleSince}
        incidentStaleSince={incidentStaleSince}
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
          // [T-2.82.a] Con la lista congelada, «SIN EVIDENCIA ARCHIVADA» es la
          // ausencia no verificable que T-2.79.d decidió no afirmar — y aquí se
          // afirmaría al lado del botón que descarga el miniSEED, en la pantalla
          // donde se firma. `stale` gana y la ausencia sale fechada.
          staleSince={evidence.staleSince}
        >
          {miniseed?.sha256 && (
            <p className="soc-mono soc-meta">sha256 {miniseed.sha256.slice(0, 16)}…</p>
          )}
        </StateFrame>
        {/* [T-2.43] La explicación del miniSEED vive FUERA del StateFrame: con cero
            objetos el marco pinta su estado "empty" y se comía la nota justo en el
            caso que más necesita explicarse. Solo se muestra cuando la consulta ya
            resolvió y de verdad no hay crudo — en `loading`/`error` el marco ya dice
            lo suyo y duplicarlo sería ruido. */}
        {(mseed.kind === "backfill" || mseed.kind === "absent") && (
          <p className="soc-meta" data-testid="miniseed-note">
            {mseed.label} · {mseed.hint}
            {mseed.fleetLink && (
              <>
                {" "}
                <Link to="/fleet" className="soc-link">
                  IR A FLOTA EDGE
                </Link>
              </>
            )}
          </p>
        )}
      </div>

      {/* [T-2.40] La bitácora existe para reconstruir lo ocurrido; contarla en un
          número desperdiciaba precisamente eso. */}
      <IncidentTimeline actions={actions} openedAt={inc.opened_at} onRetry={detail.refetch} />
      {/* [T-5.15] Va DESPUÉS de la bitácora y no dentro: la bitácora es lo que
          hizo TAKAB y esto es lo que hicieron los proveedores con ello. */}
      <NotifyChain incidentId={inc.incident_id} />

      {detail.exportError && (
        <p className="soc-meta" role="alert">
          {detail.exportError}
        </p>
      )}

      <footer className="triage-detail__actions">
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={!mseed.enabled || detail.downloadPending}
          title={mseed.hint}
          onClick={() => miniseed && detail.downloadEvidence(miniseed.evidence_id)}
        >
          <FileDown size={13} aria-hidden /> {mseed.label}
        </button>
        <button
          type="button"
          className="soc-btn soc-btn--primary"
          // [T-2.43] Se retira el gate `head === null`, espejo del que ya se quitó en la
          // API: un incidente sin dictamen YA tiene hechos que reportar —lo medido,
          // quién acusó, qué estaciones corroboraron— y el documento se rotula como
          // preliminar. El gate dejaba sin evidencia exportable justo el caso en que
          // más falta hace.
          disabled={!canGenerateReport || detail.pdfPending}
          title={!canGenerateReport ? "Requiere la acción generate_report" : undefined}
          onClick={() => detail.generatePdf()}
        >
          <Printer size={13} aria-hidden /> DICTAMEN PDF
        </button>
      </footer>

      {/* [T-2.82] Entre el PDF y la firma: son los dos actos que este apartado
          cualifica. Quien firma se lleva detrás las afirmaciones normativas del
          cliente y tiene que leer, en el mismo golpe de vista, que TAKAB no las
          verificó. Sale del MISMO `forensics` que alimenta el PDF.
          [T-2.82.a] Y con la EDAD de ese forense: el panel siempre supo recibir
          `staleSince`, pero nadie se la pasaba, así que su valor por defecto
          (`= null`) afirmaba «este dato no puede envejecer» — en la pantalla
          donde se firma. Con el dato viejo gana `stale` (T-2.79.d) y la
          ausencia de marco declarado se FECHA en vez de acusar al cliente de no
          haber declarado nada. */}
      <ComplianceDeclared forensics={forensics} staleSince={forensics.staleSince} />

      <StateFrame
        label="DICTAMEN"
        loading={dictamens.loading}
        error={dictamens.error}
        onRetry={detail.refetch}
        empty={!dictamens.loading && !dictamens.error && head === null}
        emptyText="SIN DICTAMEN REGISTRADO PARA ESTE INCIDENTE"
        // [T-2.82.a] Dentro de este marco está el botón FIRMAR DICTAMEN. La
        // cadena de custodia que se enseña aquí puede haber crecido una versión
        // desde la última respuesta, y firmar sobre una cadena vieja creyéndola
        // vigente es exactamente el acto que la regla de oro 7 protege.
        staleSince={dictamens.staleSince}
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
              CADENA DE CUSTODIA · {countOf(dictamens)} VERSIÓN(ES) APPEND-ONLY
              {head.signed_by && ` · firmó ${head.signed_by.slice(0, 8)}`}
            </div>
          </>
        )}
      </StateFrame>

      {/* [T-2.10] Reportes de daños del móvil (2.4) con verificación de hash.
          [T-2.39] FUERA del gate `verdict && head` y fuera del StateFrame del
          dictamen: vivían dentro, así que un incidente sin dictamen —o con la
          consulta del dictamen aún en vuelo— ocultaba por completo los reportes que
          los tácticos ya habían enviado desde el edificio. Son un HECHO del
          incidente, igual que las métricas que T-1.52 sacó del gate. */}
      <StructuralTriage incidentId={inc.incident_id} />
    </aside>
  );
}
