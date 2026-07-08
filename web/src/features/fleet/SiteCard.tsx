import { Activity, Clock, Cpu, MapPin, Radio, ToggleRight, Zap } from "lucide-react";

import { utcClock } from "../../lib/time";
import LinkPill from "./LinkPill";
import RelayGrid from "./RelayGrid";
import UpsGauge from "./UpsGauge";
import type { FleetCabinet } from "./useFleet";

/** derived_state (server) → tono del pill. Desconocido ⇒ ámbar, nunca ok. */
const STATE_PILL: Record<string, "ok" | "warn" | "crit"> = {
  OPERATIVO: "ok",
  DEGRADADO: "warn",
  "SIN ENLACE": "crit",
};

/** Tarjeta de gabinete: pinta el estado YA derivado por el servidor (G7). */
export default function SiteCard({ cabinet }: { cabinet: FleetCabinet }) {
  const gw = cabinet.gateway;
  const offline = gw.derived_state === "SIN ENLACE";
  const pill = STATE_PILL[gw.derived_state] ?? "warn";
  const linkKind = offline ? "crit" : "ok";
  const mqttValue = offline
    ? "— sin enlace —"
    : gw.mqtt_rtt_ms != null
      ? `↔ ${gw.mqtt_rtt_ms.toFixed(1)} ms`
      : "s/d";
  const seedlinkValue = offline
    ? "— sin enlace —"
    : gw.seedlink_lag_s != null
      ? `lag ${gw.seedlink_lag_s.toFixed(2)} s`
      : "s/d";

  return (
    <article className={`fleet-card fleet-card--${pill}`} data-gateway={gw.gateway_id}>
      <header className="fleet-card__hd">
        <div>
          <div className="fleet-card__name">{cabinet.siteName}</div>
          <div className="fleet-card__loc">
            <MapPin size={11} aria-hidden />
            {cabinet.siteCode ?? gw.serial}
            {gw.iot_thing && <span className="fleet-card__tenant"> · {gw.iot_thing}</span>}
          </div>
        </div>
        <div className="fleet-card__id">
          <span className={`soc-pill soc-pill--${pill}`}>
            <span className="soc-dot" /> {gw.derived_state}
          </span>
          <span className="fleet-card__sid">{gw.serial}</span>
        </div>
      </header>

      <div className="fleet-card__links">
        <LinkPill
          kind={linkKind}
          label="MQTT BROKER"
          icon={<Radio size={12} aria-hidden />}
          value={mqttValue}
        />
        <LinkPill
          kind={linkKind}
          label="SEEDLINK · RS4D"
          icon={<Activity size={12} aria-hidden />}
          value={seedlinkValue}
        />
      </div>

      <UpsGauge powerStatus={gw.power_status} batteryPct={gw.battery_pct} />

      <div className="fleet-card__section">
        <div className="fleet-card__sectionhd">
          <ToggleRight size={12} aria-hidden />
          <span>ACTUADORES LOCALES · BACnet/IP</span>
        </div>
        {cabinet.relays && cabinet.relays.length > 0 ? (
          <>
            <RelayGrid relays={cabinet.relays} />
            <div className="fleet-card__derived">CONFIG ACTIVA · ESTADO DERIVADO DEL ENLACE</div>
          </>
        ) : (
          <div className="fleet-card__derived">
            {offline ? "ACTUADORES · S/D (SIN ENLACE)" : "ARMADOS · CONFIG DE RELAYS NO VISIBLE"}
          </div>
        )}
      </div>

      <footer className="fleet-card__ft">
        <div className="fleet-card__meta">
          <span>
            <Cpu size={11} aria-hidden /> {gw.fw_version ?? "fw s/d"}
          </span>
          <span className="tk-sep">·</span>
          <span>
            <Clock size={11} aria-hidden /> HB{" "}
            {gw.last_heartbeat_ts ? `${utcClock(Date.parse(gw.last_heartbeat_ts))} UTC` : "—"}
          </span>
        </div>
        <button
          type="button"
          className="fleet-card__diag"
          disabled
          title="Requiere acción self_test en el Command Service (extensión de T-1.23)"
        >
          <Zap size={13} aria-hidden /> AUTODIAGNÓSTICO SILENCIOSO
        </button>
      </footer>
    </article>
  );
}
