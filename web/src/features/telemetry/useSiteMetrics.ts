// Historial de máximos por bucket (T-1.34), sobre los continuous aggregates.
//
// El preset elige el cagg: hasta 24 h se lee `1m` (1.440 puntos como mucho); a 7 días
// se conmuta a `1h` (168 puntos). Pedir 7 días en buckets de 1 minuto serían 10.080
// puntos para 600 px de ancho — payload y DOM tirados a la basura.

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { siteMetricsTelemetrySitesSiteIdMetricsGet } from "@takab/sdk";

export type HistoryPreset = "1h" | "6h" | "24h" | "7d";

export const HISTORY_PRESETS: readonly HistoryPreset[] = ["1h", "6h", "24h", "7d"] as const;

const SPAN_MS: Record<HistoryPreset, number> = {
  "1h": 3_600_000,
  "6h": 6 * 3_600_000,
  "24h": 24 * 3_600_000,
  "7d": 7 * 24 * 3_600_000,
};

/** El bucket es función del preset, no del gusto del usuario. */
export function bucketFor(preset: HistoryPreset): "1m" | "1h" {
  return preset === "7d" ? "1h" : "1m";
}

export interface HistoryPoint {
  ts: number;
  maxPga: number | null;
  maxPgv: number | null;
}

export interface SiteMetricsData {
  points: HistoryPoint[];
  bucket: string;
  calibrated: boolean | undefined;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSiteMetrics(siteId: string | null, preset: HistoryPreset): SiteMetricsData {
  const query = useQuery({
    queryKey: ["siteMetrics", siteId, preset],
    queryFn: async () => {
      const now = Date.now();
      const { data, response } = await siteMetricsTelemetrySitesSiteIdMetricsGet({
        path: { site_id: siteId as string },
        query: {
          bucket: bucketFor(preset),
          from: new Date(now - SPAN_MS[preset]).toISOString(),
          to: new Date(now).toISOString(),
        },
      });
      if (data === undefined) {
        throw new Error(`GET /telemetry/sites/${siteId}/metrics falló (${response.status})`);
      }
      return data;
    },
    enabled: siteId !== null,
  });

  const points = useMemo<HistoryPoint[]>(
    () =>
      (query.data?.ts ?? []).map((ts, i) => ({
        ts: Date.parse(ts),
        maxPga: query.data?.max_pga_g[i] ?? null,
        maxPgv: query.data?.max_pgv_cms[i] ?? null,
      })),
    [query.data],
  );

  return {
    points,
    bucket: query.data?.bucket ?? bucketFor(preset),
    calibrated: query.data?.calibrated,
    loading: siteId !== null && query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
