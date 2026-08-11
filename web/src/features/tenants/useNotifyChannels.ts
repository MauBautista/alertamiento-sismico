import { useQuery } from "@tanstack/react-query";

import { listNotifyChannelsNotifyChannelsGet } from "@takab/sdk";
import type { NotifyChannelOut } from "@takab/sdk";

/**
 * [T-2.75.a] ¿Qué canal de notificación entrega de verdad?
 *
 * Lo decide el REGISTRO de providers del servidor (`build_providers`), no la
 * consola: la respuesta se congela al arrancar la API, así que cambia con un
 * despliegue y no entre dos peticiones — de ahí el `staleTime` largo y la
 * ausencia de `refetchInterval`.
 *
 * `undefined` mientras carga o si falla: la tarjeta pinta `S/D`. Deliberadamente
 * NO se reintenta en bucle ni se degrada a "todos simulados": un canal sin dato
 * es un canal del que no se sabe nada, y decir «real» sin saberlo es el
 * tablero mentiroso que cerró T-2.75.
 */
export const NOTIFY_CHANNELS_STALE_MS = 600_000;

export interface NotifyChannelsData {
  channels: NotifyChannelOut[] | undefined;
  loading: boolean;
  error: string | null;
}

export function useNotifyChannels(): NotifyChannelsData {
  const query = useQuery({
    queryKey: ["notify", "channels"],
    queryFn: async (): Promise<NotifyChannelOut[]> => {
      const { data, response } = await listNotifyChannelsNotifyChannelsGet();
      if (data === undefined) {
        throw new Error(`GET /notify/channels falló (${response.status})`);
      }
      return data.channels;
    },
    staleTime: NOTIFY_CHANNELS_STALE_MS,
  });

  return {
    channels: query.data,
    loading: query.isPending,
    error: query.error ? query.error.message : null,
  };
}
