import { AlertTriangle, Check } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export interface ConfirmButtonProps {
  label: string;
  armedLabel?: string;
  /** Icono en reposo (nodo ya renderizado, p.ej. <CheckCircle2 size={13} />). */
  icon?: ReactNode;
  variant?: "primary" | "secondary";
  /** Gate de allowed_actions: deshabilitado ni arma ni dispara. */
  disabled?: boolean;
  timeoutSec?: number;
  onConfirm?: () => void;
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
  icon,
  variant = "primary",
  disabled = false,
  timeoutSec = 5,
  onConfirm,
}: ConfirmButtonProps) {
  const [state, setState] = useState<"idle" | "armed" | "done">("idle");
  const [remaining, setRemaining] = useState(timeoutSec);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resetRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  useEffect(() => clearTimers, []);

  function arm(): void {
    clearTimers();
    setState("armed");
    setRemaining(timeoutSec);
    tickRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearTimers();
          setState("idle");
          return timeoutSec;
        }
        return r - 1;
      });
    }, 1000);
  }

  function fire(): void {
    clearTimers();
    setState("done");
    onConfirm?.();
    resetRef.current = setTimeout(() => setState("idle"), 1500);
  }

  const cls =
    state === "armed"
      ? "soc-confirm soc-confirm--armed"
      : state === "done"
        ? "soc-confirm soc-confirm--done"
        : `soc-confirm soc-confirm--${variant}`;

  return (
    <button
      type="button"
      className={cls}
      disabled={disabled}
      aria-live="polite"
      onClick={() => {
        if (state === "idle") {
          arm();
        } else if (state === "armed") {
          fire();
        }
      }}
    >
      <span className="soc-confirm__row">
        {state === "armed" ? (
          <AlertTriangle size={13} aria-hidden />
        ) : state === "done" ? (
          <Check size={13} aria-hidden />
        ) : (
          icon
        )}
        <span>{state === "armed" ? armedLabel : state === "done" ? "EJECUTADO" : label}</span>
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
