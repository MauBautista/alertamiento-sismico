// Copia offline de los ARCHIVOS de rutas/manuales (1.6): el binario se
// descarga a documentos con el asset_id como nombre; "DISPONIBLE OFFLINE" es
// un hecho verificado (File.exists), no una promesa.
import type { SiteAssetOut } from "@takab/sdk";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

export type AssetRowKind = "textual" | "cached" | "downloadable" | "unavailable";

/** Decisión PURA del estado de la fila (testeable sin I/O). */
export function assetRowKind(args: { hasFile: boolean; cached: boolean; url: string | null }): AssetRowKind {
  if (!args.hasFile) {
    return "textual"; // p.ej. punto de reunión: solo texto, nada que descargar
  }
  if (args.cached) {
    return "cached";
  }
  return args.url !== null ? "downloadable" : "unavailable";
}

function localFile(asset: SiteAssetOut): File {
  return new File(Paths.document, `asset-${asset.asset_id}`);
}

export function isCached(asset: SiteAssetOut): boolean {
  try {
    return localFile(asset).exists;
  } catch {
    return false;
  }
}

/** Descarga el binario a la copia local. Lanza si no hay red/URL (la pantalla
 *  lo declara — jamás spinner infinito). */
export async function downloadAsset(asset: SiteAssetOut): Promise<void> {
  if (!asset.url) {
    throw new Error("asset sin URL de descarga");
  }
  const dest = localFile(asset);
  if (dest.exists) {
    dest.delete();
  }
  await File.downloadFileAsync(asset.url, dest);
}

/** Abre la copia local con el visor del sistema (share sheet). */
export async function openAsset(asset: SiteAssetOut): Promise<void> {
  await Sharing.shareAsync(localFile(asset).uri, {
    mimeType: asset.content_type ?? undefined,
  });
}
