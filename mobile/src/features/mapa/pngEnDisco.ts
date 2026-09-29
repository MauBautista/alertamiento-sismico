// [T-9.65] La superficie llega en base64 dentro del JSON; el SDK nativo del mapa
// la quiere como fichero (`file://`): no manda cabeceras por fuente, así que una
// URL de la API daría 401 sin el token.
//
// El nombre lleva el incidente Y una huella de la imagen. Con el incidente solo,
// una superficie RECALCULADA del mismo incidente (epicentro reubicado, otros
// umbrales del sitio) reescribía el mismo fichero con la misma `url`: el nativo
// sólo recarga cuando cambia la prop, así que seguía pintando la imagen vieja
// estirada sobre el bbox nuevo, bajo un rótulo que ya contaba otros sensores.
import { File, Paths } from "expo-file-system";

/** Huella corta (FNV-1a de 32 bits) del base64: basta para distinguir versiones. */
export function huella(texto: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

function bytesDeBase64(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/** La `uri` del PNG escrito en la caché, o `null` si no se pudo (y entonces no se pinta). */
export function pngEnDisco(incidentId: string, pngBase64: string): string | null {
  try {
    const f = new File(Paths.cache, `mapa-de-calor-${incidentId}-${huella(pngBase64)}.png`);
    if (f.exists) f.delete();
    f.create();
    f.write(bytesDeBase64(pngBase64));
    return f.uri;
  } catch {
    return null;
  }
}
