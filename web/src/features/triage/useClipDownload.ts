// [T-8.08 · A-014] DESCARGAR CLIP, que no descargaba.
//
// `CctvPanel` pintaba el botón y llamaba a `onDownloadClip?.(clip_id)`, y
// `TriagePage` nunca le pasó el callback: el `?.` convertía el clic en nada, sin
// un error, delante del cliente. El endpoint existía desde T-3.12.c
// (`POST /cctv/clips/{clip_id}/download`: URL pre-firmada de 300 s y su fila en
// `audit_log`, porque el vídeo son personas) y ningún código web lo llamaba.
//
// La misma forma que `downloadEvidence` del miniSEED (`useIncidentDetail`): la
// pestaña se RESERVA dentro del gesto —la URL no existe hasta que el servidor
// firma, y abrirla entonces llega tarde al bloqueador de ventanas— y se navega
// cuando la URL llega; si falla, esa misma pestaña lo dice. Hook aparte y no un
// campo más del detalle: es CCTV, tiene su permiso propio (`cctv_video`) y su
// propio panel.
//
// [T-8.08 · verificador] Y EL FALLO LLEVA SU CLIP. La mutación vive en
// `TriagePage`, que cambia de incidente sin desmontarse: un fallo de un clip de
// A («EL CLIP YA NO ESTÁ…») se pintaba bajo los clips de B, afirmando de B lo
// que se midió de A, y un clip de A en vuelo deshabilitaba DESCARGAR CLIP en B.
// El hook no sabe qué incidente se mira —y no debe: sería un dato del servidor
// viajando fuera del marco del panel (`serverDataCensus`)—; dice QUÉ clip está
// en vuelo y QUÉ clip falló, y `CctvPanel` lo casa DENTRO de su marco contra los
// clips que pinta. La pestaña reservada en el clic de A se resuelve aunque luego
// se pida otro clip: el `onSuccess` es de la mutación, no de quien la mira.

import { useMutation } from "@tanstack/react-query";

import { downloadClipCctvClipsClipIdDownloadPost } from "@takab/sdk";

import { openPendingDownload, type PendingDownload } from "../../lib/download";

export interface ClipDownload {
  /** Reserva la pestaña (en el clic) y pide la URL firmada de ESE clip. */
  download: (clipId: string) => void;
  /** El clip cuya URL se está firmando; `null` = ninguno en vuelo. */
  pendingClipId: string | null;
  /**
   * El último fallo, CON el clip que lo tuvo: el panel sólo lo pinta si ese clip
   * es uno de los suyos. `null` = no falló nada.
   */
  failure: { clipId: string; message: string } | null;
}

/** El motivo, dicho para quien lo lee. 410 no es «no existe»: la retención lo podó. */
function motivo(status: number): string {
  if (status === 410) {
    return (
      "EL CLIP YA NO ESTÁ: la retención de vídeo lo podó. Su huella y sus horas " +
      "siguen en el reporte"
    );
  }
  return `POST /cctv/clips/{id}/download falló (${status})`;
}

export function useClipDownload(): ClipDownload {
  const mutation = useMutation({
    mutationFn: async (vars: { clipId: string; pending: PendingDownload }) => {
      try {
        const { data, response } = await downloadClipCctvClipsClipIdDownloadPost({
          path: { clip_id: vars.clipId },
        });
        if (data === undefined) {
          throw new Error(motivo(response.status));
        }
        return data;
      } catch (err) {
        vars.pending.fail(
          err instanceof Error && err.message ? err.message : "el servidor no devolvió el clip",
        );
        throw err;
      }
    },
    onSuccess: (data, vars) => vars.pending.resolve(data.url),
  });

  return {
    // `openPendingDownload()` corre AQUÍ, sincrónicamente dentro del onClick.
    download: (clipId) => mutation.mutate({ clipId, pending: openPendingDownload() }),
    pendingClipId: mutation.isPending ? (mutation.variables?.clipId ?? null) : null,
    failure:
      mutation.error && mutation.variables
        ? { clipId: mutation.variables.clipId, message: mutation.error.message }
        : null,
  };
}
