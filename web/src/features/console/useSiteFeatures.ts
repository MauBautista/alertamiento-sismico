// Features 1 s del sitio enfocado (T-1.27): backfill 10 min + rolling live.
//
// El strip NO es waveform crudo (regla de oro 9): son las features 1 s de la
// vista segura. Backfill REST (default 10 min, carga <1 s por diseño columnar)
// + frames `features:<site_id>` que se APPENDEAN a la ventana rodante de 600 s.

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { featuresTopic, siteFeaturesTelemetrySitesSiteIdFeaturesGet } from "@takab/sdk";
import type { FeatureRow, FeatureSeries, FeaturesFrame } from "@takab/sdk";

import { useLiveSocket } from "./socket";

export const FEATURES_WINDOW_S = 600;

/** Punto por segundo del strip (colapsado entre canales: pisos máximos). */
export interface FeaturePoint {
  /** Epoch ms alineado al segundo. */
  ts: number;
  pga: number | null;
  pgv: number | null;
  stalta: number | null;
  clipping: boolean;
}

function second(ts: string): number {
  return Math.floor(Date.parse(ts) / 1000) * 1000;
}

function maxOf(a: number | null, b: number | null | undefined): number | null {
  if (b === null || b === undefined) return a;
  return a === null ? b : Math.max(a, b);
}

/** Serie columnar REST → puntos por segundo (ya viene una fila por segundo). */
export function seriesToPoints(series: FeatureSeries): FeaturePoint[] {
  return series.ts.map((ts, i) => ({
    ts: second(ts),
    pga: series.pga[i] ?? null,
    pgv: series.pgv[i] ?? null,
    stalta: series.stalta[i] ?? null,
    clipping: series.clipping[i] ?? false,
  }));
}

/** Append de filas live: colapsa por segundo (máximos, clipping OR), ordena y
 *  recorta a la ventana rodante. Idempotente ante frames duplicados. */
export function appendRows(points: FeaturePoint[], rows: FeatureRow[]): FeaturePoint[] {
  if (rows.length === 0) return points;
  const bySecond = new Map(points.map((p) => [p.ts, { ...p }]));
  for (const row of rows) {
    const ts = second(row.ts);
    const prev = bySecond.get(ts) ?? { ts, pga: null, pgv: null, stalta: null, clipping: false };
    bySecond.set(ts, {
      ts,
      pga: maxOf(prev.pga, row.pga_g),
      pgv: maxOf(prev.pgv, row.pgv_cms),
      stalta: maxOf(prev.stalta, row.stalta),
      clipping: prev.clipping || row.clipping === true,
    });
  }
  const merged = [...bySecond.values()].sort((a, b) => a.ts - b.ts);
  const newest = merged[merged.length - 1].ts;
  return merged.filter((p) => newest - p.ts < FEATURES_WINDOW_S * 1000);
}

export interface SiteFeaturesData {
  points: FeaturePoint[];
  /** Última muestra (readouts PGA/PGV y clipping del detalle). */
  latest: FeaturePoint | null;
  /** ¿Los valores son `g`/`cm/s` de verdad? Sin snapshot todavía ⇒ `undefined`
   *  y `unitsFor` cae del lado seguro (T-1.33). */
  calibrated: boolean | undefined;
  loading: boolean;
  error: string | null;
  /** Epoch ms del último frame live del topic del sitio (staleness). */
  lastFrameAt: number | null;
  refetch: () => void;
}

export function useSiteFeatures(siteId: string | null): SiteFeaturesData {
  const socket = useLiveSocket();
  const query = useQuery({
    queryKey: ["siteFeatures", siteId],
    queryFn: async () => {
      const { data, response } = await siteFeaturesTelemetrySitesSiteIdFeaturesGet({
        path: { site_id: siteId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /telemetry/sites/${siteId}/features falló (${response.status})`);
      }
      return data;
    },
    enabled: siteId !== null,
  });

  const [liveRows, setLiveRows] = useState<FeatureRow[]>([]);

  // Cambio de sitio o backfill fresco: el buffer live arranca de cero.
  useEffect(() => {
    setLiveRows([]);
  }, [siteId, query.dataUpdatedAt]);

  useEffect(() => {
    if (!socket || siteId === null) return undefined;
    return socket.subscribe(featuresTopic(siteId), (frame) => {
      if (frame.type !== "features") return;
      setLiveRows((prev) => [...prev, ...(frame as FeaturesFrame).rows]);
    });
  }, [socket, siteId]);

  const points = useMemo(() => {
    const base = query.data ? seriesToPoints(query.data) : [];
    return appendRows(base, liveRows);
  }, [query.data, liveRows]);

  return {
    points,
    latest: points.length > 0 ? points[points.length - 1] : null,
    calibrated: query.data?.calibrated,
    loading: siteId !== null && query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    lastFrameAt: siteId !== null ? (socket?.lastFrameAt(featuresTopic(siteId)) ?? null) : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
