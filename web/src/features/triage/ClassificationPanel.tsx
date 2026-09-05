// [T-5.12] Clasificar un incidente — y la tasa que sale de hacerlo.
//
// El defecto que cierra: cerrar un incidente no pedía ni admitía una razón, así
// que la tasa de falsos positivos —la métrica que decide si un cliente renueva—
// no era calculable ni a mano sobre la base.
//
// DOS PROPIEDADES QUE NO SON COSMÉTICAS:
//
//  1. **Corregir INSERTA.** No hay «editar»: se clasifica otra vez declarando a
//     cuál sustituye, y las dos quedan a la vista. La base lo impone (append-only
//     con sus dos capas); esta pantalla solo evita prometer lo que no puede.
//  2. **`INDETERMINADO` es un botón como los demás.** No es el estado en el que
//     caen los que nadie miró: ésos no tienen fila, y la tarjeta de la tasa los
//     cuenta aparte.

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { utcClock } from "../../lib/time";
import { CLASIFICACIONES, useClassification, useClassificationStats } from "./useClassification";

const ETIQUETA: Record<string, string> = Object.fromEntries(
  CLASIFICACIONES.map((c) => [c.value, c.label]),
);

export function ClassificationPanel({ incidentId }: { incidentId: string }) {
  const puede = useSessionStore((s) => s.me?.allowed_actions.classify_incident === true);
  const { items, current, loading, readError, updatedAt, refetch, clasificar, pending } =
    useClassification(incidentId);

  return (
    <StateFrame
      label="CLASIFICACIÓN"
      loading={loading}
      error={readError && items.length === 0 ? "no se pudo leer la clasificación" : null}
      onRetry={refetch}
      empty={items.length === 0 && !puede}
      emptyText="SIN CLASIFICAR"
      staleSince={readError && items.length > 0 ? updatedAt : null}
    >
      <div className="triage-clasif" data-testid="classification-panel">
        <div className="triage-clasif__actual" data-testid="classification-current">
          {current === null ? "SIN CLASIFICAR" : ETIQUETA[current.classification]}
        </div>

        {puede && (
          <div className="triage-clasif__btns">
            {CLASIFICACIONES.map((c) => (
              <button
                key={c.value}
                type="button"
                className="triage-clasif__btn"
                data-testid={`classify-${c.value}`}
                title={c.hint}
                disabled={pending}
                onClick={() =>
                  clasificar({
                    classification: c.value,
                    // Corregir SUSTITUYE a la vigente; la primera vez no hay a
                    // quién sustituir. Nunca se edita una fila.
                    supersedesId: current?.classification_id,
                  })
                }
              >
                {c.label}
              </button>
            ))}
          </div>
        )}

        {items.length > 1 && (
          <ul className="triage-clasif__hist" data-testid="classification-history">
            {items.map((i) => (
              <li key={i.classification_id}>
                {utcClock(Date.parse(i.classified_at))} UTC · {ETIQUETA[i.classification]}
                {i.current ? " · VIGENTE" : " · SUSTITUIDA"}
              </li>
            ))}
          </ul>
        )}
      </div>
    </StateFrame>
  );
}

/** `0.1234` → `12.3 %`. Sin dato dice por qué, jamás `0 %`. */
export function tasaLegible(v: number | null | undefined): string {
  if (v === null || v === undefined) return "S/D";
  return `${(v * 100).toFixed(1)} %`;
}

export function FalsePositiveRate() {
  const { stats, loading, readError, updatedAt, refetch } = useClassificationStats();

  return (
    <StateFrame
      label="FALSOS POSITIVOS"
      loading={loading}
      error={readError && stats === null ? "no se pudo leer la tasa" : null}
      onRetry={refetch}
      empty={stats !== null && stats.total === 0}
      emptyText="SIN INCIDENTES EN LA VENTANA"
      staleSince={readError && stats !== null ? updatedAt : null}
    >
      {stats !== null && stats.total > 0 ? (
        <div className="triage-tasa" data-testid="false-positive-rate">
          <span className="triage-tasa__v" data-testid="fp-rate-value">
            {tasaLegible(stats.false_positive_rate)}
          </span>
          {/* Los sin clasificar van SIEMPRE a la vista. Un porcentaje calculado
              sobre lo clasificado, con lo no clasificado escondido, se lee como
              una medición y es una muestra sesgada por quién tuvo tiempo. */}
          <span className="triage-tasa__sin" data-testid="fp-unclassified">
            {stats.unclassified} DE {stats.total} SIN CLASIFICAR
          </span>
          {stats.false_positive_rate === null && (
            <span className="triage-tasa__nota">
              Sin nada clasificado no hay tasa: no es cero, es que nadie miró
            </span>
          )}
        </div>
      ) : null}
    </StateFrame>
  );
}
