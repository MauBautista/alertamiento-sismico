// [T-9.52 · D-44] EL PNG DE LA SUPERFICIE ESTIMADA, con la sesión.
//
// `GET /incidents/{id}/shakemap/superficie.png` exige el Bearer —la nube lo sirve
// con la misma RLS que el JSON, sin URL prefirmada (`routers/shakemap.py`)—, así
// que MapLibre NO puede pedirlo por su cuenta: su `fetch` no lleva sesión. Se
// descarga aquí con el cliente del SDK (baseUrl, Bearer y el 401 que cierra
// sesión salen de `configureApiClient`) como `Blob`, y el mapa lo pinta desde un
// `objectURL`.
//
// EL CICLO DEL objectURL. Cada `createObjectURL` retiene el Blob hasta que se
// revoca, así que se revoca al cambiar de incidente, al llegar un snapshot
// nuevo y al desmontar. Y mientras llega el PNG nuevo NO se devuelve el viejo:
// una superficie del incidente anterior bajo la leyenda del actual diría otro
// sismo (regla de oro 7).

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { incidentShakemapSuperficiePngIncidentsIncidentIdShakemapSuperficiePngGet as pedirPng } from "@takab/sdk";

import type { PngSuperficie } from "./superficie";

/**
 * La hora del cálculo va en la clave: un snapshot recalculado es otro PNG, y la
 * caché no puede servir la imagen del cálculo anterior bajo la leyenda nueva.
 */
export const SUPERFICIE_PNG_KEY = (id: string, calculo: string) =>
  ["shakemap-superficie", id, calculo] as const;

/**
 * El PNG de la superficie del incidente enfocado.
 *
 * @param incidentId  el incidente, o `null` si no hay ninguno enfocado.
 * @param calculo     identifica el snapshot que TIENE superficie (su
 *                    `calculado_en`), o `null` si no hay superficie que pedir.
 *                    Sin superficie no se pide nada: la nube respondería 404, y
 *                    ese 404 no es un fallo sino el motivo que ya trae el JSON.
 */
export function useSuperficiePng(incidentId: string | null, calculo: string | null): PngSuperficie {
  const habilitado = incidentId !== null && calculo !== null;
  const q = useQuery({
    queryKey: SUPERFICIE_PNG_KEY(incidentId ?? "", calculo ?? ""),
    enabled: habilitado,
    // El PNG de un snapshot ya calculado no cambia mientras se mira (la nube lo
    // sirve con `max-age=60`); lo que lo cambia es un snapshot nuevo, y ése
    // trae otra clave.
    staleTime: 60_000,
    queryFn: async () => {
      const r = await pedirPng({ path: { incident_id: incidentId as string }, parseAs: "blob" });
      // Un fallo NO puede volver como `undefined` y leerse como «no hay
      // superficie»: la leyenda tiene que poder decir que la imagen no llegó.
      if (r.error !== undefined || !(r.data instanceof Blob)) {
        throw new Error(`GET superficie.png falló (${r.response?.status ?? "sin respuesta"})`);
      }
      return r.data;
    },
  });

  const blob = habilitado ? q.data : undefined;
  // El objectURL vive en un EFECTO y no en un `useMemo`: el doble montaje de
  // StrictMode revocaría en la limpieza la URL que el memo seguiría devolviendo.
  const [objeto, setObjeto] = useState<{ blob: Blob; url: string } | null>(null);
  useEffect(() => {
    if (blob === undefined) {
      setObjeto(null);
      return undefined;
    }
    const url = URL.createObjectURL(blob);
    setObjeto({ blob, url });
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  return {
    // Sólo la URL de ESTE blob: entre el cambio de incidente y el efecto que la
    // rehace hay un render, y en ese render la del anterior no se devuelve.
    url: objeto !== null && objeto.blob === blob ? objeto.url : null,
    cargando: habilitado && q.isLoading,
    error: habilitado && q.isError,
  };
}
