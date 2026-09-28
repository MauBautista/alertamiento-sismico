// [T-9.33 · D-43] CONFIRMAR DICTAMEN — derivación PURA desde la cabeza de la
// cadena. La banda y su porqué los decidió la regla determinista `dictamen-v2`
// en la nube (regla de oro 1: aquí NO se decide nada, ni por IA ni por la app);
// esto solo traduce a palabras la procedencia que dejó en `basis`:
//   · `basis.motivos`       — cada razón que sostiene la banda;
//   · `basis.evidence`      — PGA medida, calibración de sensores, daños;
//   · `basis.params`        — los umbrales congelados con que se evaluó.
//
// Qué puede hacer la brigada lo dice la NUBE (`confirm` responde 403/409); esta
// vista solo evita ofrecer lo que la nube ya dijo que no admite:
//   · cabeza AMARILLA sin firmar ⇒ se confirma (la ÚNICA que la nube acepta);
//   · cabeza VERDE sin firmar ⇒ la emite el sistema tras la gracia (409 si se
//     confirma): se explica, no se ofrece;
//   · cabeza ROJA, o sin banda (fila histórica), sin firmar ⇒ la firma el
//     inspector, no se confirma;
//   · cabeza firmada (por quien sea) ⇒ nada que confirmar.
import type { DictamenOut, MobileStateOut } from "@takab/sdk";

import { etiquetaRol } from "@/auth/roles";
import { DAMAGE_CATEGORIES } from "@/features/damage/categories";

export type Banda = "verde" | "amarillo" | "rojo";

const STATUS_BANDA: Record<string, Banda> = {
  normal_operation: "verde",
  inhabit_monitor: "amarillo",
  restricted: "rojo",
  no_inhabit_inspect: "rojo",
};

/** Banda de una fila: la columna si es válida; si no, del status. Lo que no se
 *  entiende es ROJO — el mismo criterio que `rules.banda_de` en la nube. */
export function banda(d: { band?: string | null; status: string }): Banda {
  if (d.band === "verde" || d.band === "amarillo" || d.band === "rojo") {
    return d.band;
  }
  return STATUS_BANDA[d.status] ?? "rojo";
}

const TITULO: Record<Banda, string> = {
  verde: "DICTAMEN VERDE · OPERACIÓN NORMAL",
  amarillo: "DICTAMEN AMARILLO · HABITAR CON MONITOREO",
  rojo: "DICTAMEN ROJO · NO HABITAR · INSPECCIÓN",
};

/** Lo que el sello y el firmante leen de una fila (cabeza de la cadena o
 *  certificado móvil): el tipo de firma, la banda y el ROL de quien confirma. */
export type Firma = {
  signature_kind?: string | null;
  band?: string | null;
  confirmed_by_role?: string | null;
};

function bandaDeclarada(band: string | null | undefined): Banda | null {
  return band === "verde" || band === "amarillo" || band === "rojo" ? band : null;
}

/** Rótulo del firmante, SIEMPRE desde `signature_kind` y nunca desde
 *  `signed_by` (que solo dice «firmado»). NULL es una fila anterior a la
 *  distinción: entonces solo firmaba el inspector. Un tipo que la app no conoce
 *  no se le atribuye a nadie. El sistema dice con QUÉ banda emitió; la
 *  confirmación, QUIÉN (el rol, nunca un identificador). */
export function selloDeFirma(d: Firma): string {
  switch (d.signature_kind) {
    case null:
    case undefined:
    case "inspector":
      return "FIRMA DIGITAL · INSPECTOR";
    case "system": {
      const b = bandaDeclarada(d.band);
      return b === null
        ? "EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA"
        : `EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA · BANDA ${b.toUpperCase()}`;
    }
    case "confirmation":
      return `CONFIRMADO POR ${rolQueConfirma(d.confirmed_by_role)}`;
    default:
      return "FIRMA DIGITAL";
  }
}

function rolQueConfirma(role: string | null | undefined): string {
  return typeof role === "string" && role !== "" ? etiquetaRol(role) : "PERSONAL AUTORIZADO";
}

/** Quién firmó, por su PAPEL. Jamás el `signed_by` (un UUID interno). */
export function firmanteDe(d: Firma & { signed_by?: string | null }): string {
  switch (d.signature_kind) {
    case null:
    case undefined:
    case "inspector":
      return "INSPECTOR";
    case "system":
      return "SISTEMA";
    case "confirmation":
      return rolQueConfirma(d.confirmed_by_role);
    default:
      return "—";
  }
}

/** [F3·r3 · D-43] El cartel verde de reingreso: QUIÉN lo aprobó, del
 *  `signature_kind` de la firma vigente. `null`/ausente ⇒ la app no sabe quién
 *  firmó y no se lo atribuye a nadie (antes decía siempre «el inspector»). */
export function textoReingresoAutorizado(f: Firma | null | undefined): string {
  if (f == null) {
    return "el dictamen vigente autorizó el reingreso al inmueble.";
  }
  switch (f.signature_kind) {
    case null:
    case undefined:
    case "inspector":
      return "el dictamen técnico del inspector aprobó el reingreso al inmueble.";
    case "system":
      return "el sistema emitió el dictamen (regla automática, sin daños reportados) que autoriza el reingreso.";
    case "confirmation":
      return `dictamen confirmado por ${rolQueConfirma(f.confirmed_by_role)}: autoriza el reingreso al inmueble.`;
    default:
      return "el dictamen vigente autorizó el reingreso al inmueble.";
  }
}

/** La banda rotulada para el certificado; sin banda (histórico) o una que la
 *  app no entiende ⇒ null: no se inventa un color. */
export function bandaRotulada(band: string | null | undefined): string | null {
  const b = bandaDeclarada(band);
  return b === null ? null : b.toUpperCase();
}

/** [F3·r3] La entrada a CONFIRMAR DICTAMEN desde el panel táctico: SOLO si el
 *  servidor dice que el reingreso espera una confirmación y el perfil puede
 *  confirmar. Devuelve el incidente a confirmar, o null (sin botón). */
export function incidenteAConfirmar(
  data: Pick<MobileStateOut, "incident" | "reentry">,
  acciones: Partial<Record<string, boolean>> | null | undefined,
): string | null {
  if (acciones?.confirm_dictamen !== true) {
    return null;
  }
  if (data.reentry?.reason !== "pendiente_confirmacion") {
    return null;
  }
  return data.reentry.incident_id ?? data.incident?.incident_id ?? null;
}

/** Lista de revisión corta: lo que la brigada verifica ANTES de confirmar. */
const REVISION: readonly string[] = [
  "Recorra el inmueble: sin grietas nuevas en muros, columnas ni losas.",
  "Sin olor a gas, fugas de agua ni chispas en tableros eléctricos.",
  "Salidas y rutas de evacuación despejadas.",
  "Si encuentra daño, repórtelo antes de confirmar: el dictamen se vuelve a evaluar.",
];

export type ConfirmacionView =
  | { tipo: "sin_dictamen" }
  | { tipo: "ya_firmado"; banda: Banda; titulo: string; firmante: string }
  | { tipo: "solo_inspector"; banda: Banda; titulo: string; porque: string[] }
  | { tipo: "lo_firma_el_sistema"; banda: Banda; titulo: string; porque: string[] }
  | {
      tipo: "confirmable";
      dictamenId: string;
      banda: Banda;
      titulo: string;
      porque: string[];
      revision: readonly string[];
    };

function obj(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function g(v: number): string {
  return `${Number(v.toPrecision(3))} g`;
}

function etiquetaDano(key: string): string {
  const c = DAMAGE_CATEGORIES.find((x) => x.key === key);
  return c ? c.label.toLowerCase() : "categoría no reconocida";
}

/** Una frase por motivo de la regla, con los números de `basis`. */
function porQue(basis: Record<string, unknown>): string[] {
  const motivos = Array.isArray(basis.motivos)
    ? basis.motivos.filter((m): m is string => typeof m === "string")
    : [];
  if (motivos.length === 0) {
    return ["La regla no dejó el detalle de la evaluación."];
  }
  const ev = obj(basis.evidence);
  const params = obj(basis.params);
  const pga = num(ev.pga_g);
  const verde = num(params.verde_max_g);
  const rojo = num(params.rojo_min_g);
  const activos = num(ev.active_sensors);
  const sinCal = num(ev.uncalibrated_sensors);

  const frases: string[] = [];
  let otros = false;
  for (const m of motivos) {
    if (m === "sin_pga") {
      frases.push(
        "No hay aceleración medida en el edificio: sin ese dato no se puede dar el verde.",
      );
    } else if (m === "pga_banda_amarilla") {
      frases.push(
        pga !== null && verde !== null && rojo !== null
          ? `La aceleración máxima medida (${g(pga)}) está entre ${g(verde)} y ${g(rojo)}.`
          : "La aceleración máxima medida está en la franja amarilla.",
      );
    } else if (m === "pga_banda_roja") {
      frases.push(
        pga !== null && rojo !== null
          ? `La aceleración máxima medida (${g(pga)}) alcanza o supera ${g(rojo)}.`
          : "La aceleración máxima medida está en la franja roja.",
      );
    } else if (m === "pga_bajo_verde") {
      frases.push(
        pga !== null && verde !== null
          ? `La aceleración máxima medida (${g(pga)}) está por debajo de ${g(verde)}.`
          : "La aceleración máxima medida está por debajo de la franja amarilla.",
      );
    } else if (m === "sin_calibracion") {
      frases.push(
        activos !== null && sinCal !== null && activos > 0
          ? `${sinCal} de ${activos} sensores activos no tiene calibración declarada: sus lecturas son relativas.`
          : "No hay sensores activos con calibración declarada: las lecturas son relativas.",
      );
    } else if (m.startsWith("dano:")) {
      frases.push(`Se reportó un daño: ${etiquetaDano(m.slice("dano:".length))}.`);
    } else if (m === "dano_sin_categoria") {
      frases.push("Se reportó un daño sin categoría.");
    } else {
      otros = true;
    }
  }
  if (otros) {
    frases.push("Otro motivo registrado por la regla.");
  }
  return frases;
}

/** La cabeza vigente (la más reciente de la cadena) ⇒ qué se pinta. */
export function confirmacionView(head: DictamenOut | undefined | null): ConfirmacionView {
  if (head == null) {
    return { tipo: "sin_dictamen" };
  }
  const b = banda(head);
  const titulo = TITULO[b];
  if (head.signed_by != null) {
    return { tipo: "ya_firmado", banda: b, titulo, firmante: selloDeFirma(head) };
  }
  const porque = porQue(obj(head.basis));
  // [F3·r3] La nube sólo confirma un AMARILLO con la COLUMNA `band` puesta
  // (`routers/dictamens.confirm_dictamen`): el VERDE lo firma el sistema y una
  // fila sin banda no es salida de la regla v2. Ofrecer el botón era un 409 fijo.
  if (head.band === "verde") {
    return { tipo: "lo_firma_el_sistema", banda: b, titulo, porque };
  }
  if (b === "rojo" || head.band !== "amarillo") {
    return { tipo: "solo_inspector", banda: b, titulo, porque };
  }
  return {
    tipo: "confirmable",
    dictamenId: head.dictamen_id,
    banda: b,
    titulo,
    porque,
    revision: REVISION,
  };
}
