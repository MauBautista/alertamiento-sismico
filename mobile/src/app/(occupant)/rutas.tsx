// 1.6 · Rutas de evacuación, punto de reunión y manual — lista de site_assets
// con copia offline: la LISTA se cachea (useCachedQuery) y los ARCHIVOS se
// descargan a documentos. En modo avión: lo cacheado abre; lo no cacheado se
// declara (jamás spinner infinito).
import { listSiteAssetsSitesSiteIdAssetsGet, type SiteAssetOut } from "@takab/sdk";
import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { assetRowKind, downloadAsset, isCached, openAsset } from "@/features/routes/assetsCache";
import { useCachedQuery } from "@/offline/useCachedQuery";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, radius, space } from "@/ui/theme";

const KIND_LABEL: Record<string, string> = {
  evac_route: "RUTA DE EVACUACIÓN",
  assembly_point: "PUNTO DE REUNIÓN",
  manual: "MANUAL",
};

function AssetRow(props: { asset: SiteAssetOut }) {
  const { asset } = props;
  const [cached, setCached] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.resolve(isCached(asset)).then((v) => {
      if (alive) {
        setCached(v);
      }
    });
    return () => {
      alive = false;
    };
  }, [asset]);

  const kind = assetRowKind({ hasFile: asset.url !== null || cached, cached, url: asset.url });

  const download = useCallback(() => {
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        await downloadAsset(asset);
        setCached(true);
      } catch {
        setError("Sin conexión: no se pudo descargar. Intente con red.");
      } finally {
        setBusy(false);
      }
    })();
  }, [asset]);

  return (
    <View style={styles.card} testID={`asset-${asset.asset_id}`}>
      <Text style={styles.kind}>{KIND_LABEL[asset.kind] ?? asset.kind.toUpperCase()}</Text>
      <Text style={styles.title}>{asset.title}</Text>
      {asset.description ? <Text style={styles.desc}>{asset.description}</Text> : null}

      {kind === "cached" ? (
        <View style={styles.rowActions}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>DISPONIBLE OFFLINE</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            onPress={() => void openAsset(asset).catch(() => setError("No se pudo abrir."))}
            style={styles.actionBtn}
          >
            <Text style={styles.actionText}>ABRIR</Text>
          </Pressable>
        </View>
      ) : null}
      {kind === "downloadable" ? (
        <Pressable
          accessibilityRole="button"
          disabled={busy}
          onPress={download}
          style={[styles.actionBtn, busy && styles.dim]}
        >
          <Text style={styles.actionText}>{busy ? "DESCARGANDO…" : "DESCARGAR PARA OFFLINE"}</Text>
        </Pressable>
      ) : null}
      {kind === "unavailable" ? (
        <Text style={styles.unavailable}>SIN COPIA OFFLINE · requiere conexión</Text>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

export default function Rutas() {
  const siteId = useWatchedSiteId();
  const assets = useCachedQuery<SiteAssetOut[]>({
    cacheKey: `assets:${siteId ?? "none"}`,
    queryKey: ["site-assets", siteId],
    enabled: siteId != null,
    queryFn: async () => {
      const res = await listSiteAssetsSitesSiteIdAssetsGet({
        path: { site_id: siteId as string },
      });
      if (!res.data) {
        throw new Error("assets no disponibles");
      }
      return res.data;
    },
  });

  return (
    <StateFrame
      empty={siteId === null || assets.data?.length === 0}
      emptyText={
        siteId === null
          ? "Sin sitio vigilado. Vincúlese a su edificio (Cuenta → Vincular)."
          : "Su edificio aún no publica rutas ni manuales."
      }
      error={assets.error}
      loading={assets.loading}
      staleSinceMs={assets.staleSinceMs}
    >
      <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
        <Text style={styles.eyebrow}>RUTAS Y DOCUMENTOS DEL INMUEBLE</Text>
        {(assets.data ?? []).map((a) => (
          <AssetRow asset={a} key={a.asset_id} />
        ))}
      </ScrollView>
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  kind: { color: palette.cyan, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.md, fontWeight: "700" },
  desc: { color: palette.fg2, fontSize: fontSize.sm },
  rowActions: { flexDirection: "row", alignItems: "center", gap: space[2] },
  badge: {
    borderColor: palette.ok,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space[2],
    paddingVertical: 2,
  },
  badgeText: { color: palette.ok, fontSize: fontSize.xs, letterSpacing: 1 },
  actionBtn: {
    backgroundColor: palette.raised,
    borderRadius: radius.md,
    paddingHorizontal: space[3],
    paddingVertical: space[2],
    alignSelf: "flex-start",
  },
  actionText: { color: palette.cyan, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  unavailable: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  error: { color: palette.crit, fontSize: fontSize.xs },
  dim: { opacity: 0.5 },
});
