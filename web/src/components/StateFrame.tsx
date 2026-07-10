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
 * Enforcer de los 4 estados obligatorios (regla de oro 7), con precedencia
 * loading > error > empty > stale. En stale el dato sigue visible pero SIEMPRE
 * bajo el banner "DATOS RETENIDOS" — un dato congelado jamás se presenta como
 * live. Los tests lo verifican vía `data-state` (helper expectFourStates).
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
  if (loading) {
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
  if (error) {
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
  if (empty) {
    return (
      <div className={cls("soc-stateframe soc-stateframe--status", className)} data-state="empty">
        <span>{emptyText ?? `SIN DATOS · ${label}`}</span>
      </div>
    );
  }
  const stale = staleSince !== null && staleSince !== undefined;
  return (
    <div className={cls("soc-stateframe", className)} data-state={stale ? "stale" : "ready"}>
      {stale && (
        <div className="soc-stateframe__stale" role="status">
          DATOS RETENIDOS · {utcClock(staleSince)} UTC
        </div>
      )}
      {children}
    </div>
  );
}
