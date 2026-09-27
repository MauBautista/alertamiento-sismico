// [T-9.04] El aviso de reingreso BLOQUEADO que pinta INICIO — derivación PURA.
//
// Desde `D-33` firmar el dictamen cierra el incidente en tres segundos, así que
// el veredicto ya no puede leerse del incidente abierto: el servidor lo arrastra
// en `phase = reentry_blocked` y en `reentry.reason`. El teléfono NO decide el
// bloqueo; sólo traduce el motivo que le sirven a lo que lee el ocupante.
//
// Se lee del MOTIVO y no sólo de la fase porque el bloqueo es un hecho del
// EDIFICIO: si la alarma del inmueble gana la precedencia de fase (suena
// ahora), el NO HABITAR sigue siendo verdad y el servidor lo sigue mandando en
// `reentry`. Con `reentry_approved` no hay aviso de bloqueo: ese lo pinta el
// cartel verde de siempre.
//
// ⚠️ Ningún aviso de bloqueo convive con «SEGURO» en la tarjeta de estado
// (`estadoDelInmueble`). La primera versión sólo lo negaba con un NO HABITAR:
// con un pendiente —que el servidor sirve hasta 30 días— o con un motivo que la
// app no reconoce, INICIO decía «SEGURO» en verde y en grande bajo la franja de
// «reingreso bloqueado». Son dos verdades que se desmienten, y la persona lee la
// grande. El servidor dice `reentry.blocked = true`: la app no lo contradice.
import type { MobileStateOut } from "@takab/sdk";

import type { HealthBanner } from "@/features/home/health";

/**
 * Los motivos que publica el servidor, DERIVADOS del contrato y no copiados a
 * mano: `AVISOS` es un `Record` exhaustivo sobre este tipo, así que un motivo
 * nuevo en `MobileReentryOut.reason` tumba el typecheck hasta que tenga su aviso.
 */
type MotivoDelServidor = NonNullable<MobileStateOut["reentry"]["reason"]>;

export type MotivoBloqueo =
  | MotivoDelServidor
  /** El servidor dice que está bloqueado y esta versión no reconoce por qué. */
  | "desconocido";

export type AvisoReingreso = {
  motivo: MotivoBloqueo;
  /** `crit` ⇒ cartel rojo de relleno sólido; `warn` ⇒ franja ámbar informativa. */
  tono: "crit" | "warn";
  titulo: string;
  detalle: string;
  /**
   * El rótulo que toma la tarjeta de estado mientras dure el aviso: con
   * cualquiera de ellos la tarjeta NO puede afirmar «SEGURO». Cada uno dice
   * sólo lo que sabe: un pendiente no es un NO HABITAR, y un motivo que la app
   * no reconoce no le autoriza a inventarse un dictamen.
   */
  rotulo: string;
};

const AVISOS: Record<MotivoDelServidor, AvisoReingreso> = {
  no_habitable: {
    motivo: "no_habitable",
    tono: "crit",
    titulo: "REINGRESO NO AUTORIZADO",
    detalle: "el dictamen indica NO HABITAR · INSPECCIÓN",
    rotulo: "NO HABITABLE",
  },
  pendiente_dictamen: {
    motivo: "pendiente_dictamen",
    tono: "warn",
    titulo: "REINGRESO PENDIENTE DE DICTAMEN",
    detalle: "aún no hay un dictamen técnico firmado del inmueble.",
    rotulo: "REINGRESO PENDIENTE",
  },
  pendiente_confirmacion: {
    motivo: "pendiente_confirmacion",
    tono: "warn",
    titulo: "REINGRESO PENDIENTE DE CONFIRMACIÓN",
    detalle: "el dictamen espera la confirmación de la brigada o del inspector.",
    rotulo: "REINGRESO PENDIENTE",
  },
};

/** Servidor más nuevo que la app: bloqueado por un motivo que no conocemos. Se
 *  dice que está bloqueado —callarlo sería lo peor— sin inventar un dictamen. */
const DESCONOCIDO: AvisoReingreso = {
  motivo: "desconocido",
  tono: "warn",
  titulo: "REINGRESO BLOQUEADO",
  detalle: "consulte a su brigada antes de volver a entrar al inmueble.",
  rotulo: "REINGRESO BLOQUEADO",
};

function esMotivoConocido(r: unknown): r is keyof typeof AVISOS {
  return typeof r === "string" && Object.prototype.hasOwnProperty.call(AVISOS, r);
}

export function avisoDeReingreso(
  data: Pick<MobileStateOut, "phase" | "reentry">,
): AvisoReingreso | null {
  if (data.phase === "reentry_approved") {
    return null;
  }
  const reason: unknown = data.reentry?.reason ?? null;
  if (esMotivoConocido(reason)) {
    return AVISOS[reason];
  }
  // `blocked = true` sin motivo también es un bloqueo: la app no lo contradice
  // pintando «SEGURO» (p. ej. con el incidente aún abierto, o un servidor que
  // aún no manda `reason`).
  if (reason !== null || data.phase === "reentry_blocked" || data.reentry?.blocked === true) {
    return DESCONOCIDO;
  }
  return null;
}

/**
 * La tarjeta de estado de INICIO, con el aviso de reingreso ya aplicado.
 *
 * · Sin aviso ⇒ el estado del gabinete tal cual.
 * · NO HABITAR ⇒ «NO HABITABLE» en rojo, sea cual sea el gabinete.
 * · Pendiente o motivo desconocido ⇒ su rótulo en ámbar **si el gabinete iba a
 *   decir «SEGURO»**. Si el gabinete ya dice DEGRADADO o SIN ENLACE, manda él:
 *   no afirma que el edificio esté seguro, y un rojo de SIN ENLACE no se
 *   ablanda a ámbar por un aviso menos grave. La franja de arriba sigue diciendo
 *   por qué no se puede entrar.
 *
 * El detalle del gabinete se conserva siempre: sigue vigilando, o no.
 */
export function estadoDelInmueble(
  aviso: AvisoReingreso | null,
  salud: HealthBanner,
): HealthBanner {
  if (aviso === null) {
    return salud;
  }
  if (aviso.tono === "crit") {
    return { label: aviso.rotulo, tone: "crit", detail: salud.detail };
  }
  if (salud.tone === "ok") {
    return { label: aviso.rotulo, tone: "warn", detail: salud.detail };
  }
  return salud;
}
