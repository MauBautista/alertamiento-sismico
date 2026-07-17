// 1.7 · Directorio del inmueble — roster público (brigadistas/seguridad/
// administración) con copia offline y llamada de un toque.
import { siteDirectorySitesSiteIdDirectoryGet, type DirectoryEntryOut } from "@takab/sdk";
import { ScrollView, StyleSheet, Text } from "react-native";

import { DirectoryList } from "@/features/directory/DirectoryList";
import { useCachedQuery } from "@/offline/useCachedQuery";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, space } from "@/ui/theme";

export default function Directorio() {
  const siteId = useWatchedSiteId();
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

  return (
    <StateFrame
      empty={siteId === null || directory.data?.length === 0}
      emptyText={
        siteId === null
          ? "Sin sitio vigilado. Vincúlese a su edificio (Cuenta → Vincular)."
          : "Su edificio aún no publica contactos de emergencia."
      }
      error={directory.error}
      loading={directory.loading}
      staleSinceMs={directory.staleSinceMs}
    >
      <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
        <Text style={styles.eyebrow}>CONTACTOS DE EMERGENCIA DEL INMUEBLE</Text>
        <DirectoryList entries={directory.data ?? []} />
      </ScrollView>
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
});
