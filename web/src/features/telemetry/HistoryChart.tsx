// Historial de PGA por bucket (T-1.34). SVG a mano, sin librería de gráficas.
//
// Es el máximo por bucket, no una serie continua: entre dos picos no hubo silencio,
// hubo un agregado. Por eso se pinta como barras y no como línea — una línea sugeriría
// una interpolación que los datos no respaldan.

import { useMemo } from "react";

import { utcStamp } from "../../lib/time";
import NotCalibratedBadge from "./NotCalibratedBadge";
import { unitsFor } from "./calibration";
import { scaleOf } from "./svgScale";
import type { HistoryPoint, HistoryPreset } from "./useSiteMetrics";
import { HISTORY_PRESETS } from "./useSiteMetrics";

const WIDTH = 600;
const HEIGHT = 120;
const TOP = 8;
const BOTTOM = HEIGHT - 18;

export interface HistoryPresetPickerProps {
  preset: HistoryPreset;
  onPreset: (preset: HistoryPreset) => void;
}

/**
 * [A-111 · T-8.09] El selector de rango, suelto del gráfico.
 *
 * Vivía SOLO dentro de `HistoryChart`, y el gráfico dentro del `StateFrame` del
 * historial: con el rango vacío el marco pintaba «SIN MÉTRICAS EN EL RANGO» y el
 * selector desaparecía con él. Quien eligió 1H en un sitio tranquilo se quedaba
 * sin forma de volver a 24H o 7D. La página que tiene el marco lo pinta FUERA.
 */
export function HistoryPresetPicker({ preset, onPreset }: HistoryPresetPickerProps) {
  return (
    <div className="soc-history__presets" role="group" aria-label="Rango del historial">
      {HISTORY_PRESETS.map((p) => (
        <button
          key={p}
          type="button"
          className={`soc-chip ${p === preset ? "soc-chip--on" : ""}`}
          aria-pressed={p === preset}
          onClick={() => onPreset(p)}
        >
          {p.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export interface HistoryChartProps {
  points: HistoryPoint[];
  bucket: string;
  calibrated: boolean | undefined;
  /**
   * El rango, si el gráfico lo pinta él mismo. Ausente cuando el anfitrión ya
   * pinta `HistoryPresetPicker` fuera de su marco (A-111): dos selectores del
   * mismo rango en la misma tarjeta serían dos verdades.
   */
  preset?: HistoryPreset;
  onPreset?: (preset: HistoryPreset) => void;
}

export default function HistoryChart({
  points,
  bucket,
  calibrated,
  preset,
  onPreset,
}: HistoryChartProps) {
  const unit = unitsFor(calibrated).pga;
  const { bars, scale } = useMemo(() => {
    const values = points.map((p) => p.maxPga);
    const s = scaleOf(values);
    const step = points.length > 0 ? WIDTH / points.length : 0;
    return {
      scale: s,
      bars: points.map((p, i) => {
        const h = ((p.maxPga ?? 0) / s) * (BOTTOM - TOP);
        return { x: i * step, w: Math.max(1, step - 0.5), y: BOTTOM - h, h, ts: p.ts };
      }),
    };
  }, [points]);

  return (
    <div className="soc-history">
      <div className="soc-history__head">
        <span className="soc-mono">MÁXIMO PGA · BUCKET {bucket.toUpperCase()}</span>
        {preset !== undefined && onPreset !== undefined && (
          <HistoryPresetPicker preset={preset} onPreset={onPreset} />
        )}
        <NotCalibratedBadge calibrated={calibrated} />
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="soc-history__chart"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Máximo de PGA por bucket de ${bucket} (${unit})`}
        data-testid="history-chart"
      >
        <line
          x1="0"
          y1={BOTTOM}
          x2={WIDTH}
          y2={BOTTOM}
          stroke="rgba(0,191,255,0.15)"
          strokeWidth="1"
        />
        {bars.map((b) => (
          <rect key={b.ts} x={b.x} y={b.y} width={b.w} height={b.h} fill="#00BFFF" opacity="0.75" />
        ))}
      </svg>
      <div className="soc-history__foot soc-mono">
        <span>{points.length > 0 ? utcStamp(points[0].ts) : "—"}</span>
        <span>
          máx {scale.toFixed(3)} {unit}
        </span>
        <span>{points.length > 0 ? utcStamp(points[points.length - 1].ts) : "—"}</span>
      </div>
    </div>
  );
}
