// Captura forense con marca de agua HORNEADA en el pixel (2.3). El flujo:
// (1) CameraView toma la foto → (2) se compone en un View con la marca de agua
// (watermarkLines) → (3) react-native-view-shot captura ESE View a un archivo
// JPEG NUEVO (la marca queda en el bitmap, no es overlay ni EXIF) → (4) se
// mueve a un dir PRIVADO de la app (jamás a la galería) → (5) SHA-256 del
// archivo final. Este módulo es la costura nativa; la lógica pura vive en
// watermark.ts / fileHash.ts (testeadas). GATE-HW: verificación en dispositivo.
import { Directory, File, Paths } from "expo-file-system";
import { captureRef } from "react-native-view-shot";

import { readAndHash } from "./fileHash";
import type { ForensicMeta } from "./watermark";

export type CapturedEvidence = {
  /** URI del archivo privado con la marca horneada. */
  uri: string;
  /** SHA-256 de los bytes finales (coincide con el hash server-side). */
  sha256: string;
  /** Tamaño en bytes: la cola offline lo suma en "tamaño pendiente" (§7·2.5). */
  bytes: number;
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
  // ⚠️⚠️ [T-7.58] LAS DOS COSAS DE ESTA LÍNEA, Y LAS DOS SE MIDIERON.
  //
  // 1· **`move()` DEVUELVE UNA PROMESA Y HAY QUE ESPERARLA.** Ésta es la causa
  //    del defecto, y engaña porque su hermana no: en
  //    `expo-file-system@57.0.1`, `FileSystemFile` declara
  //    `move(destination, options?): Promise<void>` y, aparte,
  //    `moveSync(destination, options?): void`. Las vecinas de este módulo
  //    —`delete()`, `create()`, `write()`— sí son síncronas, así que la línea
  //    sin `await` no desentonaba. Y `tsc` no la caza: una promesa suelta no es
  //    un error de tipos. El resultado era una CARRERA entre el movimiento
  //    nativo y la lectura de la línea siguiente, que se resolvía a cara o cruz:
  //    el flujo `02` fallaba ~1 de cada 2 corridas. Medido en el Pixel el
  //    2026-09-19; el teléfono imprimía `FileNotFoundException … ENOENT` con la
  //    ruta de la CACHÉ, o sea el fichero leído antes de que se moviera.
  //
  // 2· **Se lee del objeto ORIGEN, no del destino.** Lo dice la API: «Updates
  //    the `uri` property that now points to the new location» — `move()` muta
  //    el ORIGEN; el objeto que se pasa como destino NO se actualiza. El código
  //    anterior descartaba el origen (`new File(shotUri).move(dest)`) y leía
  //    `dest.uri`, una ruta construida a mano en la que se CONFIABA.
  const origen = new File(shotUri);
  await origen.move(dest);

  // Y la POSTCONDICIÓN, porque un `ENOENT` tres líneas más abajo no dice en qué
  // paso se perdió el fichero. Esta evidencia va a `evidence_objects`, que no
  // admite reescritura: lo que no se capturó no se recupera luego.
  if (!origen.exists) {
    throw new Error(
      `la foto sellada no quedó en el disco tras moverla (${origen.uri}). No se ha guardado nada.`,
    );
  }

  const { bytes, sha256 } = await readAndHash(origen.uri);
  return { uri: origen.uri, sha256, bytes: bytes.length, meta };
}
