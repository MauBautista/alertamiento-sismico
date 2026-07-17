// Captura forense con marca de agua HORNEADA en el pixel (2.3). El flujo:
// (1) CameraView toma la foto → (2) se compone en un View con la marca de agua
// (watermarkLines) → (3) react-native-view-shot captura ESE View a un archivo
// JPEG NUEVO (la marca queda en el bitmap, no es overlay ni EXIF) → (4) se
// mueve a un dir PRIVADO de la app (jamás a la galería) → (5) SHA-256 del
// archivo final. Este módulo es la costura nativa; la lógica pura vive en
// watermark.ts / fileHash.ts (testeadas). GATE-HW: verificación en dispositivo.
import { Directory, File, Paths } from "expo-file-system";
import { captureRef } from "react-native-view-shot";

import { sha256OfFile } from "./fileHash";
import type { ForensicMeta } from "./watermark";

export type CapturedEvidence = {
  /** URI del archivo privado con la marca horneada. */
  uri: string;
  /** SHA-256 de los bytes finales (coincide con el hash server-side). */
  sha256: string;
  meta: ForensicMeta;
};

const EVIDENCE_DIR = "forensic";

function evidenceDir(): Directory {
  const dir = new Directory(Paths.document, EVIDENCE_DIR);
  if (!dir.exists) {
    dir.create();
  }
  return dir;
}

/** Compone la marca sobre la foto y persiste el resultado en privado + hash.
 *  `composedRef` es el View (foto + watermarkLines) listo para capturar. */
export async function captureForensicPhoto(
  composedRef: Parameters<typeof captureRef>[0],
  meta: ForensicMeta,
  id: string,
): Promise<CapturedEvidence> {
  const shotUri = await captureRef(composedRef, { format: "jpg", quality: 0.9 });
  // Mover a un archivo PRIVADO estable (fuera de cache, jamás en galería).
  const dest = new File(evidenceDir(), `evidence-${id}.jpg`);
  if (dest.exists) {
    dest.delete();
  }
  new File(shotUri).move(dest);
  const sha256 = await sha256OfFile(dest.uri);
  return { uri: dest.uri, sha256, meta };
}
