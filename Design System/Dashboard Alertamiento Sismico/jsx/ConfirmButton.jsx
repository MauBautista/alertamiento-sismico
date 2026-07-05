// jsx/ConfirmButton.jsx
// Two-step operator confirmation button.
//
// UX contract:
//   Click 1 → button enters AMBER "armed" state with a 5s cancellation
//             countdown. A subtitle reads "Haz clic de nuevo para
//             confirmar orden de operador".
//   Click 2 (within 5s) → confirm() fires, button briefly flashes the
//             success color, then resets.
//   No click (5s elapse) → reverts silently to idle.
//
// This pattern is non-negotiable for any operator action that touches
// real-world actuators or notifies stakeholders. Reduces inadvertent
// triggers on a videowall touched by multiple people.

const ConfirmButton = ({
  icon,
  label,
  armedLabel = 'CLIC NUEVAMENTE PARA CONFIRMAR',
  variant = 'primary',         // primary | secondary
  onConfirm,
  timeoutSec = 5,
}) => {
  // 'idle' | 'armed' | 'done'
  const [state, setState] = React.useState('idle');
  const [remaining, setRemaining] = React.useState(timeoutSec);
  const timerRef = React.useRef(null);

  const clearTimer = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  const arm = () => {
    setState('armed');
    setRemaining(timeoutSec);
    clearTimer();
    timerRef.current = setInterval(() => {
      setRemaining(r => {
        if (r <= 1) { clearTimer(); setState('idle'); return timeoutSec; }
        return r - 1;
      });
    }, 1000);
  };

  const fire = () => {
    clearTimer();
    setState('done');
    onConfirm?.();
    setTimeout(() => setState('idle'), 1500);
  };

  React.useEffect(() => () => clearTimer(), []);

  const handleClick = () => {
    if (state === 'idle')      arm();
    else if (state === 'armed') fire();
  };

  const cls = state === 'armed'
    ? 'soc-confirm soc-confirm--armed'
    : state === 'done'
      ? 'soc-confirm soc-confirm--done'
      : `soc-confirm soc-confirm--${variant}`;

  return (
    <button className={cls} onClick={handleClick} aria-live="polite">
      <span className="soc-confirm__row">
        {state === 'armed' ? (
          <i data-lucide="alert-triangle" width="13" height="13" />
        ) : state === 'done' ? (
          <i data-lucide="check" width="13" height="13" />
        ) : (
          icon && <i data-lucide={icon} width="13" height="13" />
        )}
        <span>{state === 'armed' ? armedLabel : state === 'done' ? 'EJECUTADO' : label}</span>
        {state === 'armed' && (
          <span className="soc-confirm__timer">{remaining}s</span>
        )}
      </span>
      {state === 'armed' && (
        <span className="soc-confirm__sub">
          Orden bajo verificación humana · {remaining}s para cancelar
        </span>
      )}
    </button>
  );
};

window.ConfirmButton = ConfirmButton;
