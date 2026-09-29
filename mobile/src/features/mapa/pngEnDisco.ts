// [T-9.65] La superficie llega en base64 dentro del JSON; el SDK nativo del mapa
// la quiere como fichero (`file://`): no manda cabeceras por fuente, así que una
// URL de la API daría 401 sin el token. Un fichero por incidente en la caché:
// si cambia el incidente cambia la ruta, y el mapa no se queda con la imagen vieja.
import { File, Paths } from "expo-file-system";

function bytesDeBase64(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/** La `uri` del PNG escrito en la caché, o `null` si no se pudo (y entonces no se pinta). */
export function pngEnDisco(incidentId: string, pngBase64: string): string | null {
  try {
    const f = new File(Paths.cache, `mapa-de-calor-${incidentId}.png`);
    if (f.exists) f.delete();
    f.create();
    f.write(bytesDeBase64(pngBase64));
    return f.uri;
  } catch {
    return null;
  }
}
