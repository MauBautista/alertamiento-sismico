// Prioridad sugerida de inspección por sitio (T-2.40).
//
// Un sismo no toca un edificio: toca la cartera entera. Hasta ahora la pantalla
// mostraba un incidente a la vez y el responsable tenía que abrir veinte fichas para
// decidir a dónde mandar al primer inspector.
//
// El encabezado dice explícitamente que NO es un dictamen. Un cuadro con semáforos
// junto a un panel de dictámenes se confunde solo si nadie lo desmiente.

import { PRIORITY_LABEL } from "./priority";
import type { PriorityRow } from "./priority";

export interface InspectionMatrixProps {
  rows: PriorityRow[];
  selectedId: string | null;
  onSelect: (incidentId: string) => void;
}

export default function InspectionMatrix({ rows, selectedId, onSelect }: InspectionMatrixProps) {
  if (rows.length <= 1) {
    // Con un solo sitio afectado no hay nada que priorizar: el panel sobraría y
    // sugeriría una comparación que no existe.
    return null;
  }
  return (
    <div className="soc-card inspection" data-testid="inspection-matrix">
      <div className="soc-card__hd">
        <div>
          <div>Prioridad sugerida de inspección</div>
          <div className="soc-card__sub">
            SACUDIDA MEDIDA × CRITICIDAD DEL INMUEBLE · {rows.length} SITIOS DEL MISMO EVENTO
          </div>
        </div>
      </div>
      <p className="inspection__disclaimer" data-testid="inspection-disclaimer">
        NO ES UN DICTAMEN. Es un orden de atención derivado de dos hechos. El dictamen de cada sitio
        vive en su propia cadena, append-only y firmada por un inspector.
      </p>
      <ul className="inspection__list">
        {rows.map((row) => (
          <li key={row.incidentId}>
            <button
              type="button"
              className={`inspection__row inspection__row--${row.priority.level}${
                row.incidentId === selectedId ? " is-selected" : ""
              }`}
              title={row.priority.why}
              onClick={() => onSelect(row.incidentId)}
            >
              <span className="inspection__dot" aria-hidden />
              <span className="inspection__site">{row.siteName}</span>
              <span className="inspection__pga soc-mono">
                {row.maxPgaG === null ? "SIN MEDICIÓN" : `${row.maxPgaG.toFixed(3)} g`}
              </span>
              <span className="inspection__level">{PRIORITY_LABEL[row.priority.level]}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
