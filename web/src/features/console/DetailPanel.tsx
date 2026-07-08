// Detalle del sitio (T-1.27): strip de features live + readouts + SOH + traza
// de actuadores con ACKs del edge. Desviación RATIFICADA: el caption es
// honesto — "FEATURES 1 s · PROCESAMIENTO EDGE" (el RS4D muestrea 100 sps y el
// crudo NO se sube en continuo, regla de oro 9). CCTV ONVIF = placeholder
// detrás de VITE_FEATURE_CCTV (criterio #2, no bloquea).

import { Activity, Cpu, ToggleRight, Video, X } from "lucide-react";

import StateFrame from "../../components/StateFrame";
import { utcClock } from "../../lib/time";
import type { IncidentActionsData } from "./useIncidentActions";
import type { SiteFeaturesData } from "./useSiteFeatures";
import FeatureStrip from "./FeatureStrip";
import type { SiteStateFrame } from "@takab/sdk";

/** Sin frame de features tras esto (live 1 Hz) el strip pasa a DATOS RETENIDOS. */
export const FEATURES_STALE_MS = 15_000;

const ACTION_STATE: Record<string, { state: string; kind: "critical" | "warning" | "ok" }> = {
  siren_on: { state: "ACTIVADA", kind: "critical" },
  gas_valve_close: { state: "CERRADAS", kind: "warning" },
  elevator_recall: { state: "RETORNADOS", kind: "warning" },
  door_release: { state: "LIBERADOS", kind: "ok" },
  ack: { state: "ACUSADO", kind: "ok" },
};

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
  nowMs: number;
  cctvEnabled: boolean;
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
  nowMs,
  cctvEnabled,
  onClose,
}: DetailPanelProps) {
  const liveFresh =
    features.lastFrameAt !== null && nowMs - features.lastFrameAt < FEATURES_STALE_MS;
  const staleSince =
    !features.loading && !features.error && features.points.length > 0 && !liveFresh
      ? (features.lastFrameAt ?? features.points[features.points.length - 1].ts)
      : null;
  const latest = features.latest;

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
                <span className="unit">g</span>
              </div>
            </div>
            <div>
              <div className="soc-readout__label">PGV</div>
              <div className="soc-readout__value">
                {latest?.pgv?.toFixed(1) ?? "—"}
                <span className="unit">cm/s</span>
              </div>
            </div>
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

      {/* Actuadores y acciones (ACKs reales) =========================== */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ToggleRight size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
              Automatización y Actuadores (BMS)
            </div>
            <div className="soc-card__sub">TRAZA DEL INCIDENTE · ACKS EDGE+CLOUD</div>
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
            {actions.actions.map((action) => {
              const mapped = ACTION_STATE[action.kind] ?? {
                state: action.kind.toUpperCase(),
                kind: "ok" as const,
              };
              return (
                <div className="soc-bms__row" key={action.action_id}>
                  <span className={`soc-check soc-check--${mapped.kind}`} />
                  <span>
                    <div className="soc-bms__label">
                      {action.kind.replaceAll("_", " ").toUpperCase()}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--tk-fg-3)",
                        fontFamily: "var(--tk-font-mono)",
                        letterSpacing: "0.04em",
                        marginTop: 2,
                      }}
                    >
                      {action.actor.toUpperCase()} · {utcClock(Date.parse(action.ts))} UTC
                    </div>
                  </span>
                  <span className={`soc-bms__state soc-bms__state--${mapped.kind}`}>
                    {mapped.state}
                  </span>
                </div>
              );
            })}
          </div>
        </StateFrame>
      </div>

      {/* CCTV ONVIF (flag off en MVP — criterio #2) ==================== */}
      {cctvEnabled && (
        <div className="soc-card">
          <div className="soc-card__hd">
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Video size={14} aria-hidden style={{ color: "var(--tk-cyan)" }} />
                Verificación Visual · CCTV ONVIF
              </div>
              <div className="soc-card__sub">PROFILE S · PENDIENTE DE INTEGRACIÓN</div>
            </div>
            <span className="soc-bacnet">⬢ ONVIF</span>
          </div>
          <div className="soc-cctv" data-testid="cctv-placeholder">
            <div className="soc-edge-tag">PLACEHOLDER · SIN FUENTE RTSP CONFIGURADA</div>
          </div>
        </div>
      )}
    </aside>
  );
}
