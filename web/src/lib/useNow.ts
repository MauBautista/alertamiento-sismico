import { useEffect, useState } from "react";

/**
 * Epoch ms de "ahora", re-renderizado cada ``intervalMs``. Alimenta los cálculos
 * de staleness de los paneles (StateFrame) sin que cada componente monte su timer.
 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
