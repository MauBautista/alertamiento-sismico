// Certificado de reingreso (2.7) — derivación PURA de la copy desde el dictamen
// firmado. El sello sale del `signature_kind` (T-9.33 · D-43): «FIRMA DIGITAL ·
// INSPECTOR» solo si firmó el inspector (o la fila es anterior a la distinción);
// nada de siglas de hardware (§2.1-B). La magnitud, si el PDF la trae, se rotula "SSN · dato oficial
// posterior al evento" — jamás preliminar (§2.1-A); aquí no se muestra magnitud.
import type { MobileDictamenOut, MobileStateOut } from "@takab/sdk";

import { avisoDeReingreso } from "@/features/reentry/avisoReingreso";

import { bandaRotulada, firmanteDe, selloDeFirma } from "./confirmacion";
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
  /** Banda de la regla («VERDE»/«AMARILLO»/«ROJO»); null en una fila histórica. */
  band: string | null;
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
    // [F3·r3] Quién firmó, por su PAPEL: jamás el `signed_by` (UUID interno).
    signer: firmanteDe(d),
    signedAt: d.signed_at
      ? new Date(d.signed_at).toLocaleString("es-MX", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "—",
    seal: selloDeFirma(d),
    band: bandaRotulada(d.band),
    hasPdf: d.pdf_url != null,
  };
}

/**
 * [T-9.33 · D-49] El inmueble sigue BLOQUEADO aunque este dictamen no lo diga.
 *
 * El certificado es el veredicto de UN incidente; el reingreso es del EDIFICIO. Por
 * D-49, un NO HABITAR firmado de OTRO incidente del sitio manda sobre el habitable
 * de éste, y sin la calma ninguna firma autoriza. Medido en el Pixel el 2026-09-30:
 * el panel decía «NO HABITAR» y el certificado, en grande, «REINGRESO APROBADO».
 *
 * El teléfono NO decide el bloqueo: lee el MISMO aviso que pinta INICIO
 * (`avisoDeReingreso`, del estado que sirve el servidor), así que el certificado y
 * el panel no pueden volver a desmentirse. Sin aviso cuando el propio certificado
 * ya dice que no se habita y el bloqueo es suyo: sería repetirlo.
 */
export type BloqueoDelInmueble = {
  tono: "crit" | "warn";
  titulo: string;
  detalle: string;
  /** El bloqueo es de OTRO incidente del inmueble, no del de este dictamen. */
  deOtroEvento: boolean;
};

type MotivoDelServidor = NonNullable<MobileStateOut["reentry"]["reason"]>;

/**
 * El detalle del CERTIFICADO, y no el de INICIO. El de INICIO habla del inmueble
 * («aún no hay un dictamen técnico firmado») y, al lado de un certificado firmado,
 * se desmiente: una escalada al inspector sobre este mismo evento lo servía así.
 * `Record` exhaustivo: un motivo nuevo del servidor tumba el typecheck hasta tener
 * el suyo.
 */
const DETALLE_DEL_CERTIFICADO: Record<MotivoDelServidor, { propio: string; otro: string }> = {
  no_habitable: {
    propio: "El dictamen vigente de este evento indica NO HABITAR · INSPECCIÓN.",
    otro: "Lo bloquea un NO HABITAR firmado de OTRO evento del inmueble.",
  },
  pendiente_dictamen: {
    propio: "Se pidió la revisión del inspector: este dictamen queda en suspenso hasta su firma.",
    otro: "Falta el dictamen firmado de OTRO evento del inmueble.",
  },
  pendiente_confirmacion: {
    propio: "Este dictamen espera la confirmación de la brigada o del inspector.",
    otro: "El dictamen de OTRO evento del inmueble espera la confirmación de la brigada o del inspector.",
  },
};

function esMotivoConocido(r: unknown): r is MotivoDelServidor {
  return typeof r === "string" && Object.prototype.hasOwnProperty.call(DETALLE_DEL_CERTIFICADO, r);
}

export function bloqueoDelInmueble(
  d: Pick<MobileDictamenOut, "incident_id" | "habitable">,
  estado: Pick<MobileStateOut, "phase" | "reentry"> | null | undefined,
): BloqueoDelInmueble | null {
  if (estado == null) {
    return null;
  }
  const aviso = avisoDeReingreso(estado);
  if (aviso === null) {
    return null;
  }
  const motivo: unknown = estado.reentry?.reason ?? null;
  // «OTRO evento» sólo con un MOTIVO: sin él (p. ej. sin la calma, D-49 R1) el
  // `incident_id` que viaja es el que autorizaría, no el que bloquea.
  const conocido = esMotivoConocido(motivo);
  const deOtro =
    conocido && estado.reentry?.incident_id != null && estado.reentry.incident_id !== d.incident_id;
  if (!d.habitable && !deOtro) {
    return null;
  }
  return {
    tono: aviso.tono,
    titulo: aviso.titulo,
    detalle: conocido
      ? deOtro
        ? DETALLE_DEL_CERTIFICADO[motivo].otro
        : DETALLE_DEL_CERTIFICADO[motivo].propio
      : comoFrase(aviso.detalle),
    deOtroEvento: deOtro,
  };
}

/** El detalle de INICIO va tras un guion («REINGRESO BLOQUEADO — consulte…»); en el
 *  certificado es una frase suelta, y empieza en mayúscula. */
function comoFrase(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Desde cuándo el certificado muestra algo retenido: el MÁS VIEJO de sus dos datos.
 *  El dictamen puede estar fresco con el estado del inmueble congelado, y el aviso de
 *  bloqueo —o su ausencia— sale de ese estado. */
export function antiguedadDelCertificado(
  dictamenDesde: number | null,
  estadoDesde: number | null,
): number | null {
  if (dictamenDesde === null) {
    return estadoDesde;
  }
  if (estadoDesde === null) {
    return dictamenDesde;
  }
  return Math.min(dictamenDesde, estadoDesde);
}
