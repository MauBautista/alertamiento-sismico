import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useNow } from "../../lib/useNow";
import { utcStamp } from "../../lib/time";
import { AUDIT_STALE_MS, EMPTY_FILTERS, isFiltering, useAudit } from "./useAudit";
import type { AuditFilters } from "./useAudit";

/** Meta de la fila, en una línea legible. `{}` ⇒ nada, no un "{}" decorativo. */
function metaSummary(meta: Record<string, unknown>): string {
  const entries = Object.entries(meta ?? {});
  if (entries.length === 0) {
    return "";
  }
  return entries
    .map(([k, v]) => `${k}=${typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

/**
 * T-2.52 · Bitácora de auditoría.
 *
 * `GET /audit` existe completo desde T-1.57 (filtros de actor/verbo/prefijo de
 * objeto, rango de fechas y paginación keyset) y hasta aquí no tenía UNA sola
 * pantalla que lo consumiera: la evidencia de cumplimiento solo se podía leer
 * abriendo una sesión SSM contra la base.
 *
 * Tres cosas que esta pantalla NO hace, a propósito:
 * - **No filtra en el cliente.** La RLS `audit_read` decide qué filas existen para
 *   cada rol y el endpoint ya trae los filtros. Duplicarlos daría dos verdades, y
 *   la del cliente mentiría en cuanto llegara la segunda página.
 * - **No ofrece escritura ni borrado.** `audit_log` es append-only por trigger y no
 *   se poda jamás (regla de oro 11); un botón de borrar sería un 403 permanente.
 * - **No inventa un total.** La paginación es keyset: se sabe si hay MÁS, no cuántas.
 *   Un contador "de 1.234" exigiría un COUNT sobre una tabla que solo crece.
 */
export default function AuditPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const data = useAudit(filters);
  const now = useNow(5000);

  const staleSince =
    !data.loading &&
    !data.error &&
    data.dataUpdatedAt > 0 &&
    now - data.dataUpdatedAt > AUDIT_STALE_MS
      ? data.dataUpdatedAt
      : null;

  function field(key: keyof AuditFilters, label: string, type = "text", placeholder = "") {
    return (
      <label className="audit__field">
        <span>{label}</span>
        <input
          type={type}
          value={draft[key]}
          placeholder={placeholder}
          onChange={(e) => setDraft((f) => ({ ...f, [key]: e.target.value }))}
        />
      </label>
    );
  }

  return (
    <section className="audit" data-screen-label="05 Auditoría">
      <header className="audit__hd">
        <div>
          <span className="soc-meta">CUMPLIMIENTO · EVIDENCIA</span>
          <h1 className="audit__title">Bitácora de Auditoría</h1>
          <p className="audit__sub">
            Registro append-only de cada acto con consecuencia: acuses, dictámenes, comandos de
            actuador, altas y retiros. No se edita, no se borra y no se poda por retención.
          </p>
        </div>
      </header>

      <form
        className="audit__filters"
        data-testid="audit-filters"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        {field("actor", "Actor", "text", "user:<sub> · gateway:<id>")}
        {field("verb", "Verbo", "text", "ack · siren_test · user_update")}
        {field("object", "Objeto (prefijo)", "text", "incident: · gateway:")}
        {field("from", "Desde (UTC)", "datetime-local")}
        {field("to", "Hasta (UTC)", "datetime-local")}
        <div className="audit__actions">
          <button type="submit" className="soc-btn">
            APLICAR
          </button>
          <button
            type="button"
            className="soc-btn soc-btn--secondary"
            disabled={!isFiltering(draft) && !isFiltering(filters)}
            // [T-2.59] Un botón apagado y mudo obliga a adivinar en mitad de un
            // turno (regla de oro 7). Aquí el motivo es siempre el mismo y cabe
            // en una línea: no hay nada que limpiar.
            title={
              !isFiltering(draft) && !isFiltering(filters)
                ? "No hay filtros aplicados que limpiar"
                : undefined
            }
            onClick={() => {
              setDraft(EMPTY_FILTERS);
              setFilters(EMPTY_FILTERS);
            }}
          >
            LIMPIAR
          </button>
        </div>
      </form>

      <StateFrame
        label="BITÁCORA"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={data.rows.length === 0}
        emptyText={
          isFiltering(filters)
            ? "SIN REGISTROS PARA EL FILTRO"
            : "SIN REGISTROS VISIBLES PARA ESTE ROL"
        }
        staleSince={staleSince}
        className="audit__frame"
      >
        <div className="audit__tablewrap">
          <table className="audit__table">
            <thead>
              <tr>
                <th scope="col">FECHA · UTC</th>
                <th scope="col">ACTOR</th>
                <th scope="col">VERBO</th>
                <th scope="col">OBJETO</th>
                <th scope="col">DETALLE</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.audit_id} data-testid="audit-row">
                  <td className="soc-mono audit__ts">{utcStamp(Date.parse(row.ts))}</td>
                  <td className="soc-mono">{row.actor}</td>
                  <td className="audit__verb">{row.verb}</td>
                  <td className="soc-mono audit__object">{row.object}</td>
                  <td className="audit__meta">{metaSummary(row.meta)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="audit__more">
          {data.hasMore ? (
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              disabled={data.loadingMore}
              onClick={data.loadMore}
            >
              {data.loadingMore ? "CARGANDO…" : "CARGAR MÁS"}
            </button>
          ) : (
            <span className="soc-meta">FIN DE LA BITÁCORA VISIBLE</span>
          )}
          <span className="soc-meta">{data.rows.length} REGISTRO(S) CARGADO(S)</span>
        </div>
      </StateFrame>
    </section>
  );
}
