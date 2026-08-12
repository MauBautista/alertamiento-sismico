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
 * componentes que pintan dato de servidor: se cambia ESTE array y `resolveState`
 * lo obedece — ningún componente tiene que enterarse.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * DECIDIDO [T-2.79.d · 2026-08-11]: entre `empty` y `stale`, GANA `stale`.
 *
 * Y la razón importa más que el orden, porque es lo único que impide que
 * alguien lo revierta dentro de seis meses viéndolo «menos útil»:
 *
 *   · `empty` afirma un hecho **sobre el mundo**: «no hay».
 *   · `stale` afirma un hecho **sobre nuestro conocimiento**: «no lo sé desde
 *     las hh:mm».
 *
 * Cuando los dos son ciertos a la vez, **sólo el segundo se puede verificar**.
 * La consola no tiene forma de saber si de verdad no hay nada o si lleva diez
 * minutos sin poder preguntar. Afirmar una ausencia que no puedes comprobar, en
 * la consola de un SOC, es el modo de fallo que produce «no hay heridos» cuando
 * lo que pasa es que el enlace está caído.
 *
 * Que `stale` sea **menos accionable es una virtud aquí, no un defecto**: manda
 * al operador a revisar el enlace en vez de a concluir. Es la regla de oro 7
 * («mostrar un dato congelado como si fuera live es peor que mostrar sin
 * datos») llevada al caso en que las dos cosas ocurren a la vez.
 *
 * El «no hay» NO se pierde: se FECHA. Ver `staleEmptyText` — con `empty`
 * encendido el marco imprime la ausencia con la hora en que se supo, en pasado.
 * Así el estado que gana sigue diciendo lo que el otro sabía.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Dos guardas sostienen esto y ninguna es opcional:
 *  · `src/serverDataCensus.test.ts` — nadie más materializa `data-state` (cada
 *    copia sería una precedencia paralela) y todo marco cablea sus 4 entradas.
 *  · `src/statePrecedenceCensus.test.ts` — nadie puede apagar su `empty` porque
 *    el dato esté viejo. Ese `sereno &&` es la precedencia LOCAL que produjo la
 *    franja muda del banner de privacidad, y es la forma que tiene un
 *    componente de sortear esta tabla sin tocarla.
 */
export const STATE_PRECEDENCE = ["loading", "error", "stale", "empty"] as const;

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
 * en orden: cambiar la tabla cambia la conducta.
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
 * El «no hay» del `empty`, dicho en PASADO y con su hora, para cuando el dato
 * además está viejo. [T-2.79.d]
 *
 * Vive aquí y no en cada panel a propósito: si cada componente escribiera su
 * propio deslinde, la decisión volvería a estar repartida en 27 sitios — que es
 * exactamente lo que esta ficha existe para cerrar. El tiempo verbal es el
 * contenido: «no había» es verificable (lo vimos), «no hay» no lo es.
 */
export function staleEmptyText(
  label: string,
  emptyText: string | undefined,
  staleSince: number,
): string {
  return (
    `${emptyText ?? `SIN DATOS · ${label}`} — así estaba a las ${utcClock(staleSince)} UTC; ` +
    "desde entonces no se ha podido confirmar."
  );
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
  // `?? null` y no `|| null`: un `staleSince` de 0 es una hora, no una ausencia.
  const cuando = staleSince ?? null;
  const state = resolveState({ loading, error, empty, stale: cuando !== null });

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
  const banda = cuando !== null && (
    <div className="soc-stateframe__stale" role="status">
      DATOS RETENIDOS · {utcClock(cuando)} UTC
    </div>
  );
  // [T-2.79.d] `stale` GANA, pero no se traga lo que el `empty` sabía: sin esto
  // el marco pintaría la franja de edad y debajo nada —la banda muda del banner
  // de privacidad—, porque cuando no hay dato los hijos tampoco pintan nada.
  // Se reusa el layout de `--status` (centrado, con su alto mínimo) para que la
  // franja, que es `position:absolute`, no se coma la línea de texto.
  if (state === "stale" && empty === true && cuando !== null) {
    return (
      <div className={cls("soc-stateframe soc-stateframe--status", className)} data-state="stale">
        {banda}
        <span>{staleEmptyText(label, emptyText, cuando)}</span>
      </div>
    );
  }
  return (
    <div className={cls("soc-stateframe", className)} data-state={state}>
      {banda}
      {children}
    </div>
  );
}
