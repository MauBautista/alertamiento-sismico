// Cola de incidentes abiertos (T-1.27): filas live + barra de acciones de
// operador. Desviaciones RATIFICADAS: "WS · LIVE" (no GraphQL) y la identidad
// REAL de la sesión (no un selector de turno). El acuse es two-step y está
// gateado por allowed_actions.ack_incident (default-deny server-driven).

import { CheckCircle2, FileSearch, List, MapPin, UserCheck } from "lucide-react";

import ConfirmButton from "../../components/ConfirmButton";
import SevTag from "../../components/SevTag";
import { secondsSince, utcClock } from "../../lib/time";
import type { LiveStatus } from "../../lib/ws";
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
}: IncidentTableProps) {
  const live = liveStatus === "ready";
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
          <span>WS · LIVE</span>
          <span
            data-testid="live-pill"
            style={{ color: live ? "var(--tk-status-normal)" : "var(--tk-status-warning)" }}
          >
            {live ? "● LIVE" : "● SIN LIVE"}
          </span>
        </div>
      </header>

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
          {incidents.map((incident) => {
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
                <td className={`soc-mono ${incident.severity !== "info" ? "soc-table__pga" : ""}`}>
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
          <ConfirmButton
            icon={<MapPin size={13} aria-hidden />}
            label="REUBICAR EPICENTRO"
            variant="secondary"
            disabled
          />
          <ConfirmButton
            icon={<FileSearch size={13} aria-hidden />}
            label="SOLICITAR DICTAMEN TÉCNICO"
            variant="secondary"
            disabled
          />
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
