// Registro + subida de evidencia forense (2.3). El backend firma un PUT
// presignado (regla de oro 6: el teléfono sube sin credenciales AWS) y guarda
// el SHA-256 declarado para verificarlo después. La foto NUNCA va a la galería
// del sistema: se lee de su archivo privado y se sube directo a S3.
import { registerEvidenceIncidentsIncidentIdEvidencePost } from "@takab/sdk";
import { File } from "expo-file-system";

export type EvidenceResult =
  | { ok: true; evidenceId: string }
  | { ok: false; reason: string };

export async function registerAndUploadEvidence(args: {
  incidentId: string;
  uri: string;
  sha256: string;
  contentType?: string;
}): Promise<EvidenceResult> {
  const contentType = args.contentType ?? "image/jpeg";
  try {
    const reg = await registerEvidenceIncidentsIncidentIdEvidencePost({
      path: { incident_id: args.incidentId },
      body: { sha256: args.sha256, content_type: contentType },
    });
    if (!reg.data) {
      return { ok: false, reason: "El servidor no registró la evidencia." };
    }
    const { evidence_id, upload_url } = reg.data;
    if (!upload_url) {
      // Registrada pero sin bucket (dev sin S3): la huella ya quedó guardada.
      return { ok: true, evidenceId: String(evidence_id) };
    }
    const bytes = await new File(args.uri).bytes();
    const put = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": contentType },
      body: bytes as unknown as BodyInit,
    });
    if (!put.ok) {
      return { ok: false, reason: `La subida falló (HTTP ${put.status}).` };
    }
    return { ok: true, evidenceId: String(evidence_id) };
  } catch {
    return { ok: false, reason: "Sin conexión: la evidencia no se subió." };
  }
}
