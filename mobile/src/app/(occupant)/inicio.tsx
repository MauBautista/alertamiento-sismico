// 1.1 · Modo reposo del ocupante. El estado del edificio viene de
// mobile-state (verdad única de Flota); el directorio con copia offline.
// StateFrame garantiza los 4 estados obligatorios (regla de oro 7).
import {
  readDictamenIncidentsIncidentIdDictamenGet,
  siteDirectorySitesSiteIdDirectoryGet,
  type DirectoryEntryOut,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { firmaDelCartel, huellaDelReingreso } from "@/features/dictamen/confirmacion";
import { HomeView } from "@/features/home/HomeView";
import { useCachedQuery } from "@/offline/useCachedQuery";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

/** Cada cuánto se re-pide el certificado del cartel (el poll del reposo). */
const CERTIFICADO_POLL_MS = 30_000;

export default function Inicio() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data, loading, error, staleSinceMs, dataUpdatedAt, refetch } = useAlertState(siteId);

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

  // [F3·r3 · D-43] El cartel verde de reingreso dice QUIÉN lo aprobó (el
  // sistema, una confirmación con su rol o el inspector). `mobile-state` no lo
  // trae: sale del certificado, y SOLO si el perfil lo puede leer
  // (`dictamen_read`). Sin él (el ocupante) no se pide y el cartel no se lo
  // atribuye a nadie.
  // [F3·r4 · D-49] Se INVALIDA cuando mobile-state cambia: la clave lleva la
  // huella del dictamen vigente (incidente, status, firmado), así que un cambio
  // no reusa el certificado viejo; se re-pide con el poll del reposo por si otra
  // firma deja la misma huella; y uno que no coincide con mobile-state (el del
  // firmante ANTERIOR) no se le atribuye a nadie (`firmaDelCartel`).
  const puedeLeerDictamen = useSessionStore((s) => s.me?.allowed_actions?.dictamen_read === true);
  const incidenteAprobado =
    data?.phase === "reentry_approved"
      ? (data.reentry?.incident_id ?? data.incident?.incident_id ?? null)
      : null;
  const certificado = useQuery({
    queryKey: ["dictamen", incidenteAprobado, huellaDelReingreso(data)],
    enabled: puedeLeerDictamen && incidenteAprobado !== null,
    refetchInterval: CERTIFICADO_POLL_MS,
    queryFn: async () => {
      const res = await readDictamenIncidentsIncidentIdDictamenGet({
        path: { incident_id: incidenteAprobado as string },
      });
      if (!res.data) {
        throw new Error("dictamen no disponible");
      }
      return res.data;
    },
  });
  const firmaReingreso = puedeLeerDictamen
    ? firmaDelCartel(certificado.data, incidenteAprobado, data?.reentry)
    : null;

  const zoneId = data?.my_zone?.zone_id ?? null;
  const all = directory.data ?? [];
  const brigadistas = (zoneId ? all.filter((b) => b.zone_id === zoneId) : all).slice(0, 3);

  return (
    <StateFrame
      empty={siteId === null}
      emptyText="Sin sitio vigilado. Vincúlese a su edificio con el código de su administrador (Cuenta → Vincular)."
      error={data === null ? error : null}
      loading={loading}
      // [T-8.11] El error tiene salida: re-consulta el estado Y el directorio.
      onRetry={() => {
        refetch();
        directory.refetch();
      }}
      staleSinceMs={staleSinceMs}
    >
      {data !== null ? (
        <HomeView
          brigadistas={brigadistas}
          data={data}
          firmaReingreso={firmaReingreso}
          // Edad relativa al momento de la CONSULTA (se refresca con el poll);
          // render puro — sin Date.now() en el cuerpo (react-hooks/purity).
          nowMs={dataUpdatedAt}
          onOpenDirectorio={() => router.push("/(occupant)/directorio")}
          onOpenPanic={() => router.push("/panic")}
          onOpenRutas={() => router.push("/(occupant)/rutas")}
          staleSinceMs={staleSinceMs}
        />
      ) : null}
    </StateFrame>
  );
}
