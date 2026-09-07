// T-2.71 · El banner que declara que HAY ALARMAS MUDAS (al shell en T-6.01).
//
// Criterio 2 de la ficha: "la consola lo dice en pantalla mientras dure; nadie
// debe deducirlo". Desde T-6.01 lo dice en las SEIS rutas, no sólo en /console.
//
// Dos decisiones que separan este banner del del simulacro, y que no son gusto:
//
// 1. **NO se degrada bajo alerta real.** `DrillBanner` sí: con la alerta real
//    mandando pasa a badge, porque lo real gana visualmente y un simulacro que
//    no se ve solo es ruido perdido. Aquí es al revés — el momento en que más
//    falta hace saber que la alarma de un gabinete no va a sonar es justo el
//    sismo. Es el precedente literal del `banner-wr1` violeta del panel LAN
//    (T-1.69): "MODO PRUEBA WR-1 — LA NUBE NO RECIBE ALERTAS", visible SIEMPRE,
//    incluso bajo alerta real, porque el operador DEBE saber que algo se está
//    callando. Desde T-6.01 esa excepción está ESCRITA en la tabla
//    (`DEGRADES_UNDER_ALERT.maintenance === false`, `scene.ts`) y este
//    componente ya ni recibe la alerta: no tiene forma de degradarse.
//
// 2. **El fallo de lectura no puede vaciar el banner.** Decir "no hay ventana"
//    con las alarmas mudas es el peor fallo posible de esta pantalla: es el cero
//    tranquilizador de T-2.59 aplicado a la vigilancia. Con último dato conocido
//    se conserva y se rotula RETENIDO; sin ninguno, el fallo ES el estado.
//
// El MOTIVO va en pantalla a propósito. Una ventana sin dueño visible es una
// alarma apagada sin dueño, y el modo de fallo real de esta función no es
// técnico: alguien la abre "para que no moleste" y nadie vuelve a preguntar.
//
// [T-6.01] No posee el dato: lo recibe de `SceneStrip`. Ver `sceneCensus.test.ts`.

import { ShieldOff } from "lucide-react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { endClock, muteAckLine, muteHeadline, muteOutcome } from "../console/maintenance";
import type { MaintenanceData } from "../console/useMaintenanceWindows";

export default function MaintenanceBanner({ data }: { data: MaintenanceData }) {
  const canClose = useSessionStore((s) => s.me?.allowed_actions.maintenance_window === true);
  const { items, loading, readError, updatedAt, refetch, close, pending, error } = data;

  // "Conocido" = el servidor ya nos dijo algo alguna vez. Con eso el fallo
  // degrada a RETENIDO; sin eso, el fallo ES el estado.
  const known = items.length > 0;
  const frameError = readError !== null && !known ? readError : null;
  const staleSince = readError !== null && known ? updatedAt : null;

  return (
    <StateFrame
      label="VENTANAS DE MANTENIMIENTO"
      className="soc-drill__frame"
      loading={loading}
      error={frameError}
      onRetry={refetch}
      empty={!known}
      emptyText="SIN VENTANA DE MANTENIMIENTO"
      silentEmpty
      staleSince={staleSince}
    >
      <div className="soc-maint-list" data-testid="maintenance-banner">
        {/* El fallo de la MUTACIÓN (cerrar). Va anclado por test desde el lote
            C: REABRIR VIGILANCIA es la única vía con re-disparo documentado, y
            un fallo tragado deja al operador creyendo que devolvió la
            vigilancia mientras el edificio sigue mudo hasta que expire sola. */}
        {error !== null && (
          <span className="soc-user__error" role="alert">
            {error.toUpperCase()}
          </span>
        )}
        {items.map((w) => (
          <div
            key={w.window_id}
            className="soc-drill soc-maint"
            role="status"
            // Lo que de VERDAD quedó mudo, en el DOM: el titular es texto y el
            // texto cambia; esto es el gancho estable para medirlo.
            data-mute={muteOutcome(w)}
          >
            <ShieldOff size={16} aria-hidden />
            <span>
              🟣 VENTANA DE MANTENIMIENTO — {muteHeadline(w)} ·{" "}
              {w.scope === "platform" ? "PLATAFORMA" : (w.site_name ?? w.gateway_serial ?? "—")} ·{" "}
              {muteAckLine(w)} · TERMINA {endClock(w)} UTC · MOTIVO: {w.reason}
            </span>
            {canClose && (
              <button
                type="button"
                className="soc-btn soc-btn--secondary"
                disabled={pending}
                onClick={() => close(w.window_id)}
                title="Reabre la vigilancia AHORA: si alguna alarma quedó disparada, su correo sale"
              >
                REABRIR VIGILANCIA
              </button>
            )}
          </div>
        ))}
      </div>
    </StateFrame>
  );
}
