// [T-2.47] `prefers-reduced-motion` como INTERRUPTOR, no como sugerencia.
//
// En una consola de alertamiento el movimiento no es decoración: un frente que
// avanza y unas líneas que marchan atraen la vista al sitio correcto. Pero para
// quien tiene vestibular disorder o migraña vestibular ese mismo movimiento es un
// síntoma, y el sistema operativo YA lo declaró. Aquí se lee ese ajuste una vez y
// se reacciona a sus cambios en caliente (el operador puede activarlo a media
// guardia sin recargar la consola).
//
// Defensivo a propósito: jsdom no implementa `matchMedia` y un import transitivo
// no puede reventar una pantalla entera por un ajuste de accesibilidad. Sin
// `matchMedia` se asume `false` (movimiento permitido), que es la conducta que ya
// tenía la consola.

import { useEffect, useState } from "react";

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function query(): MediaQueryList | null {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  return window.matchMedia(REDUCED_MOTION_QUERY);
}

/** ¿El operador pidió menos movimiento? Reactivo al cambio del ajuste del SO. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => query()?.matches ?? false);

  useEffect(() => {
    const mql = query();
    if (mql === null) return undefined;
    setReduced(mql.matches);
    const onChange = (event: MediaQueryListEvent): void => setReduced(event.matches);
    // Safari < 14 solo tiene addListener; el fallback evita perder el cambio en
    // caliente (nunca un crash: el valor inicial ya está leído arriba).
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  return reduced;
}
