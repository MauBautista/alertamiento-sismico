// [T-8.03 · D-38 · A-039] EL AVISO PREVIO AL TOPE DE LA SESIÓN.
//
// La API cierra la sesión de los roles de mesa a las 24 h del login (30 días
// para brigadista e inspector), cuente o no con un sismo en curso. Un operador
// cuyo turno cruza esa hora tendría que teclear contraseña y código justo
// entonces. Este aviso le da, con una hora de margen, la HORA EXACTA del corte y
// un botón para adelantarlo a un momento tranquilo.
//
// Lo que NO hace, a propósito:
//   · no ofrece prórroga — renovar ES volver a entrar (contraseña + código): una
//     prórroga sin segundo factor sería el agujero que D-38 cierra;
//   · no pinta nada sin dato — sin `session_expires_at` ni marca del login no se
//     sabe cuándo termina, y un aviso con una hora inventada es peor que ninguno
//     (regla de oro 7);
//   · no cierra la sesión al cumplirse — eso lo hace el cinturón del store, que
//     funciona aunque la barra no esté montada.
import { selectSessionDeadline, useSessionStore } from "../auth/session.store";
import Button from "../components/Button";
import { useNow } from "../lib/useNow";

/** Con cuánta anticipación se avisa. */
export const AVISO_PREVIO_MS = 60 * 60_000;

/** Cada cuánto se re-evalúa: el aviso aparece como mucho 15 s después de la marca. */
const TICK_MS = 15_000;

/** hh:mm en la hora de la sala: la misma que el reloj CST de la barra. */
function horaCst(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString("en-GB", {
    timeZone: "America/Mexico_City",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function SessionExpiryBanner() {
  const deadline = useSessionStore(selectSessionDeadline);
  const logout = useSessionStore((s) => s.logout);
  const now = useNow(TICK_MS);

  if (deadline === null) {
    return null;
  }
  const left = deadline - now;
  if (left <= 0 || left > AVISO_PREVIO_MS) {
    return null;
  }
  const hora = horaCst(deadline);
  return (
    <div
      className="soc-sesion-aviso"
      role="status"
      data-testid="session-expiry-banner"
      title={
        `A las ${hora} (hora de Ciudad de México) la consola le pedirá contraseña y código. ` +
        "RENOVAR AHORA cierra la sesión para que entre de nuevo cuando le convenga; " +
        "la sesión nueva cuenta desde ese login."
      }
    >
      <span className="soc-sesion-aviso__txt">SU SESIÓN TERMINA A LAS {hora} CST</span>
      <Button variant="secondary" className="soc-sesion-aviso__btn" onClick={() => void logout()}>
        RENOVAR AHORA
      </Button>
    </div>
  );
}
