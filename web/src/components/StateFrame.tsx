import type { ReactNode } from "react";

import { utcClock } from "../lib/time";

export interface StateFrameProps {
  /** Nombre del panel, para mensajes de estado y accesibilidad. */
  label: string;
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean;
  emptyText?: string;
  /**
   * Epoch ms del último dato fresco cuando el dato YA se considera viejo;
   * null/undefined = fresco. El umbral lo decide el dueño del dato.
   */
  staleSince?: number | null;
  /**
   * Clase(s) de layout del DUEÑO aplicadas al wrapper en TODOS los estados
   * (T-1.50). El caso que motivó esto: el grid del live wall
   * (`.soc-main { grid-template-rows: minmax(0,1fr) auto }`) esperaba a
   * `.soc-stage`/`.soc-incidents` como items directos, pero este wrapper los
   * envolvía y `.soc-stage` (solo hijos absolutos) colapsaba a altura 0 — el
   * mapa existía e "invisible". jsdom no hace layout: solo un contrato DOM
   * puede vigilarlo.
   */
  className?: string;
  children: ReactNode;
}

function cls(base: string, extra?: string): string {
  return extra ? `${base} ${extra}` : base;
}

/**
 * LA PRECEDENCIA, como TABLA y no como cadena de `if`. [T-2.84.c]
 *
 * Existe para que sea un PARÁMETRO del contrato y no quede cableada en los 27
 * componentes que pintan dato de servidor. `T-2.79.d` tiene que decidir qué
 * gana entre `empty` y `stale` cuando los dos son ciertos (una lista vacía que
 * además lleva diez minutos sin refrescar: ¿«SIN DATOS» o «DATOS RETENIDOS»?).
 * Esa decisión es de Mauricio; cuando llegue se cambia ESTE array y
 * `resolveState` la obedece — ningún componente tiene que enterarse.
 *
 * `src/serverDataCensus.test.ts` vigila que nadie más materialice `data-state`,
 * que es lo que convertiría cada copia en una precedencia paralela.
 */
export const STATE_PRECEDENCE = ["loading", "error", "empty", "stale"] as const;

export type FrameState = (typeof STATE_PRECEDENCE)[number] | "ready";

export interface StateInputs {
  loading: boolean;
  error?: string | null;
  empty?: boolean;
  /** Ya evaluado por el dueño del dato: `staleSince` presente ⇒ true. */
  stale: boolean;
}

/**
 * El ÚNICO sitio donde se decide qué estado gana. Recorre `STATE_PRECEDENCE`
 * en orden: cambiar la tabla cambia la conducta, que es justo lo que
 * `T-2.79.d` necesitará.
 */
export function resolveState(inputs: StateInputs): FrameState {
  for (const state of STATE_PRECEDENCE) {
    if (state === "loading" && inputs.loading) return state;
    if (
      state === "error" &&
      inputs.error !== null &&
      inputs.error !== undefined &&
      inputs.error !== ""
    )
      return state;
    if (state === "empty" && inputs.empty === true) return state;
    if (state === "stale" && inputs.stale) return state;
  }
  return "ready";
}

/**
 * Enforcer de los 4 estados obligatorios (regla de oro 7). La precedencia NO
 * vive aquí: la decide `resolveState` sobre `STATE_PRECEDENCE`. En stale el
 * dato sigue visible pero SIEMPRE bajo el banner "DATOS RETENIDOS" — un dato
 * congelado jamás se presenta como live. Los tests lo verifican vía
 * `data-state` (helper expectFourStates).
 */
export default function StateFrame({
  label,
  loading,
  error,
  onRetry,
  empty,
  emptyText,
  staleSince,
  className,
  children,
}: StateFrameProps) {
  const stale = staleSince !== null && staleSince !== undefined;
  const state = resolveState({ loading, error, empty, stale });

  if (state === "loading") {
    return (
      <div
        className={cls("soc-stateframe soc-stateframe--status", className)}
        data-state="loading"
        aria-busy="true"
      >
        <span>CARGANDO · {label}…</span>
      </div>
    );
  }
  if (state === "error") {
    return (
      <div
        className={cls("soc-stateframe soc-stateframe--status", className)}
        data-state="error"
        role="alert"
      >
        <span className="soc-stateframe__error">{error}</span>
        {onRetry && (
          <button type="button" className="soc-btn soc-btn--secondary" onClick={onRetry}>
            REINTENTAR
          </button>
        )}
      </div>
    );
  }
  if (state === "empty") {
    return (
      <div className={cls("soc-stateframe soc-stateframe--status", className)} data-state="empty">
        <span>{emptyText ?? `SIN DATOS · ${label}`}</span>
      </div>
    );
  }
  return (
    <div className={cls("soc-stateframe", className)} data-state={state}>
      {state === "stale" && staleSince !== null && staleSince !== undefined && (
        <div className="soc-stateframe__stale" role="status">
          DATOS RETENIDOS · {utcClock(staleSince)} UTC
        </div>
      )}
      {children}
    </div>
  );
}
