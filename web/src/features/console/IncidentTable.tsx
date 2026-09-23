// Cola de incidentes abiertos (T-1.27): filas live + barra de acciones de
// operador. Desviaciones RATIFICADAS: "WS · LIVE" (no GraphQL) y la identidad
// REAL de la sesión (no un selector de turno). El acuse es two-step y está
// gateado por allowed_actions.ack_incident (default-deny server-driven).

import { CheckCircle2, FileSearch, List, MapPin, UserCheck } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import Table from "../../components/Table";
import type { AuthBadge } from "../../auth/authEvidence";
import ConfirmButton from "../../components/ConfirmButton";
import SevTag from "../../components/SevTag";
import StateFrame from "../../components/StateFrame";
import { secondsSince, utcClock } from "../../lib/time";
import type { LiveStatus } from "../../lib/ws";
import { actualizarCenso, type CensoFilas } from "./filasNuevas";
import { INCIDENT_ORDERS, orderIncidents, type IncidentOrderKey } from "./stats";
import type { LiveDegradation, LiveIncident } from "./useLiveIncidents";
import SiteLabel from "../../components/SiteLabel";

/**
 * [A-096 · T-8.07] El `state` del incidente con la etiqueta de operador (el CHECK
 * de `incidents.state`). La cola sostiene `open`, `acked` e `in_review` a la vez
 * y no decía cuál era cuál: tras acusar no había forma de comprobar EN LA TABLA
 * que el acuse había entrado. Mismo rótulo que el historial de EVALUACIÓN.
 */
export const INCIDENT_STATE_LABEL: Record<string, string> = {
  open: "ABIERTO",
  acked: "ACUSADO",
  in_review: "EN REVISIÓN",
  closed: "CERRADO",
};

/** Un estado que la consola no conoce se imprime tal cual: disfrazarlo sería peor. */
export function incidentStateLabel(state: string): string {
  return INCIDENT_STATE_LABEL[state] ?? state.toUpperCase();
}

const SEV_DOT: Record<string, string> = {
  critical: "var(--tk-status-critical)",
  warning: "var(--tk-status-warning)",
  watch: "var(--tk-status-warning)",
  info: "var(--tk-status-normal)",
};

export interface IncidentSiteInfo {
  name: string;
  coords: string | null;
  /** [T-6.04] `sites.code`: de él se deriva la cinta DEMO de la fila. */
  code: string | null;
}

export interface IncidentTableProps {
  incidents: LiveIncident[];
  /**
   * [T-6.06] El error de la COLA, con su reintento. Vivía sólo en el marco del
   * wall, que envuelve mapa y cola juntos: una lectura de incidentes caída
   * borraba también el mapa, y la cola no podía ofrecer reintentar lo suyo.
   */
  queueError?: string | null;
  onRetryQueue?: () => void;
  /**
   * [T-6.06] Cuándo se supo por última vez de la cola. Sin esto el marco
   * afirmaba «este dato no puede envejecer», que es la mentira que la regla de
   * oro 7 persigue: una cola vieja se lee como una cola vacía.
   */
  queueStaleSince?: number | null;
  /** Datos del sitio para la fila (nombre/coordenadas), o null si no visible. */
  siteInfoOf: (siteId: string) => IncidentSiteInfo | null;
  nowMs: number;
  liveStatus: LiveStatus;
  operatorLabel: string;
  /**
   * [T-6.02] Lo que la consola PUEDE afirmar sobre cómo se autenticó la sesión
   * (`auth/authEvidence.ts`). `null` = nada que afirmar, y no se pinta nada:
   * hasta esta ficha aquí vivía «AUTH · MFA» a fuego, también en la sesión dev.
   */
  authBadge?: AuthBadge | null;
  /**
   * [A-012 · T-8.07] El INCIDENTE elegido, no el sitio: con dos abiertos en el
   * mismo edificio (pánico + sísmico) la selección por sitio actuaba siempre
   * sobre el primero.
   */
  selectedId: string | null;
  onSelect: (incident: LiveIncident) => void;
  /** allowed_actions.ack_incident del /me (server-driven, default-deny). */
  canAck: boolean;
  /**
   * [A-011 · T-8.07] Devuelve la PROMESA de la petición: el botón dice
   * «ENVIANDO…» mientras vuela y «ACUSADO» sólo cuando el servidor respondió 2xx.
   */
  onAck: (incidentId: string) => void | Promise<unknown>;
  /** [A-011 · T-8.07] Lo que respondió el servidor cuando el acuse NO entró. */
  ackError?: string | null;
  /** allowed_actions.relocate_epicenter (T-1.51). */
  canRelocate: boolean;
  onRelocate: (incidentId: string) => void;
  /** allowed_actions.request_dictamen (T-1.51). */
  canRequestDictamen: boolean;
  onRequestDictamen: (incidentId: string) => void | Promise<unknown>;
  /** [T-2.50] Estaciones del snapshot: solo para el orden por DISTANCIA. */
  sites?: MapSiteState[];
  /** [T-2.50] Epicentro de referencia del orden por distancia (null = no hay). */
  epicenter?: MapEpicenter | null;
  /**
   * [T-2.129] Topics que el SERVIDOR declara degradados (frames `live_health`).
   * Vacío = el canal entrega todo lo que debe.
   */
  degraded?: LiveDegradation[];
}

/** Explica el gate del botón (regla de oro 7: un disabled mudo no informa). */
function gateTitle(allowed: boolean, selected: boolean): string | undefined {
  if (!allowed) return "Tu rol no tiene esta acción (allowed_actions)";
  if (!selected) return "Selecciona un incidente primero";
  return undefined;
}

/**
 * [T-8.07] El acuse sólo pasa `open → acked`: sobre uno ya acusado o en revisión
 * la API responde 409. Se apaga ANTES y se dice por qué, en vez de dejar que el
 * operador descubra el 409.
 */
function ackGateTitle(allowed: boolean, selected: LiveIncident | null): string | undefined {
  const base = gateTitle(allowed, selected !== null);
  if (base !== undefined || selected === null) return base;
  if (selected.state !== "open") {
    return `El incidente ya está ${incidentStateLabel(selected.state)}: sólo se acusa uno ABIERTO`;
  }
  return undefined;
}

function age(openedAt: string, nowMs: number): string {
  const s = secondsSince(Date.parse(openedAt), nowMs);
  return s < 120 ? `T+${String(s).padStart(2, "0")}s` : `T+${Math.floor(s / 60)}min`;
}

/** PGA de la fila (T-1.50): un pico real diminuto (piso MEMS ~0.001 g) no debe
 * imprimirse como "0.000g" — parecería un cero medido. Bajo el medio milésimo
 * se muestra `<0.001g`; null sigue siendo "—" (sin medición). */
export function formatPga(pga: number | null): string {
  if (pga === null) return "—";
  if (pga > 0 && pga < 0.0005) return "<0.001g";
  return `${pga.toFixed(3)}g`;
}

export default function IncidentTable({
  incidents,
  queueError = null,
  onRetryQueue,
  queueStaleSince = null,
  siteInfoOf,
  nowMs,
  liveStatus,
  operatorLabel,
  authBadge = null,
  selectedId,
  onSelect,
  canAck,
  onAck,
  ackError = null,
  canRelocate,
  onRelocate,
  canRequestDictamen,
  onRequestDictamen,
  sites = [],
  epicenter = null,
  degraded = [],
}: IncidentTableProps) {
  const live = liveStatus === "ready";
  // [T-2.129] TRES estados, no dos. «SIN LIVE» dice «no me llega nada» y manda
  // al operador al refresco REST; «DEGRADADO» dice «el canal entrega, pero se
  // perdió algo» — la única de las dos en la que esta cola puede estar
  // INCOMPLETA PARECIENDO COMPLETA, que es la regla de oro 7 en la pantalla
  // donde se decide a quién se manda una brigada.
  //
  // Sin conexión gana sobre degradado: sin canal no hay nada que degradar, y
  // apilar los dos avisos sólo diluye el que hay que atender primero.
  const degradadoVisible = live && degraded.length > 0;
  const pill = degradadoVisible ? "● LIVE DEGRADADO" : live ? "● LIVE" : "● SIN LIVE";
  // [T-6.09] Tinta, no ancla: `--tk-status-critical` dibuja (el punto de
  // severidad de arriba) y `--tk-status-critical-text` escribe.
  const pillColor = degradadoVisible
    ? "var(--tk-status-critical-text)"
    : live
      ? "var(--tk-status-normal)"
      : "var(--tk-status-warning)";
  // [T-2.50] El orden vive AQUÍ, no en el servidor: es una preferencia de lectura
  // del operador, no un hecho del incidente. La cola sigue siendo la misma.
  const [order, setOrder] = useState<IncidentOrderKey>("severity");
  const siteById = useMemo(() => new Map(sites.map((s) => [s.site_id, s])), [sites]);
  const rows = useMemo(
    () => orderIncidents(incidents, order, { epicenter, siteById }),
    [incidents, order, epicenter, siteById],
  );
  // Ordenar por distancia sin epicentro conocido barajaría las filas fingiendo
  // una medida que nadie tomó: se degrada a severidad y se DICE (regla de oro 7).
  const distanceUnavailable = order === "distance" && epicenter === null;
  // [T-6.10 · W13] Qué filas LLEGARON mientras se miraba. El censo vive en una
  // ref y no en estado: no dispara un render propio —lo dispara `nowMs`, que ya
  // late— y volver a censar con el mismo instante devuelve lo mismo, así que la
  // doble pintura del modo estricto no reinicia la cuenta.
  // [A-012 · T-8.07] La fila sobre la que actúan los botones, resuelta por su id.
  const selected = incidents.find((i) => i.incident_id === selectedId) ?? null;
  const ackable = canAck && selected !== null && selected.state === "open";
  const censoRef = useRef<CensoFilas | null>(null);
  const { censo, nuevas } = actualizarCenso(
    censoRef.current,
    rows.map((r) => r.incident_id),
    nowMs,
  );
  censoRef.current = censo;
  return (
    <section className="soc-incidents" data-screen-label="Incidents queue">
      <header className="soc-incidents__hd">
        <h3 className="soc-incidents__title">
          <List size={16} aria-hidden style={{ color: "var(--tk-cyan)" }} />
          Incidentes Abiertos
          <span className="soc-incidents__count">{incidents.length} ACTIVOS</span>
        </h3>
        <div className="soc-incidents__toolbar">
          <label className="soc-incidents__order">
            <span className="soc-meta">ORDEN</span>
            <select
              aria-label="Orden de la cola de incidentes"
              data-testid="incident-order"
              value={order}
              onChange={(event) => setOrder(event.target.value as IncidentOrderKey)}
            >
              {INCIDENT_ORDERS.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <span>WS · LIVE</span>
          <span data-testid="live-pill" style={{ color: pillColor }}>
            {pill}
          </span>
        </div>
      </header>

      {/* [T-2.129] El aviso nombra QUÉ se degradó. El detalle técnico
          (`LockTimeout`…) va al `title`: en una sala de crisis el rótulo que se
          lee en voz alta tiene que decir qué falta, no cómo se llama la
          excepción. Y el aviso se apaga solo — el servidor manda su
          `degraded: false` en cuanto vuelve a poder leer. */}
      {degradadoVisible && (
        <p
          className="soc-incidents__note"
          data-testid="live-degraded"
          role="status"
          title={degraded.map((d) => `${d.topic}: ${d.detail ?? "sin detalle"}`).join(" · ")}
          style={{ color: "var(--tk-status-critical-text)" }}
        >
          {`CANAL LIVE DEGRADADO · ${degraded.map((d) => d.label).join(" · ")} · ` +
            "PUEDE FALTAR INFORMACIÓN EN VIVO · EL REFRESCO PERIÓDICO SIGUE"}
        </p>
      )}

      {/* [T-2.55] Estado VACÍO explícito. Sin él, cero incidentes producía un
          <tbody> hueco bajo los encabezados: indistinguible de "la cola no
          cargó". `loading`/`error` de la fuente los resuelve el StateFrame del
          wall, que envuelve a esta tabla y no la monta hasta tener datos; aquí
          se declara lo único que el wall no puede saber: que la cola está
          vacía porque no hay incidentes abiertos, que es una BUENA noticia. */}
      <StateFrame
        label="INCIDENTES ABIERTOS"
        loading={false}
        error={queueError}
        onRetry={onRetryQueue}
        empty={rows.length === 0}
        emptyText="SIN INCIDENTES ABIERTOS EN EL ALCANCE"
        staleSince={queueStaleSince}
      >
        <Table>
          <thead>
            <tr>
              <th style={{ width: "24%" }}>Sitio</th>
              <th style={{ width: "12%" }}>Severidad</th>
              <th style={{ width: "12%" }}>Estado</th>
              <th style={{ width: "20%" }}>Coordenadas</th>
              <th style={{ width: "10%" }}>PGA</th>
              <th style={{ width: "12%" }}>Hora UTC</th>
              <th style={{ width: "10%" }}>Edad</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((incident) => {
              const site = siteInfoOf(incident.site_id);
              const nueva = nuevas.has(incident.incident_id);
              const elegida = incident.incident_id === selectedId;
              return (
                <tr
                  key={incident.incident_id}
                  className={nueva ? "soc-table__row--nueva" : undefined}
                  onClick={() => onSelect(incident)}
                  aria-selected={elegida}
                  // [A-012 · T-8.07] La fila elegida se VE: los botones de abajo
                  // actúan sobre ella y hasta hoy nada la distinguía (el
                  // `aria-selected` no tenía regla en la hoja).
                  style={{
                    cursor: "pointer",
                    backgroundColor: elegida ? "var(--tk-cyan-08)" : undefined,
                  }}
                >
                  <td className="soc-table__site">
                    <span
                      className="soc-dot"
                      style={{ color: SEV_DOT[incident.severity] ?? "var(--tk-status-warning)" }}
                    />
                    <SiteLabel
                      name={site?.name ?? `SITIO ${incident.site_id.slice(0, 8)}`}
                      code={site?.code ?? null}
                    />
                    {/* El PORTADOR del aviso es este rótulo, no el destello: con
                        la reducción de movimiento puesta la fila no se mueve y
                        hay que enterarse igual. */}
                    {nueva && (
                      <span className="soc-table__nuevo" data-testid="fila-nueva">
                        NUEVO
                      </span>
                    )}
                  </td>
                  <td>
                    <SevTag severity={incident.severity} />
                  </td>
                  <td className="soc-mono" data-testid="incident-state">
                    {incidentStateLabel(incident.state)}
                  </td>
                  <td className="soc-mono" style={{ color: "var(--tk-fg-2)" }}>
                    {site?.coords ?? "—"}
                  </td>
                  <td
                    className={`soc-mono ${incident.severity !== "info" ? "soc-table__pga" : ""}`}
                  >
                    {formatPga(incident.max_pga_g)}
                  </td>
                  <td className="soc-mono">{utcClock(Date.parse(incident.opened_at))} UTC</td>
                  <td className="soc-mono" style={{ color: "var(--tk-fg-3)" }}>
                    {age(incident.opened_at, nowMs)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </StateFrame>

      {distanceUnavailable && (
        <p className="soc-incidents__note" data-testid="order-distance-unavailable" role="status">
          SIN EPICENTRO LOCALIZADO · ORDENADO POR SEVERIDAD
        </p>
      )}

      {/* [A-011 · T-8.07] Lo que respondió el servidor cuando el acuse NO entró,
          encima del pie y no dentro: el pie es una fila (operador | botones) y un
          párrafo más ahí se colaría entre los dos. */}
      {ackError !== null && (
        <p
          className="soc-incidents__note"
          role="alert"
          data-testid="ack-error"
          style={{ color: "var(--tk-status-critical-text)" }}
        >
          {ackError}
        </p>
      )}

      <footer className="soc-incidents__ft">
        <div className="soc-incidents__operator">
          <span className="soc-meta">Operador</span>
          <span className="soc-mono" data-testid="operator-label">
            {operatorLabel}
          </span>
          {authBadge != null && (
            <span
              className="soc-pill soc-pill--ok"
              title={authBadge.title}
              data-testid="auth-badge"
            >
              <UserCheck size={11} aria-hidden /> {authBadge.label}
            </span>
          )}
        </div>
        <div className="soc-incidents__actions">
          {/* T-1.51: gates por allowed_actions (matriz server-driven, jamás
              roles hardcodeados). Reubicar abre modal (la confirmación vive
              dentro); solicitar dictamen es two-step aquí mismo. */}
          <span title={gateTitle(canRelocate, selectedId !== null)}>
            <button
              type="button"
              className="soc-confirm soc-confirm--secondary"
              disabled={!canRelocate || selectedId === null}
              onClick={() => {
                if (selectedId !== null) onRelocate(selectedId);
              }}
            >
              <span className="soc-confirm__row">
                <MapPin size={13} aria-hidden />
                <span>REUBICAR EPICENTRO</span>
              </span>
            </button>
          </span>
          <span title={gateTitle(canRequestDictamen, selectedId !== null)}>
            {/* [T-8.07] `key` por incidente: cambiar de fila DESARMA. Sin ella la
                fase «armado» sobrevivía al cambio de selección y el segundo clic
                caía sobre una fila que nadie había confirmado. */}
            <ConfirmButton
              key={selectedId ?? "ninguno"}
              icon={<FileSearch size={13} aria-hidden />}
              label="SOLICITAR DICTAMEN TÉCNICO"
              armedLabel="CLIC DE NUEVO PARA SOLICITAR"
              variant="secondary"
              disabled={!canRequestDictamen || selectedId === null}
              onConfirm={() => (selectedId !== null ? onRequestDictamen(selectedId) : undefined)}
            />
          </span>
          {/* [T-2.59] El envoltorio con `gateTitle` faltaba SOLO aquí: los dos
              botones de al lado explicaban su gate desde T-1.51 y el acuse —el
              más consecuente de los tres— se quedaba gris y mudo. Lo encontró
              `screens.spec.ts` inventariando los deshabilitados de cada pantalla. */}
          <span title={ackGateTitle(canAck, selected)}>
            <ConfirmButton
              key={selectedId ?? "ninguno"}
              icon={<CheckCircle2 size={13} aria-hidden />}
              label="CONFIRMAR ACUSE"
              armedLabel="CLIC DE NUEVO PARA ACUSAR"
              doneLabel="ACUSADO"
              variant="primary"
              disabled={!ackable}
              // [A-011 · T-8.07] Se DEVUELVE la promesa: sin ella el botón pintaba
              // «EJECUTADO» antes de que el servidor contestara, y un 409 o un 403
              // se tragaban en silencio.
              onConfirm={() => (selected !== null ? onAck(selected.incident_id) : undefined)}
            />
          </span>
        </div>
      </footer>
    </section>
  );
}
