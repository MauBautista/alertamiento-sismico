import { BatteryLow, PlugZap } from "lucide-react";

export interface UpsGaugeProps {
  /** power_status del último device_health: line | battery | unknown | null. */
  powerStatus: string | null | undefined;
  batteryPct: number | null | undefined;
}

/**
 * Gauge de UPS del gabinete. El color del fill es SOLO estilo visual (mockup);
 * el estado del gabinete sigue siendo derived_state del servidor. Sin dato no
 * se finge 0%: se muestra "—" y el fill queda vacío.
 */
export default function UpsGauge({ powerStatus, batteryPct }: UpsGaugeProps) {
  const onBattery = powerStatus === "battery";
  const known = powerStatus === "line" || powerStatus === "battery";
  const pct =
    typeof batteryPct === "number" ? Math.max(0, Math.min(100, Math.round(batteryPct))) : null;
  const kind = pct === null ? "warn" : pct < 40 ? "crit" : pct < 80 ? "warn" : "ok";

  return (
    <div className="fleet-ups">
      <div className="fleet-ups__hd">
        {onBattery ? <BatteryLow size={13} aria-hidden /> : <PlugZap size={13} aria-hidden />}
        <span className="fleet-ups__lbl">
          {onBattery ? "EN BATERÍA" : known ? "RED ELÉCTRICA" : "UPS · S/D"}
        </span>
        <span className={`fleet-ups__pct fleet-ups__pct--${kind}`}>
          {pct === null ? "—" : `${pct}%`}
        </span>
      </div>
      <div className="fleet-ups__bar">
        <div
          className={`fleet-ups__fill fleet-ups__fill--${kind}`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  );
}
