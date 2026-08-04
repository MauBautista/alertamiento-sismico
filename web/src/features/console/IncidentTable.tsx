// Cola de incidentes abiertos (T-1.27): filas live + barra de acciones de
// operador. Desviaciones RATIFICADAS: "WS · LIVE" (no GraphQL) y la identidad
// REAL de la sesión (no un selector de turno). El acuse es two-step y está
// gateado por allowed_actions.ack_incident (default-deny server-driven).

import { CheckCircle2, FileSearch, List, MapPin, UserCheck } from "lucide-react";
import { useMemo, useState } from "react";

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import ConfirmButton from "../../components/ConfirmButton";
import SevTag from "../../components/SevTag";
import StateFrame from "../../components/StateFrame";
import { secondsSince, utcClock } from "../../lib/time";
import type { LiveStatus } from "../../lib/ws";
import { INCIDENT_ORDERS, orderIncidents, type IncidentOrderKey } from "./stats";
import type { LiveIncident } from "./useLiveIncidents";

const SEV_DOT: Record<string, string> = {
  critical: "var(--tk-status-critical)",
  warning: "var(--tk-status-warning)",
  watch: "var(--tk-status-warning)",
  info: "var(--tk-status-normal)",
};

export interface IncidentSiteInfo {
  name: string;
  coords: string | null;
}

export interface IncidentTableProps {
  incidents: LiveIncident[];
  /** Datos del sitio para la fila (nombre/coordenadas), o null si no visible. */
  siteInfoOf: (siteId: string) => IncidentSiteInfo | null;
  nowMs: number;
  liveStatus: LiveStatus;
  operatorLabel: string;
  selectedId: string | null;
  onSelect: (incident: LiveIncident) => void;
  /** allowed_actions.ack_incident del /me (server-driven, default-deny). */
  canAck: boolean;
  onAck: (incidentId: string) => void;
  /** allowed_actions.relocate_epicenter (T-1.51). */
  canRelocate: boolean;
  onRelocate: (incidentId: string) => void;
  /** allowed_actions.request_dictamen (T-1.51). */
  canRequestDictamen: boolean;
  onRequestDictamen: (incidentId: string) => void;
  /** [T-2.50] Estaciones del snapshot: solo para el orden por DISTANCIA. */
  sites?: MapSiteState[];
  /** [T-2.50] Epicentro de referencia del orden por distancia (null = no hay). */
  epicenter?: MapEpicenter | null;
}

/** Explica el gate del botón (regla de oro 7: un disabled mudo no informa). */
function gateTitle(allowed: boolean, selected: boolean): string | undefined {
  if (!allowed) return "Tu rol no tiene esta acción (allowed_actions)";
  if (!selected) return "Selecciona un incidente primero";
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
  siteInfoOf,
  nowMs,
  liveStatus,
  operatorLabel,
  selectedId,
  onSelect,
  canAck,
  onAck,
  canRelocate,
  onRelocate,
  canRequestDictamen,
  onRequestDictamen,
  sites = [],
  epicenter = null,
}: IncidentTableProps) {
  const live = liveStatus === "ready";
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
  return (
    <section className="soc-incidents" data-screen-label="Incidents queue">
      <header className="soc-incidents__hd">
        <h3 className="soc-incidents__title">
          <List size={16} aria-hidden style={{ color: "var(--tk-cyan)" }} />
          Incidentes Abiertos
          <span className="soc-incidents__count">{incidents.length} ACTIVOS</span>
        </h3>
        <div
          style={{
            display: "flex",
            gap: 12,
            alignItems: "center",
            color: "var(--tk-fg-3)",
            fontSize: 11,
            fontFamily: "var(--tk-font-mono)",
            letterSpacing: "0.04em",
          }}
        >
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
          <span
            data-testid="live-pill"
            style={{ color: live ? "var(--tk-status-normal)" : "var(--tk-status-warning)" }}
          >
            {live ? "● LIVE" : "● SIN LIVE"}
          </span>
        </div>
      </header>

      {/* [T-2.55] Estado VACÍO explícito. Sin él, cero incidentes producía un
          <tbody> hueco bajo los encabezados: indistinguible de "la cola no
          cargó". `loading`/`error` de la fuente los resuelve el StateFrame del
          wall, que envuelve a esta tabla y no la monta hasta tener datos; aquí
          se declara lo único que el wall no puede saber: que la cola está
          vacía porque no hay incidentes abiertos, que es una BUENA noticia. */}
      <StateFrame
        label="INCIDENTES ABIERTOS"
        loading={false}
        empty={rows.length === 0}
        emptyText="SIN INCIDENTES ABIERTOS EN EL ALCANCE"
      >
        <table className="soc-table">
          <thead>
            <tr>
              <th style={{ width: "26%" }}>Sitio</th>
              <th style={{ width: "14%" }}>Severidad</th>
              <th style={{ width: "24%" }}>Coordenadas</th>
              <th style={{ width: "10%" }}>PGA</th>
              <th style={{ width: "14%" }}>Hora UTC</th>
              <th style={{ width: "12%" }}>Edad</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((incident) => {
              const site = siteInfoOf(incident.site_id);
              return (
                <tr
                  key={incident.incident_id}
                  onClick={() => onSelect(incident)}
                  aria-selected={incident.incident_id === selectedId}
                  style={{ cursor: "pointer" }}
                >
                  <td className="soc-table__site">
                    <span
                      className="soc-dot"
                      style={{ color: SEV_DOT[incident.severity] ?? "var(--tk-status-warning)" }}
                    />
                    {site?.name ?? `SITIO ${incident.site_id.slice(0, 8)}`}
                  </td>
                  <td>
                    <SevTag severity={incident.severity} />
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
        </table>
      </StateFrame>

      {distanceUnavailable && (
        <p className="soc-incidents__note" data-testid="order-distance-unavailable" role="status">
          SIN EPICENTRO LOCALIZADO · ORDENADO POR SEVERIDAD
        </p>
      )}

      <footer className="soc-incidents__ft">
        <div className="soc-incidents__operator">
          <span className="soc-meta">Operador</span>
          <span className="soc-mono" data-testid="operator-label">
            {operatorLabel}
          </span>
          <span className="soc-pill soc-pill--ok" style={{ fontSize: 9 }}>
            <UserCheck size={11} aria-hidden /> AUTH · MFA
          </span>
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
            <ConfirmButton
              icon={<FileSearch size={13} aria-hidden />}
              label="SOLICITAR DICTAMEN TÉCNICO"
              armedLabel="CLIC DE NUEVO PARA SOLICITAR"
              variant="secondary"
              disabled={!canRequestDictamen || selectedId === null}
              onConfirm={() => {
                if (selectedId !== null) onRequestDictamen(selectedId);
              }}
            />
          </span>
          <ConfirmButton
            icon={<CheckCircle2 size={13} aria-hidden />}
            label="CONFIRMAR ACUSE"
            armedLabel="CLIC DE NUEVO PARA ACUSAR"
            variant="primary"
            disabled={!canAck || selectedId === null}
            onConfirm={() => {
              if (selectedId !== null) onAck(selectedId);
            }}
          />
        </div>
      </footer>
    </section>
  );
}
