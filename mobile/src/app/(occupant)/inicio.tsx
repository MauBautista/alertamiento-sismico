// 1.1 · Modo reposo del ocupante. El estado del edificio viene de
// mobile-state (verdad única de Flota); el directorio con copia offline.
// StateFrame garantiza los 4 estados obligatorios (regla de oro 7).
import { siteDirectorySitesSiteIdDirectoryGet, type DirectoryEntryOut } from "@takab/sdk";
import { useRouter } from "expo-router";

import { useAlertState } from "@/features/alert/useAlertState";
import { HomeView } from "@/features/home/HomeView";
import { useCachedQuery } from "@/offline/useCachedQuery";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Inicio() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data, loading, error, stale, dataUpdatedAt } = useAlertState(siteId);

  const directory = useCachedQuery<DirectoryEntryOut[]>({
    cacheKey: `directory:${siteId ?? "none"}`,
    queryKey: ["directory", siteId],
    enabled: siteId != null,
    queryFn: async () => {
      const res = await siteDirectorySitesSiteIdDirectoryGet({
        path: { site_id: siteId as string },
      });
      if (!res.data) {
        throw new Error("directorio no disponible");
      }
      return res.data;
    },
  });

  const zoneId = data?.my_zone?.zone_id ?? null;
  const all = directory.data ?? [];
  const brigadistas = (zoneId ? all.filter((b) => b.zone_id === zoneId) : all).slice(0, 3);

  return (
    <StateFrame
      empty={siteId === null}
      emptyText="Sin sitio vigilado. Vincúlese a su edificio con el código de su administrador (Cuenta → Vincular)."
      error={data === null ? error : null}
      loading={loading}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      {data !== null ? (
        <HomeView
          brigadistas={brigadistas}
          data={data}
          // Edad relativa al momento de la CONSULTA (se refresca con el poll);
          // render puro — sin Date.now() en el cuerpo (react-hooks/purity).
          nowMs={dataUpdatedAt}
          onOpenDirectorio={() => router.push("/(occupant)/directorio")}
          onOpenRutas={() => router.push("/(occupant)/rutas")}
        />
      ) : null}
    </StateFrame>
  );
}
