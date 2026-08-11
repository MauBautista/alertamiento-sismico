// Registro + subida de evidencia forense (2.3). El backend firma un PUT
// presignado (regla de oro 6: el teléfono sube sin credenciales AWS) y guarda
// el SHA-256 declarado para verificarlo después. La foto NUNCA va a la galería
// del sistema: se lee de su archivo privado y se sube directo a S3.
//
// [T-2.108] Esto ya NO se llama desde la cámara: lo llama el motor de la cola
// offline (`offline/sync.ts`) cuando le toca el turno a un item `evidence`.
// Por eso ahora distingue fallo RECUPERABLE (sin red, 5xx → reintenta) de
// fallo de contrato (4xx → failed visible), y por eso comprueba la huella del
// archivo ANTES de registrar nada: entre la captura y la subida puede haber
// pasado un día entero en el bolsillo de alguien.
import { registerEvidenceIncidentsIncidentIdEvidencePost, type EvidenceRegisterIn } from "@takab/sdk";

import { readAndHash } from "@/features/forensic/fileHash";
import { isRetryableStatus } from "@/offline/httpOutcome";

export type EvidenceResult =
  | { ok: true; evidenceId: string }
  | { ok: false; retryable: boolean; reason: string };

export async function registerAndUploadEvidence(args: {
  incidentId: string;
  /** [T-2.113] Id del ITEM de la cola, estable entre reintentos: es lo que
   *  hace idempotente al registro. Omitirlo devuelve al comportamiento viejo
   *  (el servidor inventa uno por intento) y NO debe usarse desde la cola. */
  evidenceId?: string;
  uri: string;
  sha256: string;
  contentType?: string;
}): Promise<EvidenceResult> {
  const contentType = args.contentType ?? "image/jpeg";

  let bytes: Uint8Array;
  try {
    const read = await readAndHash(args.uri);
    if (read.sha256 !== args.sha256) {
      // §2.3: alterar un byte tras la captura invalida la evidencia. Se corta
      // AQUÍ, antes de crear la fila en el servidor: subir un blob que no
      // corresponde a su huella ensucia la cadena de custodia de un incidente.
      return {
        ok: false,
        retryable: false,
        reason: "El archivo cambió tras la captura: la huella SHA-256 no coincide.",
      };
    }
    bytes = read.bytes;
  } catch {
    // El archivo privado ya no está (limpieza del SO, desinstalación parcial):
    // reintentar no lo devuelve. Se declara y queda visible como fallido.
    return { ok: false, retryable: false, reason: "La foto ya no está en este teléfono." };
  }

  // [T-2.113] `evidence_id` es el id del ITEM de la cola, no uno nuevo por
  // intento: es lo que hace que el reintento resuelva a la MISMA fila en vez de
  // dejar una huérfana sin blob en S3.
  const registro: EvidenceRegisterIn = {
    sha256: args.sha256,
    content_type: contentType,
    evidence_id: args.evidenceId,
  };

  try {
    const reg = await registerEvidenceIncidentsIncidentIdEvidencePost({
      path: { incident_id: args.incidentId },
      body: registro,
    });
    if (!reg.data) {
      const status = reg.response?.status ?? 0;
      return {
        ok: false,
        retryable: isRetryableStatus(status),
        reason: `El servidor no registró la evidencia (HTTP ${status}).`,
      };
    }
    const { evidence_id, upload_url } = reg.data;
    if (!upload_url) {
      // Registrada pero sin bucket (dev sin S3): la huella ya quedó guardada.
      return { ok: true, evidenceId: String(evidence_id) };
    }
    const put = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": contentType },
      body: bytes as unknown as BodyInit,
    });
    if (!put.ok) {
      return {
        ok: false,
        retryable: isRetryableStatus(put.status),
        reason: `La subida falló (HTTP ${put.status}).`,
      };
    }
    return { ok: true, evidenceId: String(evidence_id) };
  } catch {
    // fetch murió: sin red (modo avión) — recuperable por definición.
    return { ok: false, retryable: true, reason: "Sin conexión: la evidencia no se subió." };
  }
}
