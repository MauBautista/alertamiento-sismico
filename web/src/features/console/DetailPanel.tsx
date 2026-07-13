// Detalle del sitio (T-1.27, ampliado en T-1.50): strip de features live +
// readouts + SOH + card del INCIDENTE (trigger/evento/edad) + BMS AGRUPADO por
// actuador (último estado + traza expandible) + relés del gabinete + CCTV.
// Desviación RATIFICADA: el caption es honesto — "FEATURES 1 s · PROCESAMIENTO
// EDGE" (el RS4D muestrea 100 sps y el crudo NO se sube en continuo, regla de
// oro 9). La card CCTV es SIEMPRE visible con empty-state honesto: ahí VA la
// cámara ONVIF cuando exista el hardware (diferido documentado).

import { Activity, AlertTriangle, ChevronDown, Cpu, ToggleRight, Video, X } from "lucide-react";
import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { utcClock } from "../../lib/time";
import NotCalibratedBadge from "../telemetry/NotCalibratedBadge";
import { unitsFor } from "../telemetry/calibration";
import RelayGrid from "../fleet/RelayGrid";
import { groupActions } from "./bms";
import type { LiveIncident } from "./useLiveIncidents";
import type { IncidentActionsData } from "./useIncidentActions";
import type { SiteFeaturesData } from "./useSiteFeatures";
import { RELAYS_STALE_MS, type SiteRelaysData } from "./useSiteRelays";
import FeatureStrip from "./FeatureStrip";
import type { SiteStateFrame } from "@takab/sdk";

/** Sin frame de features tras esto (live 1 Hz) el strip pasa a DATOS RETENIDOS. */
export const FEATURES_STALE_MS = 15_000;

/** Etiqueta honesta del canal de disparo (incidents.trigger del schema). */
export const TRIGGER_LABEL: Record<string, string> = {
  sasmex: "SASMEX",
  local_threshold: "UMBRAL LOCAL EDGE",
  quorum: "QUÓRUM CLOUD",
  manual: "MANUAL",
};

/** Edad del incidente estilo wall: T+Xs / T+Xmin. */
export function ageLabel(openedAtIso: string, nowMs: number): string {
  const seconds = Math.max(0, Math.floor((nowMs - Date.parse(openedAtIso)) / 1000));
  return seconds < 120 ? `T+${seconds}s` : `T+${Math.floor(seconds / 60)}min`;
}

export interface DetailSite {
  site_id: string;
  name: string;
  coords: string | null;
}

export interface DetailPanelProps {
  site: DetailSite;
  features: SiteFeaturesData;
  soh: SiteStateFrame | null;
  actions: IncidentActionsData;
  /** Incidente enfocado del sitio (null = sin incidente abierto). */
  incident: LiveIncident | null;
  /** Relés del gabinete del sitio (config activa; null = no visible). */
  relays: SiteRelaysData;
  nowMs: number;
  onClose: () => void;
}

function SohBadge({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className={`soc-soh__badge soc-soh__badge--${ok ? "ok" : "warn"}`}>
      <span className="soc-dot" />
      <span className="soc-soh__label">{label}</span>
      <span className="soc-soh__value">{value}</span>
    </div>
  );
}

export default function DetailPanel({
  site,
  features,
  soh,
  actions,
  incident,
  relays,
  nowMs,
  onClose,
}: DetailPanelProps) {
  const [expandedKinds, setExpandedKinds] = useState<ReadonlySet<string>>(new Set());
  const toggleKind = (kind: string) =>
    setExpandedKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  const lastAck = actions.actions
    .filter((a) => a.kind === "ack")
    .sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))[0];
  const liveFresh =
    features.lastFrameAt !== null && nowMs - features.lastFrameAt < FEATURES_STALE_MS;
  const staleSince =
    !features.loading && !features.error && features.points.length > 0 && !liveFresh
      ? (features.lastFrameAt ?? features.points[features.points.length - 1].ts)
      : null;
  const latest = features.latest;
  // Sin `calibration_source` en los sensores del sitio, PGA/PGV son relativos (T-1.33).
  const units = unitsFor(features.calibrated);

  return (
    <aside className="soc-detail" data-testid="detail-panel">
      <header className="soc-detail__hd">
        <div>
          <span className="soc-meta">DETALLE DEL SITIO · EDGE+CLOUD</span>
          <h2 className="soc-detail__site">{site.name}</h2>
          <div className="soc-detail__sub">{site.coords ?? site.site_id}</div>
        </div>
        <button className="soc-icon-btn" onClick={onClose} aria-label="Cerrar">
          <X size={16} aria-hidden />
        </button>
      </header>

      {/* Features 1 s (vista segura) =================================== */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Activity size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Sensor RS4D · Features Live
            </div>
            <div className="soc-card__sub">FEATURES 1 s · SEEDLINK TCP · 100 SPS EN EDGE</div>
          </div>
          <span
            className={`soc-pill ${liveFresh ? "soc-pill--ok" : ""}`}
            style={{ fontSize: 9 }}
            data-testid="features-live-pill"
          >
            <span className={`soc-dot ${liveFresh ? "soc-dot--pulse" : ""}`} />{" "}
            {liveFresh ? "LIVE" : "SIN LIVE"}
          </span>
        </div>
        <StateFrame
          label="FEATURES DEL SITIO"
          loading={features.loading}
          error={features.error}
          onRetry={features.refetch}
          empty={features.points.length === 0}
          emptyText="SIN FEATURES EN LOS ÚLTIMOS 10 MIN"
          staleSince={staleSince}
        >
          <FeatureStrip points={features.points} />
          <div className="soc-sismograma__readout">
            <div>
              <div className="soc-readout__label">PGA</div>
              <div className="soc-readout__value">
                {latest?.pga?.toFixed(3) ?? "—"}
                <span className="unit">{units.pga}</span>
              </div>
            </div>
            <div>
              <div className="soc-readout__label">PGV</div>
              <div className="soc-readout__value">
                {latest?.pgv?.toFixed(1) ?? "—"}
                <span className="unit">{units.pgv}</span>
              </div>
            </div>
            <NotCalibratedBadge calibrated={features.calibrated} />
          </div>
          <div className="soc-soh">
            <SohBadge
              label="NTP OFFSET"
              value={
                soh?.ntp_offset_ms != null ? `±${Math.abs(soh.ntp_offset_ms).toFixed(0)} ms` : "S/D"
              }
              ok={soh?.ntp_offset_ms != null && Math.abs(soh.ntp_offset_ms) < 50}
            />
            <SohBadge
              label="CLIPPING"
              value={latest ? (latest.clipping ? "SATURADO" : "NORMAL") : "S/D"}
              ok={latest !== null && !latest.clipping}
            />
            <SohBadge
              label="LAG SEEDLINK"
              value={soh?.seedlink_lag_s != null ? `${soh.seedlink_lag_s.toFixed(1)} s` : "S/D"}
              ok={soh?.seedlink_lag_s != null && soh.seedlink_lag_s < 5}
            />
          </div>
          <div className="soc-edge-tag">
            <Cpu size={11} aria-hidden />
            FEATURES 1 s · PROCESAMIENTO EDGE
          </div>
        </StateFrame>
      </div>

      {/* Incidente enfocado (T-1.50): trigger/evento/edad — sin magnitud ni
          countdown (blueprint §14) ===================================== */}
      <div className="soc-card" data-testid="incident-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <AlertTriangle size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Incidente
            </div>
            <div className="soc-card__sub">CANAL DE DISPARO · EVENTO · ESTADO</div>
          </div>
        </div>
        {incident === null ? (
          <div className="soc-stateframe soc-stateframe--status" data-state="empty">
            <span>SIN INCIDENTE ABIERTO EN EL SITIO</span>
          </div>
        ) : (
          <div className="soc-incident-facts">
            <div className="soc-fact">
              <span className="soc-fact__label">TRIGGER</span>
              <span className="soc-fact__value">
                {TRIGGER_LABEL[incident.trigger] ?? incident.trigger.toUpperCase()}
              </span>
            </div>
            <div className="soc-fact">
              <span className="soc-fact__label">EVENTO</span>
              <span className="soc-fact__value soc-fact__value--mono">
                {incident.event_id ?? "SIN EVENTO SÍSMICO ASOCIADO"}
              </span>
            </div>
            <div className="soc-fact">
              <span className="soc-fact__label">ESTADO · EDAD</span>
              <span className="soc-fact__value">
                {incident.state.toUpperCase()} · {ageLabel(incident.opened_at, nowMs)}
              </span>
            </div>
            <div className="soc-fact">
              <span className="soc-fact__label">PGA MÁX · PGV MÁX</span>
              <span className="soc-fact__value soc-fact__value--mono">
                {incident.max_pga_g !== null ? `${incident.max_pga_g.toFixed(3)} g` : "—"}
                {" · "}
                {incident.max_pgv_cms !== null ? `${incident.max_pgv_cms.toFixed(1)} cm/s` : "—"}
              </span>
            </div>
            <div className="soc-fact">
              <span className="soc-fact__label">ÚLTIMO ACUSE</span>
              <span className="soc-fact__value soc-fact__value--mono">
                {lastAck
                  ? `${lastAck.actor.toUpperCase()} · ${utcClock(Date.parse(lastAck.ts))} UTC`
                  : "SIN ACUSE"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Actuadores y acciones (ACKs reales), AGRUPADOS por canal ======= */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ToggleRight size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Automatización y Actuadores (BMS)
            </div>
            <div className="soc-card__sub">ÚLTIMO ESTADO POR CANAL · TRAZA EXPANDIBLE</div>
          </div>
          <span className="soc-bacnet">⬢ BACnet®</span>
        </div>
        <StateFrame
          label="ACCIONES DEL INCIDENTE"
          loading={actions.loading}
          error={actions.error}
          onRetry={actions.refetch}
          empty={actions.actions.length === 0}
          emptyText="SIN ACCIONES REGISTRADAS (SIN INCIDENTE ABIERTO EN EL SITIO)"
        >
          <div className="soc-bms">
            {groupActions(actions.actions).map((group) => {
              const expanded = expandedKinds.has(group.kind);
              return (
                <div className="soc-bms__group" key={group.kind}>
                  <button
                    type="button"
                    className="soc-bms__row soc-bms__row--btn"
                    aria-expanded={expanded}
                    onClick={() => toggleKind(group.kind)}
                  >
                    <span className={`soc-check soc-check--${group.view.kind}`} />
                    <span>
                      <div className="soc-bms__label">
                        {group.label}
                        {group.count > 1 && <span className="soc-bms__count"> ×{group.count}</span>}
                      </div>
                      <div className="soc-bms__meta">
                        {group.last.actor.toUpperCase()} · {utcClock(Date.parse(group.last.ts))} UTC
                      </div>
                    </span>
                    <span className={`soc-bms__state soc-bms__state--${group.view.kind}`}>
                      {group.view.state}
                    </span>
                    <ChevronDown
                      size={12}
                      aria-hidden
                      className={`soc-bms__chev${expanded ? " is-open" : ""}`}
                    />
                  </button>
                  {expanded && (
                    <ol className="soc-bms__trace">
                      {group.trace.map((action) => (
                        <li key={action.action_id} className="soc-bms__trace-row">
                          <span className="soc-bms__meta">
                            {utcClock(Date.parse(action.ts))} UTC · {action.actor.toUpperCase()}
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              );
            })}
          </div>
        </StateFrame>
      </div>

      {/* Relés del gabinete (config activa; caché compartida con /fleet) = */}
      <div className="soc-card" data-testid="relays-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Cpu size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Relés del Gabinete
            </div>
            <div className="soc-card__sub">CONFIG ACTIVA DE RELAYS · ARMADO POR ENLACE</div>
          </div>
        </div>
        {/* M-6 (T-1.58): 4 estados — un 500 de /fleet/gateways NO es "config no
            visible"; el empty queda para lo genuinamente invisible (sin rule_set,
            sin gateway del sitio o rol sin /fleet, donde error llega null). */}
        <StateFrame
          label="RELÉS"
          loading={relays.loading}
          error={relays.error}
          onRetry={relays.refetch}
          empty={relays.relays === null}
          emptyText="CONFIG DE RELÉS NO VISIBLE (SIN RULE_SET O SIN ENLACE)"
          staleSince={
            !relays.loading &&
            !relays.error &&
            relays.dataUpdatedAt > 0 &&
            Date.now() - relays.dataUpdatedAt > RELAYS_STALE_MS
              ? relays.dataUpdatedAt
              : null
          }
        >
          <RelayGrid relays={relays.relays ?? []} />
        </StateFrame>
      </div>

      {/* CCTV ONVIF (T-1.50): SIEMPRE visible — aquí VA la cámara cuando
          exista el hardware. Empty-state honesto, jamás video fingido. ==== */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Video size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Verificación Visual · CCTV ONVIF
            </div>
            <div className="soc-card__sub">
              PROFILE S · RTSP/H.264 · CONTEO DE PERSONAS (FUTURO)
            </div>
          </div>
          <span className="soc-bacnet">⬢ ONVIF</span>
        </div>
        <div className="soc-cctv" data-testid="cctv-empty">
          <div className="soc-edge-tag">SIN CÁMARA CONFIGURADA · PENDIENTE DE HARDWARE</div>
        </div>
      </div>
    </aside>
  );
}
