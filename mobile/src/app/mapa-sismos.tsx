// [T-9.63 · T-9.65 · D-46 · D-44] SISMOS → VER EN EL MAPA. Ruta de stack (como
// `contactos-emergencia.tsx`) que abren el ocupante y los tácticos desde su
// pestaña SISMOS.
//
// Sin `@takab/sdk` aquí: expo-router barre `src/app` y el SDK se queda en los
// hooks. Los cuatro estados son los de las DOS lecturas juntas: el mapa sin los
// sismos o sin el inmueble no es el mapa que se prometió.
import { MapaSismos } from "@/features/mapa/MapaSismos";
import { useMapaDeCalor } from "@/features/mapa/useMapaDeCalor";
import { useSismos } from "@/features/sismos/useSismos";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

const SIN_SITIO =
  "Sin sitio vigilado: no hay inmueble que poner en el mapa. Vincúlese a su edificio (Cuenta → Vincular).";

export default function MapaDeSismos() {
  const siteId = useWatchedSiteId();
  const sismos = useSismos(siteId);
  const mapa = useMapaDeCalor(siteId);

  const staleSinceMs =
    sismos.staleSinceMs === null
      ? mapa.staleSinceMs
      : mapa.staleSinceMs === null
        ? sismos.staleSinceMs
        : Math.min(sismos.staleSinceMs, mapa.staleSinceMs);

  return (
    <StateFrame
      empty={siteId === null}
      emptyText={SIN_SITIO}
      error={sismos.error ?? mapa.error}
      loading={sismos.loading || mapa.loading}
      onRetry={() => {
        sismos.refetch();
        mapa.refetch();
      }}
      staleSinceMs={staleSinceMs}
    >
      {sismos.data !== null && mapa.data !== null ? (
        <MapaSismos mapa={mapa.data} sismos={sismos.data} />
      ) : null}
    </StateFrame>
  );
}
