// Features 1 s por canal SEED del sitio (T-1.34).
//
// El backend agrupa los 4 canales del RS4D en una sola respuesta; aquí solo se
// normaliza a epoch-ms. No hay live por WebSocket: el topic `features:<site>` emite
// filas colapsadas por segundo, así que el multicanal se refresca por poll. Es una
// vista de análisis, no un wall de alerta — el disparo vive en el edge.

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { siteFeaturesByChannelTelemetrySitesSiteIdFeaturesByChannelGet } from "@takab/sdk";

/** Refresco del strip multicanal. Más lento que el wall: aquí se analiza, no se vigila. */
export const CHANNELS_POLL_MS = 5_000;
/** Sin respuesta fresca tras esto, la traza es DATO RETENIDO (regla de oro 7). */
export const CHANNELS_STALE_MS = 30_000;

export interface ChannelTrace {
  channel: string;
  /** Epoch ms por muestra. */
  ts: number[];
  pga: (number | null)[];
  pgv: (number | null)[];
  clipping: boolean[];
}

export interface SiteChannelsData {
  channels: ChannelTrace[];
  calibrated: boolean | undefined;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useSiteChannels(siteId: string | null): SiteChannelsData {
  const query = useQuery({
    queryKey: ["siteChannels", siteId],
    queryFn: async () => {
      const { data, response } =
        await siteFeaturesByChannelTelemetrySitesSiteIdFeaturesByChannelGet({
          path: { site_id: siteId as string },
        });
      if (data === undefined) {
        throw new Error(
          `GET /telemetry/sites/${siteId}/features/by-channel falló (${response.status})`,
        );
      }
      return data;
    },
    enabled: siteId !== null,
    refetchInterval: CHANNELS_POLL_MS,
  });

  const channels = useMemo<ChannelTrace[]>(
    () =>
      (query.data?.channels ?? []).map((c) => ({
        channel: c.channel,
        ts: c.ts.map((t) => Date.parse(t)),
        pga: c.pga.map((v) => v ?? null),
        pgv: c.pgv.map((v) => v ?? null),
        clipping: c.clipping.map((v) => v === true),
      })),
    [query.data],
  );

  return {
    channels,
    calibrated: query.data?.calibrated,
    loading: siteId !== null && query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => {
      void query.refetch();
    },
  };
}
