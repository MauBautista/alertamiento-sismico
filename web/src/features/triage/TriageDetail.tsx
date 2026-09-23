import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileDown,
  Printer,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import Button from "../../components/Button";
import Card from "../../components/Card";
import ConfirmButton from "../../components/ConfirmButton";
import StateFrame from "../../components/StateFrame";
import EvidenceVerifier from "./EvidenceVerifier";
import { utcClock, utcStamp } from "../../lib/time";
import ComplianceDeclared from "./ComplianceDeclared";
import IncidentTimeline from "./IncidentTimeline";
import NotifyChain from "./NotifyChain";
import CctvPanel from "./CctvPanel";
import { ClassificationPanel } from "./ClassificationPanel";
import PostEventSummary from "./PostEventSummary";
import EstacionesTable from "../console/EstacionesTable";
import type { EstacionesData } from "../console/useEstaciones";
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
  dictamenPdfOf,
  miniseedOf,
  miniseedState,
  quorumView,
  verdictOf,
} from "./model";
import type { TriageRow } from "./model";
import type { CctvState } from "./useCctv";
import type { ClipDownload } from "./useClipDownload";
import type { ForensicsState } from "./useForensics";
import type { IncidentDetailData, Resource } from "./useIncidentDetail";
import SiteLabel from "../../components/SiteLabel";

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
  /** [T-7.17] La red de estaciones de este incidente. */
  estaciones: EstacionesData;
  /** `me.allowed_actions` — server-driven, default-deny. */
  canSign: boolean;
  canExport: boolean;
  /**
   * [T-8.08 · A-042] `cctv_read`. Sin ella el panel de CCTV NO se monta: la API
   * responde 403 (`takab_support` y `gov_operator` quedan fuera por T-3.12.c) y
   * pintar un fallo que siempre ocurre enseña a no leer el panel.
   */
  canReadCctv: boolean;
  /** `cctv_video` del token: sin ella no se pinta el botón de descargar el clip. */
  canDownloadClip: boolean;
  /** [T-8.08 · A-014] La descarga del clip, cableada. Era un `?:` que nadie pasaba. */
  clipDownload: ClipDownload;
  /**
   * [T-8.08 · A-052] `dictamen_read`. Verificar la huella de un `report_pdf` la
   * exige (`_ALCANCE_DE_VERIFICACION`, mobile_incident.py) y responde 404 a los
   * demás; sin ella el botón pintaba «NO SE PUDO VERIFICAR» en rojo.
   */
  canVerifyDictamen: boolean;
  canGenerateReport: boolean;
  /**
   * [T-6.02] `allowed_routes` incluye `/fleet`. Un `inspector` no la tiene: el
   * enlace «IR A FLOTA EDGE» lo mandaba a SIN ACCESO (U-38). Sin la ruta se
   * declara la ausencia y a quién pedirle la verificación.
   */
  canOpenFleet: boolean;
  /**
   * [T-6.14] `allowed_routes` incluye `/building`. Hoy la tienen los siete roles
   * web, y aun así se pregunta: el enlace se pinta desde el contrato del
   * servidor, no desde lo que hoy resulta ser cierto para todos.
   */
  canOpenBuilding: boolean;
  /**
   * [T-6.14] Sitio al que volver en el wall, si se llegó desde allí
   * (`/triage?...&volver=<site_id>`). `null` = se entró por la pestaña, y
   * entonces no hay riel al que regresar: ofrecerlo mandaría al operador a una
   * pantalla en la que no estuvo.
   */
  volverASitioId: string | null;
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
/**
 * [T-6.02] Por qué la firma está apagada. El superadmin no firma dictámenes
 * (decisión ratificada en T-1.30): un botón gris y mudo en la pantalla donde
 * se firma obligaba a adivinarlo. Lo inventaría `screens.spec.ts`.
 */
function signGateTitle(canSign: boolean, signing: boolean): string | undefined {
  if (!canSign) return "Tu rol no tiene la acción sign_dictamen: el dictamen lo firma el inspector";
  if (signing) return "Firmando…";
  return undefined;
}

/**
 * [T-7.48] Una huella de archivo, ENTERA y comparable a mano.
 *
 * ⚠️ TRES cosas de esto no son estética, y las tres estaban mal:
 *
 * 1. **Los 64 caracteres, no 16.** Antes se pintaba `sha.slice(0, 16)`, y un
 *    hash truncado no verifica nada — es el mismo defecto que `T-5.26` ya cerró
 *    una vez en el papel del dictamen. Quien compara un sha lo compara entero o
 *    no lo compara.
 * 2. **Minúsculas.** La clase `soc-meta` lleva `text-transform: uppercase`, así
 *    que la consola enseñaba el hash en mayúsculas mientras `sha256sum` lo emite
 *    en minúsculas. El portapapeles daba el texto bueno, pero quien lo comparaba
 *    A LA VISTA veía dos cadenas distintas. Por eso este marcado no usa
 *    `soc-meta` para el valor.
 * 3. **Que quepa.** La columna de detalle mide 420 px fijos y 64 caracteres de
 *    monoespaciada a 11 px no entran en una línea: sin `overflow-wrap` esto
 *    empuja una barra horizontal en la pantalla donde se firma.
 *
 * Y el RÓTULO dice qué identifica la huella. `T-7.43` decidió que hay dos —la
 * del contenido, que identifica una exportación y no se puede comparar entre
 * dos, y la del archivo, que sí—: pintarlas sin decir cuál es cuál reproduce el
 * defecto de portada que cerró `T-7.42`.
 */
function Huella({ rotulo, sha }: { rotulo: string; sha: string }) {
  return (
    <p className="triage-huella">
      <span className="triage-huella__rotulo">{rotulo} · sha256 del archivo</span>
      <code className="triage-huella__valor">{sha}</code>
    </p>
  );
}

export default function TriageDetail({
  row,
  detail,
  forensics,
  cctv,
  minNodes,
  incidentStaleSince,
  estaciones,
  canSign,
  canExport,
  canReadCctv,
  canDownloadClip,
  clipDownload,
  canVerifyDictamen,
  canGenerateReport,
  canOpenFleet,
  canOpenBuilding,
  volverASitioId,
}: TriageDetailProps) {
  const [status, setStatus] = useState<string>("no_inhabit_inspect");
  const inc = row.incident;
  const { dictamens, actions, evidence, event } = detail;
  const head = chainHead(dictamens.data);
  const verdict = head ? verdictOf(head.status) : null;
  const Icon = verdict ? VERDICT_ICON[verdict.kind] : AlertTriangle;
  const quorum = quorumView(event.data?.quorum_votes);
  const miniseed = miniseedOf(evidence.data);
  const dictamen = dictamenPdfOf(evidence.data);
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
  /**
   * [T-8.08 · A-015] LA TARJETA DE FIRMA, una sola, en los dos sitios donde se
   * firma: sobre una cadena con cabeza (dentro del marco, bajo su banda de
   * retenido) y sobre una cadena VACÍA ya leída. Vivía sólo dentro de
   * `{verdict && head && …}`, y la API firma igual sin cabeza (`supersedes =
   * NULL`, dictamens.py): si la pasada automática no dejó preliminar —worker
   * caído, ventana vencida, incidente manual— el inspector que llegaba por el
   * correo de `dictamen_request` no tenía con qué firmar desde la web.
   */
  const firma = (sub: string) => (
    <Card title="Firma del dictamen" sub={sub}>
      <select
        className="soc-select"
        aria-label="Status del dictamen a firmar"
        value={status}
        disabled={!canSign}
        title={signGateTitle(canSign, detail.signing)}
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
        title={signGateTitle(canSign, detail.signing)}
        onConfirm={() => detail.sign(status, null)}
      />
      {detail.signError && (
        <p className="soc-meta" role="alert">
          {detail.signError}
        </p>
      )}
    </Card>
  );
  // Una cadena VACÍA y LEÍDA —no en vuelo, no caída—: sólo entonces se puede
  // ofrecer la primera firma. Sobre una cadena que no se conoce no se firma.
  const cadenaVaciaLeida =
    !dictamens.loading && !dictamens.error && dictamens.data !== undefined && head === null;

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
        {/* [T-6.14] EL CAMINO DE VUELTA, arriba del todo: quien llegó aquí desde
            el wall venía mirando un sitio, y al salir de esta pantalla lo que
            quiere es seguir mirándolo. Sin esto, firmar era el final del hilo:
            la consola se re-armaba desde cero. */}
        {volverASitioId !== null && (
          <Link
            className="soc-link triage-detail__volver"
            data-testid="triage-volver"
            to={`/console?sitio=${encodeURIComponent(volverASitioId)}`}
          >
            ◀ VOLVER A MONITOREO · <SiteLabel name={row.siteName} code={row.siteCode} />
          </Link>
        )}
        <span className="soc-meta">{badge}</span>
        {/* [T-2.39] El título era `M — · Sitio`: la magnitud es SIEMPRE null (no hay
            ingesta de catálogo), así que el encabezado del panel se abría con un
            guion. Ahora encabeza el HECHO MEDIDO —la sacudida que registró el
            sensor— y la magnitud baja a métrica, rotulada como lo que es. */}
        <h2 className="triage-detail__title">
          {feltLabelOf(inc.max_pga_g)} · <SiteLabel name={row.siteName} code={row.siteCode} />
        </h2>
        <div className="triage-detail__id">
          {inc.event_id ?? inc.incident_id} · {utcStamp(Date.parse(inc.opened_at))} UTC
        </div>
        {/* [T-6.14] `/building` colgaba de UN enlace en el riel de `/console`.
            `inspector` y `building_admin` tienen la ruta concedida y NO tienen
            `/fleet`: para ellos ese riel era el único camino a la ficha del
            inmueble que están evaluando. Aquí es donde la necesitan. */}
        {canOpenBuilding && (
          <Link
            className="soc-link triage-detail__deeplink"
            data-testid="triage-building-link"
            to={`/building/${inc.site_id}`}
          >
            <ExternalLink size={11} aria-hidden /> FICHA DEL EDIFICIO
          </Link>
        )}
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
      {canReadCctv && (
        <CctvPanel cctv={cctv} canDownloadClip={canDownloadClip} clipDownload={clipDownload} />
      )}

      {/* [T-7.17] La red de estaciones SUSTITUYE a la tabla de cuórum cuando el
          evento es una reproducción: allí no hubo votos, y enseñar una tabla de
          votos vacía parecería que la red no corroboró cuando lo que pasa es que
          no había nada que corroborar. Con un evento real se pintan las dos: la
          de cuórum dice quién votó, ésta dice qué midió cada una. */}
      <EstacionesTable estaciones={estaciones} staleSince={incidentStaleSince} />

      {estaciones.data?.reproduccion !== true && (
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
      )}

      <Card
        title="Evidencia archivada"
        sub="INMUTABLE · SIN PODA POR RETENCIÓN · SÓLO EVENTOS CONFIRMADOS"
        aside={
          <>
            <span className="soc-bacnet">⬢ {countOf(evidence)} OBJETOS</span>
          </>
        }
      >
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
          {miniseed?.sha256 && <Huella rotulo="miniSEED archivado" sha={miniseed.sha256} />}
          {dictamen?.sha256 && (
            <>
              <Huella rotulo="Dictamen emitido" sha={dictamen.sha256} />
              {/* [T-7.48] El botón que la portada del papel PROMETÍA y no existía.
                  Re-hashea el objeto de S3 y lo confronta con la huella declarada,
                  que es lo único que convierte «este número» en «este archivo».
                  [T-8.08 · A-052] Sólo para quien puede LEER el dictamen: a los
                  demás la API les responde 404 y el botón salía en rojo. No se
                  amplía el permiso; se dice quién verifica y cómo, a mano. */}
              {canVerifyDictamen ? (
                <EvidenceVerifier evidenceId={dictamen.evidence_id} />
              ) : (
                <p className="soc-meta" data-testid="verify-dictamen-denied">
                  SIN RE-VERIFICACIÓN DESDE ESTE ROL · requiere la acción dictamen_read (quien lee
                  el dictamen). La huella de arriba se compara con el sha256sum del PDF.
                </p>
              )}
            </>
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
            {mseed.fleetLink &&
              (canOpenFleet ? (
                <>
                  {" "}
                  <Link to="/fleet" className="soc-link">
                    IR A FLOTA EDGE
                  </Link>
                </>
              ) : (
                <>
                  {" "}
                  <span data-testid="fleet-link-denied">
                    Su rol no accede a FLOTA EDGE: pida al operador de flota que verifique el enlace
                    de la estación.
                  </span>
                </>
              ))}
          </p>
        )}
      </Card>

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
        <Button
          variant="secondary"
          disabled={!mseed.enabled || detail.downloadPending}
          title={mseed.hint}
          onClick={() => miniseed && detail.downloadEvidence(miniseed.evidence_id)}
        >
          <FileDown size={13} aria-hidden /> {mseed.label}
        </Button>
        <Button
          variant="primary" // [T-2.43] Se retira el gate `head === null`, espejo del que ya se quitó en la
          // API: un incidente sin dictamen YA tiene hechos que reportar —lo medido,
          // quién acusó, qué estaciones corroboraron— y el documento se rotula como
          // preliminar. El gate dejaba sin evidencia exportable justo el caso en que
          // más falta hace.
          disabled={!canGenerateReport || detail.pdfPending}
          title={!canGenerateReport ? "Requiere la acción generate_report" : undefined}
          onClick={() => detail.generatePdf()}
        >
          <Printer size={13} aria-hidden /> DICTAMEN PDF
        </Button>
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

            {firma("ACTO PROFESIONAL DEL INSPECTOR · INSERTA UNA VERSIÓN NUEVA")}

            <div className="triage-detail__chain">
              <ShieldCheck size={11} aria-hidden />
              CADENA DE CUSTODIA · {countOf(dictamens)} VERSIÓN(ES) APPEND-ONLY
              {head.signed_by && ` · firmó ${head.signed_by.slice(0, 8)}`}
            </div>
          </>
        )}
      </StateFrame>
      {/* [T-8.08 · A-015] FUERA del marco a propósito: con la cadena vacía el marco
          está en `empty` (o en `stale` con la ausencia fechada) y no pinta hijos.
          Justo encima dice que no hay dictamen —o que así estaba a tal hora—, que
          es lo que el inspector tiene que leer antes de firmar la primera versión. */}
      {/* [verificador] Con la cadena VIEJA, «no hay preliminar» deja de ser un hecho
          medido: pudo llegar uno después de la última lectura. Se sigue ofreciendo
          —la API calcula `supersedes` con la cabeza REAL, dictamens.py— pero el
          rótulo dice de cuándo es lo que se sabe (regla de oro 7). */}
      {cadenaVaciaLeida &&
        firma(
          dictamens.staleSince === null
            ? "PRIMERA VERSIÓN DE LA CADENA · NO HAY PRELIMINAR AUTOMÁTICO QUE SUSTITUIR"
            : `PRIMERA VERSIÓN SEGÚN LA LECTURA DE LAS ${utcClock(dictamens.staleSince)} UTC · ` +
                "SI LLEGÓ UN PRELIMINAR DESPUÉS, ESTA FIRMA LO SUSTITUYE",
        )}

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
