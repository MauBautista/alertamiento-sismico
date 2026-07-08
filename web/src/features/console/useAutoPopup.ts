// Pop-up automático por anomalía (T-1.27, criterio #4):
// STA/LTA > 3.5 SOSTENIDO 2 s (= 2 muestras 1 s consecutivas) ⇒ onOpen(siteId).
//
// Con latch: dispara UNA vez por episodio y se rearma cuando la señal baja
// del umbral — un temblor largo no debe re-abrir el panel en cada muestra.

import { useEffect, useRef } from "react";

import type { FeaturePoint } from "./useSiteFeatures";

export const STALTA_THRESHOLD = 3.5;
export const STALTA_CONSECUTIVE = 2;

/** true si las últimas N muestras superan TODAS el umbral (anomalía sostenida). */
export function staltaSustained(
  points: FeaturePoint[],
  threshold = STALTA_THRESHOLD,
  consecutive = STALTA_CONSECUTIVE,
): boolean {
  if (points.length < consecutive) return false;
  return points.slice(-consecutive).every((p) => p.stalta !== null && p.stalta > threshold);
}

export function useAutoPopup(
  siteId: string | null,
  points: FeaturePoint[],
  onOpen: (siteId: string) => void,
): void {
  const latchedRef = useRef(false);

  // Cambio de sitio: episodio nuevo, latch abajo.
  useEffect(() => {
    latchedRef.current = false;
  }, [siteId]);

  useEffect(() => {
    if (siteId === null) return;
    const last = points.length > 0 ? points[points.length - 1] : null;
    if (last !== null && (last.stalta === null || last.stalta <= STALTA_THRESHOLD)) {
      latchedRef.current = false; // la señal bajó: se rearma el episodio
      return;
    }
    if (!latchedRef.current && staltaSustained(points)) {
      latchedRef.current = true;
      onOpen(siteId);
    }
  }, [siteId, points, onOpen]);
}
