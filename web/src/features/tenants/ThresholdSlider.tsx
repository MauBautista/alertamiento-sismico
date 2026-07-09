export interface ThresholdSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  /** Valor a partir del cual el umbral entra en zona de disparo. */
  dangerAt: number;
  hint: string;
  /** false ⇒ el valor mostrado es el DEFAULT del edge, no algo que el tenant fijó. */
  fromConfig: boolean;
  disabled?: boolean;
  onChange: (value: number) => void;
}

function zoneOf(value: number, dangerAt: number): "ok" | "warn" | "crit" {
  if (value >= dangerAt) {
    return "crit";
  }
  return value >= dangerAt * 0.6 ? "warn" : "ok";
}

/**
 * Port de `ThresholdSlider` del mockup. Escribe en `config.edge.thresholds`, que es
 * la ÚNICA rama que el worker de sync publica al gabinete: un umbral guardado en
 * cualquier otra clave no llegaría jamás al actuador.
 *
 * Cuando el valor viene del default del edge (clave ausente en el config) se rotula:
 * el operador debe saber que nadie fijó ese número para su tenant.
 */
export default function ThresholdSlider({
  label,
  value,
  min,
  max,
  step,
  unit,
  dangerAt,
  hint,
  fromConfig,
  disabled = false,
  onChange,
}: ThresholdSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  const dangerPct = ((dangerAt - min) / (max - min)) * 100;
  const zone = zoneOf(value, dangerAt);
  const decimals = step < 1 ? 3 : 1;

  return (
    <div className="mt-slider">
      <div className="mt-slider__hd">
        <span className="soc-meta">
          {label}
          {!fromConfig && " · DEFAULT DEL EDGE"}
        </span>
        <span className={`mt-slider__val mt-slider__val--${zone}`}>
          {value.toFixed(decimals)}
          <span className="unit">{unit}</span>
        </span>
      </div>
      <div className="mt-slider__track-wrap">
        <div
          className="mt-slider__track"
          style={{
            background: `linear-gradient(to right,
              var(--tk-status-normal-15) 0%,
              var(--tk-status-normal-15) ${dangerPct * 0.6}%,
              var(--tk-status-warning-15) ${dangerPct * 0.6}%,
              var(--tk-status-warning-15) ${dangerPct}%,
              var(--tk-status-critical-15) ${dangerPct}%,
              var(--tk-status-critical-15) 100%)`,
          }}
        >
          <div
            className={`mt-slider__fill mt-slider__fill--${zone}`}
            style={{ width: `${pct}%` }}
          />
          <div
            className={`mt-slider__thumb mt-slider__thumb--${zone}`}
            style={{ left: `${pct}%` }}
          />
        </div>
        <input
          type="range"
          className="mt-slider__input"
          aria-label={label}
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(parseFloat(e.target.value))}
        />
      </div>
      <div className="mt-slider__scale">
        <span>
          {min.toFixed(decimals)}
          {unit}
        </span>
        <span>
          {max.toFixed(decimals)}
          {unit}
        </span>
      </div>
      <div className="mt-slider__hint">{hint}</div>
    </div>
  );
}
