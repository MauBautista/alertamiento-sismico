// [T-9.62 · T-9.66 · D-46] Pestaña SISMOS: los sismos de México publicados por USGS
// vistos desde el inmueble, y encima el historial sísmico del propio edificio.
// La comparten ocupante y táctico (`(brigadista)/sismos.tsx` reexporta ésta).
//
// Esto es POSTERIOR al sismo: sin cuenta regresiva y sin magnitud preliminar.
//
// Sin `@takab/sdk` en el cuerpo del módulo: expo-router barre `src/app` y el SDK
// se queda en los hooks (`features/sismos/useSismos.ts`).
import { HistorialCard } from "@/features/sismos/HistorialCard";
import { catalogoSinActualizar } from "@/features/sismos/frescura";
import { SismosList } from "@/features/sismos/SismosList";
import { useAhora, useHistorialSismico, useSismos } from "@/features/sismos/useSismos";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

const SIN_SITIO =
  "Sin sitio vigilado: no hay inmueble desde el que estimar. Vincúlese a su edificio (Cuenta → Vincular).";

/** El vacío honesto: el catálogo está al día y no trae ninguno. */
const SIN_SISMOS = "Sin sismos de M 4.0 o más en 90 días";

export default function Sismos() {
  const siteId = useWatchedSiteId();
  const sismos = useSismos(siteId);
  const historial = useHistorialSismico(siteId);
  const ahora = useAhora();

  const sinSitio = siteId === null;
  const data = sismos.data;
  // Sin filas sólo se afirma «no hubo» con el catálogo AL DÍA; si no, la lista
  // se pinta igual con su franja de catálogo sin actualizar.
  const vacioHonesto =
    data !== null && data.items.length === 0 && catalogoSinActualizar(data, ahora) === null;

  return (
    <StateFrame
      empty={sinSitio || vacioHonesto}
      emptyText={sinSitio ? SIN_SITIO : SIN_SISMOS}
      error={sismos.error}
      loading={sismos.loading}
      onRetry={sismos.refetch}
      staleSinceMs={sismos.staleSinceMs}
    >
      {data !== null ? (
        <SismosList
          cabecera={<HistorialCard lectura={historial} nowMs={ahora} />}
          nowMs={ahora}
          onRefrescar={() => void sismos.refrescar()}
          refrescando={sismos.refrescando}
          respuesta={data}
        />
      ) : null}
    </StateFrame>
  );
}
