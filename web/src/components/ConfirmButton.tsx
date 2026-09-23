import { AlertTriangle, Check, Hourglass } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export interface ConfirmButtonProps {
  label: string;
  armedLabel?: string;
  /**
   * [A-163 · T-8.07] Qué se pinta cuando el servidor CONFIRMÓ (sólo con un
   * `onConfirm` que devuelve promesa). Por defecto «HECHO»; el acuse dice
   * «ACUSADO», que es lo que de verdad pasó.
   */
  doneLabel?: string;
  /** Icono en reposo (nodo ya renderizado, p.ej. <CheckCircle2 size={13} />). */
  icon?: ReactNode;
  variant?: "primary" | "secondary";
  /** Gate de allowed_actions: deshabilitado ni arma ni dispara. */
  disabled?: boolean;
  /**
   * [T-6.02] Por qué está apagado (o qué hace). Un `disabled` mudo obliga al
   * operador a adivinar en mitad de un turno; `screens.spec.ts` inventaría los
   * apagados sin explicación y aquí faltaba el hueco para dársela.
   */
  title?: string;
  /**
   * [T-8.07] Nombre accesible EN REPOSO, cuando el rótulo solo no dice sobre qué
   * actúa (un «BORRAR» por fila). Armado o en vuelo manda el texto visible: es lo
   * que hay que oír antes del segundo clic.
   */
  ariaLabel?: string;
  timeoutSec?: number;
  /**
   * [A-163 · T-8.07] Si devuelve una PROMESA (la de la petición), el botón la
   * espera: «ENVIANDO…» neutro y sin reenvío mientras vuela, el rótulo de éxito
   * sólo al resolverse y vuelta a reposo al rechazarse (el error lo pinta quien
   * llama: él sabe qué dijo el servidor). Sin promesa se conserva el flash de
   * siempre, que sólo afirma que la orden se DESPACHÓ.
   */
  onConfirm?: () => void | Promise<unknown>;
}

type Phase = "idle" | "armed" | "pending" | "done";

function isThenable(value: unknown): value is PromiseLike<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { then?: unknown }).then === "function"
  );
}

/**
 * Port TS de jsx/ConfirmButton.jsx: confirmación en dos pasos con countdown de
 * cancelación. No negociable para toda acción de operador que toque actuadores
 * reales o notifique a terceros (RBAC §4.3): clic 1 arma (ámbar, 5 s), clic 2
 * confirma, sin clic 2 se desarma en silencio.
 */
export default function ConfirmButton({
  label,
  armedLabel = "CLIC NUEVAMENTE PARA CONFIRMAR",
  doneLabel,
  icon,
  variant = "primary",
  disabled = false,
  title,
  ariaLabel,
  timeoutSec = 5,
  onConfirm,
}: ConfirmButtonProps) {
  const [state, setState] = useState<Phase>("idle");
  const [remaining, setRemaining] = useState(timeoutSec);
  // Qué afirma el flash: con promesa, lo que CONFIRMÓ el servidor; sin ella, el
  // rótulo de siempre (el botón no tiene cómo saber más).
  const [awaited, setAwaited] = useState(false);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resetRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // La fase VIGENTE sin esperar al render: dos clics en el mismo tic no pueden
  // disparar dos peticiones.
  const phaseRef = useRef<Phase>("idle");
  const mountedRef = useRef(true);

  function go(next: Phase): void {
    phaseRef.current = next;
    setState(next);
  }

  function clearTimers(): void {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (resetRef.current) {
      clearTimeout(resetRef.current);
      resetRef.current = null;
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimers();
    };
  }, []);

  function arm(): void {
    clearTimers();
    go("armed");
    setRemaining(timeoutSec);
    tickRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearTimers();
          go("idle");
          return timeoutSec;
        }
        return r - 1;
      });
    }, 1000);
  }

  function flashDone(): void {
    go("done");
    resetRef.current = setTimeout(() => go("idle"), 1500);
  }

  function fire(): void {
    clearTimers();
    const result = onConfirm?.();
    if (!isThenable(result)) {
      setAwaited(false);
      flashDone();
      return;
    }
    setAwaited(true);
    go("pending");
    Promise.resolve(result).then(
      () => {
        if (mountedRef.current) flashDone();
      },
      () => {
        // El rechazo lo DECLARA el llamador (su `error`); aquí sólo se deja de
        // afirmar nada y se devuelve el botón para reintentar.
        if (mountedRef.current) go("idle");
      },
    );
  }

  const cls =
    state === "armed"
      ? "soc-confirm soc-confirm--armed"
      : state === "done"
        ? "soc-confirm soc-confirm--done"
        : state === "pending"
          ? // Neutro a propósito: ni el ámbar de «armado» ni el verde del éxito.
            "soc-confirm soc-confirm--secondary"
          : `soc-confirm soc-confirm--${variant}`;

  const text =
    state === "armed"
      ? armedLabel
      : state === "pending"
        ? "ENVIANDO…"
        : state === "done"
          ? awaited
            ? (doneLabel ?? "HECHO")
            : "EJECUTADO"
          : label;

  return (
    <button
      type="button"
      className={cls}
      disabled={disabled || state === "pending"}
      aria-busy={state === "pending" ? true : undefined}
      aria-label={state === "idle" ? ariaLabel : undefined}
      title={title}
      aria-live="polite"
      onClick={() => {
        if (phaseRef.current === "idle") {
          arm();
        } else if (phaseRef.current === "armed") {
          fire();
        }
      }}
    >
      <span className="soc-confirm__row">
        {state === "armed" ? (
          <AlertTriangle size={13} aria-hidden />
        ) : state === "pending" ? (
          <Hourglass size={13} aria-hidden />
        ) : state === "done" ? (
          <Check size={13} aria-hidden />
        ) : (
          icon
        )}
        <span>{text}</span>
        {state === "armed" && <span className="soc-confirm__timer">{remaining}s</span>}
      </span>
      {state === "armed" && (
        <span className="soc-confirm__sub">
          Orden bajo verificación humana · {remaining}s para cancelar
        </span>
      )}
    </button>
  );
}
