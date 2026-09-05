// El catálogo de tipología, tal como lo sirve la nube (T-5.16 · D-28).
//
// NO hay copia del catálogo en `web/`. La hay del glosario de estados y de los
// design tokens, y en los dos casos por una razón física —el panel del gabinete
// es un HTML suelto en un Pi sin build—, que aquí no aplica: la consola habla
// con la API y la API lee el mismo `shared/schemas/tipologia_umbral.json`. Una
// cuarta copia sería una cuarta cosa que puede divergir, y el espejo de la
// matriz RBAC (`T-5.28`) ya enseñó cómo termina eso.

import { useQuery } from "@tanstack/react-query";

import { listBuildingTypesBuildingTypesGet } from "@takab/sdk";
import type { BuildingTypeCatalog } from "@takab/sdk";

/**
 * Cuánto puede tener la consola un catálogo en la mano antes de declararlo
 * viejo. El catálogo cambia con un DESPLIEGUE, no con un latido — pero cambia:
 * si alguien añade una tipología, una pestaña abierta desde ayer seguiría sin
 * ofrecerla, y quien la busca concluiría que no existe. Una hora es el mismo
 * `staleTime` con el que se pide.
 */
export const BUILDING_TYPES_STALE_MS = 60 * 60_000;

export interface BuildingTypesData {
  catalog: BuildingTypeCatalog | null;
  loading: boolean;
  readError: boolean;
  /** Epoch ms de la última respuesta buena; 0 = nunca hubo una. */
  dataUpdatedAt: number;
}

export function useBuildingTypes(): BuildingTypesData {
  const query = useQuery({
    queryKey: ["building-types"],
    // El catálogo es un contrato del despliegue, no un dato vivo: cambia con un
    // deploy, no con un latido. No tiene sentido re-pedirlo cada minuto.
    staleTime: BUILDING_TYPES_STALE_MS,
    queryFn: async (): Promise<BuildingTypeCatalog> => {
      const { data, response } = await listBuildingTypesBuildingTypesGet();
      if (data === undefined) {
        throw new Error(`GET /building-types falló (${response.status})`);
      }
      return data;
    },
  });
  return {
    catalog: query.data ?? null,
    loading: query.isPending,
    readError: query.error !== null,
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
