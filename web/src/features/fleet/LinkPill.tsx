import type { ReactNode } from "react";

import { ageLabel } from "../../lib/time";

/**
 * [T-6.10 · U-23] CUÁNTO PUEDE TENER UN FRAME PARA QUE EL HALO SIGA DICIENDO
 * «esto está llegando ahora».
 *
 * Dos latidos perdidos del gabinete: el edge publica salud cada 60 s
 * (`health_heartbeat_s`, edge/takab_edge/config/settings.py). Tiene que ser más
 * ANCHO que esa cadencia —si no, el halo parpadearía con cualquier jitter de
 * red— y más ESTRECHO que el umbral con el que el servidor declara SIN ENLACE
 * (`sin_enlace_min = 5.0`, api/src/takab_api/settings.py); si fuera igual o
 * mayor, el veredicto ya habría cambiado `kind` a `crit` y esta comprobación no
 * apagaría nunca nada.
 *
 * Entre 2 y 5 minutos el servidor dice OPERATIVO y NO miente: el gabinete no
 * está declarado caído. Lo que no se puede decir en esa franja es que el dato
 * de la pantalla esté llegando en ese momento — y eso es justo lo que un halo
 * latiendo afirma.
 */
export const LINK_LIVE_MS = 120_000;

export interface LinkPillProps {
  /** ok = enlace vivo (valor crudo); crit = SIN ENLACE. El semáforo fino por
   * métrica NO existe aquí: los umbrales viven solo en el servidor. */
  kind: "ok" | "crit";
  label: string;
  value: string;
  icon: ReactNode;
  /**
   * Edad del último latido del gabinete en ms, o `null` si nunca latió.
   *
   * Es el dato que decide el LATIDO, y solo puede quitarlo: `kind` sigue
   * mandando sobre el color y sobre el veredicto. La frescura no opina sobre si
   * el gabinete está caído — opina sobre si lo que se ve acaba de llegar.
   */
  frameAgeMs: number | null;
}

/** Pill de enlace (MQTT / SeedLink) de la tarjeta de gabinete. */
export default function LinkPill({ kind, label, value, icon, frameAgeMs }: LinkPillProps) {
  const fresco = frameAgeMs !== null && frameAgeMs <= LINK_LIVE_MS;
  const late = kind === "ok" && fresco;
  // El halo que se apaga sin decir por qué se lee como un halo roto. La edad
  // solo aparece cuando hay algo que explicar: el camino sano no gana ruido.
  const declaraEdad = kind === "ok" && !fresco;

  return (
    <div className={`fleet-link fleet-link--${kind}`}>
      <span className="fleet-link__hd">
        {icon}
        <span>{label}</span>
        <span className={`soc-dot ${late ? "soc-dot--pulse" : ""}`} />
      </span>
      <span className="fleet-link__val">{value}</span>
      {declaraEdad && (
        <span className="fleet-link__age" data-testid="link-frame-age">
          ÚLTIMO FRAME · {frameAgeMs === null ? "S/D" : ageLabel(frameAgeMs / 1000)}
        </span>
      )}
    </div>
  );
}
