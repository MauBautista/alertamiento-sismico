// SHA-256 de un archivo por sus BYTES CRUDOS (§4.2). Debe coincidir con el
// hash server-side (hashlib.sha256(blob)) — por eso se hashean los bytes del
// archivo, no su base64 ni su ruta.
import * as Crypto from "expo-crypto";
import { File } from "expo-file-system";

function toHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256OfFile(uri: string): Promise<string> {
  const bytes = await new File(uri).bytes();
  const digest = await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, bytes);
  return toHex(digest);
}
