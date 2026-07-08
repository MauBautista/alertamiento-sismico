// Strip rodante de features 1 s (T-1.27). NO es waveform crudo (regla de
// oro 9): cada columna es el PGA de un segundo; el clipping se marca arriba.

import { useMemo } from "react";

import type { FeaturePoint } from "./useSiteFeatures";

const WIDTH = 600;
const HEIGHT = 80;
const BASELINE = HEIGHT - 6;
const TOP = 8;
/** Piso del eje: 0.05 g — micro-tremor no debe verse plano en cero absoluto. */
const MIN_SCALE_G = 0.05;

export interface FeatureStripProps {
  points: FeaturePoint[];
}

export default function FeatureStrip({ points }: FeatureStripProps) {
  const { path, clippingXs, lastY } = useMemo(() => {
    if (points.length === 0) {
      return { path: "", clippingXs: [] as number[], lastY: BASELINE };
    }
    const scale = Math.max(MIN_SCALE_G, ...points.map((p) => p.pga ?? 0));
    const step = points.length > 1 ? WIDTH / (points.length - 1) : 0;
    const ys = points.map((p) => BASELINE - ((p.pga ?? 0) / scale) * (BASELINE - TOP));
    return {
      path: ys
        .map((y, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${y.toFixed(1)}`)
        .join(" "),
      clippingXs: points.flatMap((p, i) => (p.clipping ? [i * step] : [])),
      lastY: ys[ys.length - 1],
    };
  }, [points]);

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="soc-sismograma"
      preserveAspectRatio="none"
      role="img"
      aria-label="Features 1 s del sitio (PGA por segundo)"
      data-testid="feature-strip"
    >
      <line
        x1="0"
        y1={BASELINE}
        x2={WIDTH}
        y2={BASELINE}
        stroke="rgba(0,191,255,0.10)"
        strokeWidth="1"
        strokeDasharray="2 3"
      />
      <line x1="0" y1="20" x2={WIDTH} y2="20" stroke="rgba(0,191,255,0.05)" strokeWidth="1" />
      <line x1="0" y1="50" x2={WIDTH} y2="50" stroke="rgba(0,191,255,0.05)" strokeWidth="1" />
      {path !== "" && <path d={path} stroke="#00BFFF" strokeWidth="1.4" fill="none" />}
      {clippingXs.map((x) => (
        <line
          key={x}
          x1={x}
          y1="2"
          x2={x}
          y2="8"
          stroke="var(--tk-status-critical, #FF5252)"
          strokeWidth="2"
          data-testid="clipping-tick"
        />
      ))}
      {path !== "" && <circle cx={WIDTH - 1} cy={lastY} r="2.4" fill="#00E5FF" />}
    </svg>
  );
}
