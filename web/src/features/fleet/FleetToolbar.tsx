// Barra de búsqueda, orden y filtros de la Flota Edge (T-2.38).
//
// Con una docena de gabinetes la reja se recorre con la vista; con cien, no. La lógica
// vive en `fleetFilter.ts` (pura y testeable); aquí solo están los controles.

import { Search } from "lucide-react";

import { SORT_KEYS, SORT_LABEL } from "./fleetFilter";
import type { FleetFilters, SortKey } from "./fleetFilter";

export interface FleetToolbarProps {
  filters: FleetFilters;
  onChange: (next: FleetFilters) => void;
  /** Se pinta solo con `manage_fleet`: sin permiso no hay nada que restaurar. */
  includeRetired?: boolean;
  onIncludeRetired?: (value: boolean) => void;
  shown: number;
  total: number;
}

export default function FleetToolbar({
  filters,
  onChange,
  includeRetired,
  onIncludeRetired,
  shown,
  total,
}: FleetToolbarProps) {
  return (
    <div className="fleet__toolbar" data-testid="fleet-toolbar">
      <label className="fleet__search">
        <Search size={12} aria-hidden />
        <input
          type="search"
          value={filters.query}
          placeholder="Estación, código, serial o iot thing…"
          aria-label="Buscar en la flota"
          onChange={(e) => onChange({ ...filters, query: e.target.value })}
        />
      </label>

      <label className="fleet__sort">
        <span>ORDEN</span>
        <select
          value={filters.sort}
          aria-label="Orden de la flota"
          onChange={(e) => onChange({ ...filters, sort: e.target.value as SortKey })}
        >
          {SORT_KEYS.map((key) => (
            <option key={key} value={key}>
              {SORT_LABEL[key]}
            </option>
          ))}
        </select>
      </label>

      <label className="fleet__toggle">
        <input
          type="checkbox"
          checked={filters.hideOffline}
          onChange={(e) => onChange({ ...filters, hideOffline: e.target.checked })}
        />
        <span>OCULTAR SIN ENLACE</span>
      </label>

      {onIncludeRetired && (
        <label className="fleet__toggle" data-testid="fleet-include-retired">
          <input
            type="checkbox"
            checked={includeRetired ?? false}
            onChange={(e) => onIncludeRetired(e.target.checked)}
          />
          <span>VER RETIRADOS</span>
        </label>
      )}

      {/* Los KPI de arriba cuentan el TOTAL siempre; esta leyenda es la que dice
          cuánto se está viendo. Sin ella, un filtro activo haría creer que la flota
          encogió. */}
      {shown !== total && (
        <span className="fleet__shown" data-testid="fleet-shown">
          MOSTRANDO {shown} DE {total}
        </span>
      )}
    </div>
  );
}
