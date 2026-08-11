// SHA-256 de un archivo por sus BYTES CRUDOS (§4.2). Debe coincidir con el
// hash server-side (hashlib.sha256(blob)) — por eso se hashean los bytes del
// archivo, no su base64 ni su ruta.
import * as Crypto from "expo-crypto";
import { File } from "expo-file-system";

/** Los bytes tal y como los entrega `File.bytes()` (buffer no compartido). */
export type FileBytes = Awaited<ReturnType<InstanceType<typeof File>["bytes"]>>;

function toHex(buf: ArrayBuffer | Uint8Array): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256OfBytes(bytes: FileBytes): Promise<string> {
  return toHex(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, bytes));
}

export async function sha256OfFile(uri: string): Promise<string> {
  return sha256OfBytes(await new File(uri).bytes());
}

/** Lee el archivo UNA vez y devuelve bytes + huella. Lo usan la captura (para
 *  sellar) y la subida (para comprobar, antes de tocar el servidor, que nadie
 *  alteró el archivo mientras esperaba en la cola). */
export async function readAndHash(uri: string): Promise<{ bytes: FileBytes; sha256: string }> {
  const bytes = await new File(uri).bytes();
  return { bytes, sha256: await sha256OfBytes(bytes) };
}
