// Eje temporal compartido por las trazas (T-1.34). UTC, como todos los relojes del SOC.

import { utcClock } from "../../lib/time";
import { timeTicks } from "./svgScale";

const HEIGHT = 16;

export interface TimeAxisProps {
  /** Epoch ms, ascendente. Menos de dos ⇒ no hay eje que dibujar. */
  timestamps: number[];
  width: number;
}

export default function TimeAxis({ timestamps, width }: TimeAxisProps) {
  const ticks = timeTicks(timestamps, width);
  if (ticks.length === 0) return null;
  return (
    <svg
      viewBox={`0 0 ${width} ${HEIGHT}`}
      className="soc-timeaxis"
      preserveAspectRatio="none"
      role="img"
      aria-label="Eje temporal (UTC)"
      data-testid="time-axis"
    >
      {ticks.map(({ ts, x }) => (
        <g key={ts}>
          <line x1={x} y1="0" x2={x} y2="3" stroke="rgba(0,191,255,0.25)" strokeWidth="1" />
          <text
            x={Math.min(Math.max(x, 18), width - 18)}
            y="12"
            textAnchor="middle"
            fontSize="8"
            fill="rgba(160,200,220,0.7)"
          >
            {utcClock(ts)}
          </text>
        </g>
      ))}
    </svg>
  );
}
