// [T-7.24] EL CAMINO DEL MAPA DE LA SACUDIDA, de la nube al operador.
//
// Sin este fichero la capa no existía. `MapPanel` estrenaba las props
// `shakemap`/`shakemapError`, `shakemap.ts` tenía sus builders probados y la
// leyenda estaba escrita… y el único montaje de producción no pasaba nada, así
// que `muestraSacudida` era SIEMPRE `false` en la consola real: ni botón de
// capa, ni leyenda, ni un solo rasgo en las fuentes. Una capa que nadie alimenta
// es una capa que no existe, por muchos tests que pasen alrededor.
//
// UNA CONSULTA POR INCIDENTE, y el panel NO calcula nada. El snapshot lo hace el
// worker; si lo recalculara la consola, dos operadores verían mapas distintos
// del mismo sismo según cuándo apretaran F5 (`shakemap/lectura.py`).
//
// ⚠️ **PROVISIONAL — se va con `make drift`.** El router
// `api/src/takab_api/routers/shakemap.py` es nuevo y `shared/sdk-ts/openapi.json`
// todavía no lo conoce, así que aquí no hay función generada que llamar y la
// petición se arma sobre el `client` del SDK. Es el MISMO cliente —baseUrl,
// Bearer y el 401 que cierra sesión salen de `configureApiClient`—, así que lo
// único a mano es la URL. En cuanto el integrador regenere el OpenAPI, esto se
// sustituye por `incidentShakemapIncidentsIncidentIdShakemapGet` y los tipos de
// `shakemap.ts` por los de `@takab/sdk`.

import { useQuery } from "@tanstack/react-query";

import { client } from "@takab/sdk";

import { ESTADO_PENDIENTE, type ShakemapOut } from "./shakemap";

/** La ruta, en un solo sitio: es lo que un `grep` tiene que poder encontrar. */
export const SHAKEMAP_URL = "/incidents/{incident_id}/shakemap";

export const SHAKEMAP_KEY = (id: string) => ["shakemap", id] as const;

/**
 * Cadencia de reintento MIENTRAS el snapshot está `pendiente`.
 *
 * `pendiente` es la única respuesta que se sabe transitoria: significa que el
 * worker aún no pasó por este incidente (200, no 404 — el endpoint lo declara).
 * Sin este sondeo el operador tendría que recargar la consola para enterarse de
 * que ya hay mapa, que es pedirle que adivine cuándo. En cualquier otro estado
 * NO se sondea: el mapa de un sismo que ya ocurrió no cambia mientras se mira, y
 * repreguntarlo sería pedirle a la nube que reconstruya la misma ventana una y
 * otra vez para devolver lo mismo (el argumento de `useEstaciones`).
 */
export const SHAKEMAP_PENDING_POLL_MS = 15_000;

export interface ShakemapData {
  /** El snapshot, o `null`. `null` NO significa «no hay mapa»: mira `loading`/`error`. */
  data: ShakemapOut | null;
  /** La consulta está en vuelo y todavía no hay snapshot. */
  loading: boolean;
  /** La consulta falló. Se declara en pantalla; no se disfraza de vacío. */
  error: boolean;
  /** Cuándo respondió la nube por última vez (frescura de LA CONSULTA). */
  updatedAt: number;
  refetch: () => void;
}

/**
 * El mapa de la sacudida del incidente enfocado. `null` = no hay incidente
 * enfocado, y entonces no se consulta nada (`enabled`).
 */
export function useShakemap(incidentId: string | null): ShakemapData {
  const q = useQuery({
    queryKey: SHAKEMAP_KEY(incidentId ?? ""),
    enabled: incidentId !== null,
    queryFn: async () => {
      const r = await client.get<ShakemapOut>({
        url: SHAKEMAP_URL,
        path: { incident_id: incidentId as string },
      });
      // Un fallo NO puede volver como `undefined` y leerse aguas abajo como «el
      // incidente no tiene mapa»: es la confusión que la regla de oro 7 prohíbe
      // en cada superficie de este repositorio.
      if (r.error !== undefined || r.data === undefined) {
        throw new Error(`GET ${SHAKEMAP_URL} falló (${r.response?.status ?? "sin respuesta"})`);
      }
      return r.data;
    },
    refetchInterval: (q) =>
      q.state.data?.estado === ESTADO_PENDIENTE ? SHAKEMAP_PENDING_POLL_MS : false,
  });
  return {
    data: q.data ?? null,
    loading: q.isLoading,
    error: q.isError,
    updatedAt: q.dataUpdatedAt,
    refetch: () => void q.refetch(),
  };
}
