// Utilería MapLibre compartida (T-1.50): MapPanel (consola) y MapPointPicker
// (flota) la usan para no repetir el manejo de resize.

/** Superficie mínima del mapa que necesita el observer (fácil de mockear). */
export interface ResizableMap {
  resize(): void;
}

/**
 * Re-dimensiona el mapa cuando su contenedor cambia de tamaño. MapLibre mide
 * el contenedor SOLO al construirse: si el layout se asienta después (grid que
 * se estabiliza, form que aparece por swap), el canvas queda mal medido o en
 * 0×0. Throttle por rAF: ResizeObserver puede disparar en ráfaga.
 *
 * Devuelve la función de limpieza. En entornos sin ResizeObserver (jsdom sin
 * stub) es un no-op inofensivo.
 */
export function observeMapResize(map: ResizableMap, container: HTMLElement): () => void {
  if (typeof ResizeObserver === "undefined") {
    return () => undefined;
  }
  let raf = 0;
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => map.resize());
  });
  observer.observe(container);
  return () => {
    cancelAnimationFrame(raf);
    observer.disconnect();
  };
}
