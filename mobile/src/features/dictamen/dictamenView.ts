// Certificado de reingreso (2.7) — derivación PURA de la copy desde el dictamen
// firmado. El sello es "FIRMA DIGITAL · INSPECTOR" (§2.1-B: nada de siglas de
// hardware). La magnitud, si el PDF la trae, se rotula "SSN · dato oficial
// posterior al evento" — jamás preliminar (§2.1-A); aquí no se muestra magnitud.
import type { MobileDictamenOut } from "@takab/sdk";

import { textoOcupante } from "./veredicto";

// [T-6.26] Los títulos ya no viven aquí: son los del glosario compartido
// (`shared/glossary/dictamen.json`), y el certificado y la línea de tiempo del
// ocupante tienen que decir lo MISMO del mismo veredicto.

export type CertificateView = {
  title: string;
  habitable: boolean;
  folio: string;
  signer: string;
  signedAt: string;
  seal: string;
  hasPdf: boolean;
};

export function certificateView(d: MobileDictamenOut): CertificateView | null {
  if (!d.signed || d.folio == null) {
    return null;
  }
  return {
    title: textoOcupante(d.status),
    habitable: d.habitable,
    // Folio corto legible (el UUID completo va en el PDF).
    folio: `${d.folio.slice(0, 8).toUpperCase()}`,
    signer: d.signed_by ? d.signed_by.slice(0, 8) : "—",
    signedAt: d.signed_at
      ? new Date(d.signed_at).toLocaleString("es-MX", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "—",
    seal: "FIRMA DIGITAL · INSPECTOR",
    hasPdf: d.pdf_url != null,
  };
}
