// Sparkline SVG sin dependencias (T-2.38).
//
// Se dibuja a mano por la misma razón que el resto de gráficos del proyecto
// (`svgScale.ts`, `HistoryChart`, `MultiChannelStrip`): una librería de charts pesa
// más que todo el módulo y no aporta nada a una línea de 60×18 px.
//
// Regla de oro 7 aplicada al detalle que más engaña de una sparkline: **un hueco no
// se interpola**. Una serie con `null` intercalados dibujaría, con cualquier librería,
// una recta que cruza el silencio — y esa recta se lee como "todo estuvo bien". Aquí
// el trazo se CORTA y el hueco se ve.

export interface SparklineProps {
  /** `null` = ese tramo no reportó. NO es cero. */
  values: (number | null)[];
  label: string;
  width?: number;
  height?: number;
}

/** Segmentos contiguos de puntos con dato; los `null` parten la serie. */
export function segmentsOf(values: (number | null)[], width: number, height: number): string[] {
  const known = values.filter((v): v is number => v !== null);
  if (known.length < 2) {
    return [];
  }
  const min = Math.min(...known);
  const max = Math.max(...known);
  // Serie constante: línea a media altura. Escalar por un rango 0 daría NaN.
  const span = max - min || 1;
  const stepX = values.length > 1 ? width / (values.length - 1) : 0;

  const paths: string[] = [];
  let current: string[] = [];
  values.forEach((v, i) => {
    if (v === null) {
      if (current.length > 1) paths.push(current.join(" "));
      current = [];
      return;
    }
    const x = (i * stepX).toFixed(1);
    const y = (height - ((v - min) / span) * height).toFixed(1);
    current.push(`${current.length === 0 ? "M" : "L"}${x},${y}`);
  });
  if (current.length > 1) paths.push(current.join(" "));
  return paths;
}

export default function Sparkline({ values, label, width = 60, height = 18 }: SparklineProps) {
  const paths = segmentsOf(values, width, height);
  if (paths.length === 0) {
    // Menos de dos puntos con dato: no hay tendencia que dibujar. Una línea plana
    // sería una afirmación sobre datos que no existen.
    return (
      <span className="sparkline sparkline--empty" title={`${label}: sin datos`}>
        S/D
      </span>
    );
  }
  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      data-testid="sparkline"
    >
      {paths.map((d) => (
        <path key={d} d={d} fill="none" stroke="currentColor" strokeWidth={1.2} />
      ))}
    </svg>
  );
}
