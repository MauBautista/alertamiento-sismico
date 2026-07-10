// Catálogo de referencia de sismos relevantes (T-1.52).
//
// CLARAMENTE SEPARADO del historial del tenant: estos NO son incidentes — son
// sismos históricos REALES de catálogos oficiales (SSN/USGS, ratificados en
// T-1.46) para dar contexto al operador. La magnitud aquí es dato de catálogo
// post-hoc, NO "magnitud preliminar" en vivo (blueprint §14 intacto): cada
// fila cita su fuente. Sin SevTag ni estados de incidente — no se disfraza.

import { BookOpen, ChevronDown } from "lucide-react";
import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useCatalog } from "./useCatalog";

function utcDate(iso: string): string {
  return iso.slice(0, 10);
}

export default function CatalogPanel() {
  const catalog = useCatalog();
  const [open, setOpen] = useState(false);

  return (
    <section className="triage-catalog" data-testid="catalog-panel">
      <button
        type="button"
        className="triage-catalog__hd"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="triage-catalog__title">
          <BookOpen size={13} aria-hidden />
          CATÁLOGO DE REFERENCIA · SSN/USGS
          <span className="triage-catalog__badge">REFERENCIA</span>
        </span>
        <span className="triage-catalog__sub">
          SISMOS HISTÓRICOS OFICIALES · NO SON INCIDENTES DEL TENANT
        </span>
        <ChevronDown
          size={14}
          aria-hidden
          className={`triage-catalog__chev${open ? " is-open" : ""}`}
        />
      </button>

      {open && (
        <StateFrame
          label="CATÁLOGO"
          loading={catalog.loading}
          error={catalog.error}
          onRetry={catalog.refetch}
          empty={catalog.items.length === 0}
          emptyText="CATÁLOGO SIN SEMBRAR (db/seeds/reference_earthquakes.sql)"
        >
          <table className="soc-table triage-catalog__table">
            <thead>
              <tr>
                <th>Fecha UTC</th>
                <th>Mag</th>
                <th>Región</th>
                <th>Prof.</th>
                <th>Epicentro</th>
                <th>Fuente</th>
              </tr>
            </thead>
            <tbody>
              {catalog.items.map((eq) => (
                <tr key={eq.catalog_key}>
                  <td className="soc-mono">{utcDate(eq.origin_time)}</td>
                  <td className="soc-mono triage-catalog__mag">M {eq.magnitude.toFixed(1)}</td>
                  <td>{eq.place}</td>
                  <td className="soc-mono">{eq.depth_km === null ? "—" : `${eq.depth_km} km`}</td>
                  <td className="soc-mono">
                    {Math.abs(eq.lat).toFixed(2)}°{eq.lat >= 0 ? "N" : "S"} ·{" "}
                    {Math.abs(eq.lon).toFixed(2)}°{eq.lon >= 0 ? "E" : "W"}
                  </td>
                  <td>
                    <span className="triage-catalog__src" title={eq.source_ref}>
                      {eq.source}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </StateFrame>
      )}
    </section>
  );
}
