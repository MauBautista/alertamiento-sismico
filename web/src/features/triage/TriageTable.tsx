import SevTag from "../../components/SevTag";
import { utcStamp } from "../../lib/time";
import { epicenterKindOf, magnitudeOf } from "./model";
import type { TriageRow } from "./model";

/** Estados del CHECK de ``incidents.state`` con etiqueta de operador. */
const STATE_LABEL: Record<string, string> = {
  open: "ABIERTO",
  acked: "ACUSADO",
  in_review: "EN REVISIÓN",
  closed: "CERRADO",
};

function pga(row: TriageRow): string {
  return row.incident.max_pga_g === null ? "—" : `${row.incident.max_pga_g.toFixed(3)}g`;
}

export interface TriageTableProps {
  rows: TriageRow[];
  selectedId: string | null;
  onSelect: (row: TriageRow) => void;
}

/**
 * Historial de incidentes (port de la tabla de TriageHistory.jsx sobre datos reales).
 *
 * Desviaciones honestas frente al mockup:
 * - "Sitios n/8" era inventado: la fila ES un incidente de UN sitio. Se muestra el
 *   sitio y, aparte, los NODOS del quórum (`seismic_events.meta.node_count`).
 * - La columna "Dictamen" exigiría una petición por fila (no hay endpoint de lista);
 *   el dictamen vive en el panel de detalle. Aquí va el `state` del incidente, real.
 * - "Epicentro" son coordenadas: no existe geocodificación inversa a nombre de lugar.
 */
export default function TriageTable({ rows, selectedId, onSelect }: TriageTableProps) {
  return (
    <table role="grid" className="soc-table triage-table">
      <thead>
        <tr>
          <th style={{ width: "24%" }}>Fecha · ID</th>
          <th style={{ width: "8%" }}>Mag</th>
          <th style={{ width: "14%" }}>Epicentro</th>
          <th style={{ width: "10%" }}>PGA</th>
          <th style={{ width: "14%" }}>Severidad</th>
          <th style={{ width: "8%" }}>Nodos</th>
          <th style={{ width: "22%" }}>Sitio · Estado</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const inc = row.incident;
          const selected = inc.incident_id === selectedId;
          const mag = magnitudeOf(row.event);
          const epi = epicenterKindOf(row.event);
          return (
            <tr
              key={inc.incident_id}
              className={selected ? "is-selected" : ""}
              aria-selected={selected}
              data-testid="triage-row"
              onClick={() => onSelect(row)}
            >
              <td>
                {/* [T-2.39] La fila era un <tr onClick> sin teclado, y `aria-selected`
                    fuera de un grid es inválido. La primera celda pasa a ser un botón
                    real: se enfoca, responde a Enter/Espacio y anuncia la fila. */}
                <button
                  type="button"
                  className="triage-table__pick"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(row);
                  }}
                >
                  <span className="triage-table__dt">
                    {utcStamp(Date.parse(inc.opened_at))} UTC
                  </span>
                  <span className="triage-table__id">
                    {inc.event_id ?? inc.incident_id.slice(0, 13)}
                  </span>
                </button>
              </td>
              <td>
                <span className="soc-mono triage-table__mag" title={mag.title}>
                  {mag.label}
                </span>
              </td>
              <td className="soc-mono" title={epi.note}>
                {epi.label}
                {epi.kind === "centroid" && (
                  <span className="triage-table__note"> · CENTROIDE</span>
                )}
              </td>
              <td className={`soc-mono ${inc.severity !== "info" ? "soc-table__pga" : ""}`}>
                {pga(row)}
              </td>
              <td>
                <SevTag severity={inc.severity} />
              </td>
              <td className="soc-mono">{row.nodeCount ?? "—"}</td>
              <td className="triage-table__dictamen">
                {row.siteName} · {STATE_LABEL[inc.state] ?? inc.state.toUpperCase()}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
