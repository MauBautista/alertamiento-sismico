// Strip multicanal (T-1.34): una traza por canal SEED del RS4D.
//
// EHZ es el geófono (velocidad) y ENZ/ENN/ENE el acelerómetro de 3 ejes. Cada traza
// tiene su PROPIA escala vertical: el geófono y el acelerómetro no comparten unidad,
// y forzarlos a un eje común aplastaría uno de los dos.
//
// Sigue sin ser waveform crudo (regla de oro 9): cada punto es el pico de un segundo.

import { useMemo } from "react";

import { unitsFor } from "./calibration";
import { clippingXs, pathOf, scaleOf } from "./svgScale";
import type { Box } from "./svgScale";
import type { ChannelTrace } from "./useSiteChannels";
import TimeAxis from "./TimeAxis";

const WIDTH = 600;
const TRACE_HEIGHT = 54;
const BOX: Box = { width: WIDTH, height: TRACE_HEIGHT, top: 6, bottom: TRACE_HEIGHT - 6 };

/** El geófono mide velocidad; los tres ejes MEMS, aceleración. */
function isVelocityChannel(channel: string): boolean {
  return channel.startsWith("EH");
}

export interface MultiChannelStripProps {
  channels: ChannelTrace[];
  calibrated: boolean | undefined;
}

function ChannelRow({
  trace,
  calibrated,
}: {
  trace: ChannelTrace;
  calibrated: boolean | undefined;
}) {
  const velocity = isVelocityChannel(trace.channel);
  const values = velocity ? trace.pgv : trace.pga;
  const unit = velocity ? unitsFor(calibrated).pgv : unitsFor(calibrated).pga;

  const { path, scale, clips } = useMemo(() => {
    const s = scaleOf(values);
    return { path: pathOf(values, s, BOX), scale: s, clips: clippingXs(trace.clipping, WIDTH) };
  }, [values, trace.clipping]);

  return (
    <div className="soc-trace" data-testid={`trace-${trace.channel}`}>
      <div className="soc-trace__label">
        <span className="soc-mono">{trace.channel}</span>
        <span className="soc-trace__scale">
          {scale.toFixed(3)} {unit}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${TRACE_HEIGHT}`}
        className="soc-sismograma"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Canal ${trace.channel}: pico por segundo (${unit})`}
      >
        <line
          x1="0"
          y1={BOX.bottom}
          x2={WIDTH}
          y2={BOX.bottom}
          stroke="rgba(0,191,255,0.10)"
          strokeWidth="1"
          strokeDasharray="2 3"
        />
        {path !== "" && (
          <path d={path} stroke={velocity ? "#7CE7FF" : "#00BFFF"} strokeWidth="1.3" fill="none" />
        )}
        {clips.map((x) => (
          <line
            key={x}
            x1={x}
            y1="1"
            x2={x}
            y2="6"
            stroke="var(--tk-status-critical, #FF5252)"
            strokeWidth="2"
            data-testid="clipping-tick"
          />
        ))}
      </svg>
    </div>
  );
}

export default function MultiChannelStrip({ channels, calibrated }: MultiChannelStripProps) {
  // Los canales sin datos NO se pintan planos: su ausencia es la información.
  const axisTs = channels.length > 0 ? channels[0].ts : [];
  return (
    <div className="soc-traces" data-testid="multi-channel-strip">
      {channels.map((trace) => (
        <ChannelRow key={trace.channel} trace={trace} calibrated={calibrated} />
      ))}
      <TimeAxis timestamps={axisTs} width={WIDTH} />
    </div>
  );
}
