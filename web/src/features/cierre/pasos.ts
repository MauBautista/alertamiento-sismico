// [T-9.41 · D-43] EL CORAZÓN DEL ASISTENTE «CIERRE DEL EVENTO»: función pura.
//
// Dos reglas y ninguna es cosmética:
//
//  · TODO «hecho» SALE DE UN DATO DEL SERVIDOR. Ningún clic recordado, ningún
//    estado local, marca un paso como hecho: el operador que acusa ve «hecho»
//    cuando la FILA dice `state !== 'open'`, no cuando su botón dijo «ACUSADO».
//  · UN DATO QUE NO CARGÓ NO ES «PENDIENTE». Es `sin_dato`. «Pendiente» afirma
//    algo sobre el mundo («nadie lo hizo»); `sin_dato` afirma algo sobre nuestro
//    conocimiento («no lo sé»). Es la regla de oro 7 bajada a un paso.
//
// Los requisitos del cierre son el ESPEJO del servidor
// (`api/.../routers/incidents_ops.py::close_incident`), que es quien decide:
// ya_cerrado → sin_acuse → sismo_en_curso → sin_clasificacion → sin_dictamen.
// `sismo_en_curso` no se puede anticipar aquí (el tier vive en el servidor): lo
// traduce el 409.

import matriz from "../../../../shared/fixtures/rbac-matrix.json";
import { ETIQUETA_ROL, etiquetaDeRol } from "../../auth/rolesHistoricos";
import { damageCategoryLabel } from "../triage/structural";

/** Espejo de `incidents_ops.MOTIVO_MIN_CHARS` (tras `strip()`). */
export const MOTIVO_MIN_CHARS = 20;

/**
 * Espejo de `incident/classification.py::CIERRA_EL_INCIDENTE`: las que NO cierran
 * solas y por tanto piden dictamen firmado (o motivo) para cerrarse.
 */
const PIDEN_DICTAMEN: ReadonlySet<string> = new Set(["real", "indeterminado"]);

/** Las acciones de la matriz que este asistente consulta. */
export type AccionMatriz =
  | "ack_incident"
  | "sign_dictamen"
  | "confirm_dictamen"
  | "classify_incident"
  | "generate_report"
  | "close_incident";

export type Permisos = Partial<Record<AccionMatriz, boolean>>;

/** Lo que el paso ofrece hacer. Dos de ellas son ENLACES a Evaluación, no mutaciones. */
export type AccionPaso =
  | "ack_incident"
  | "confirm_dictamen"
  | "firmar_en_evaluacion"
  | "levantar_restriccion"
  | "classify_incident"
  | "close_incident";

export type EstadoPaso = "hecho" | "pendiente" | "no_aplica" | "bloqueado" | "sin_dato";

export type IdPaso = "acusar" | "sacudida" | "reportes" | "dictamen" | "clasificar" | "cierre";

export interface Paso {
  id: IdPaso;
  titulo: string;
  estado: EstadoPaso;
  /** Una línea: por qué el paso está como está. */
  porque: string;
  requeridoParaCerrar: boolean;
  /** Sólo si `me.allowed_actions` la concede (y el paso la admite). */
  accion?: AccionPaso;
  /** Rótulos de los roles que SÍ podrían, cuando este usuario no puede. */
  quienPuede?: readonly string[];
  /** Sólo en `cierre`: el MOTIVO escrito es obligatorio. */
  exigeMotivo?: boolean;
}

/** Cada campo en `null` = ESE dato no cargó (en vuelo o fallido). */
export interface HechosDelCierre {
  incidente: { state: string; max_pga_g: number | null; max_pgv_cms: number | null } | null;
  /** La cadena en el orden del servidor: `[0]` es la CABEZA. */
  dictamenes: readonly { signed_by: string | null; band?: string | null; status: string }[] | null;
  clasificacion: { vigente: string | null } | null;
  reportes: readonly unknown[] | null;
}

type MatrizRol = { routes: string[]; actions: Record<string, boolean> };
const ROLES = matriz.roles as Record<string, MatrizRol>;
const INTERNOS = matriz.internal_roles as readonly string[];

/**
 * Rótulos de los roles del CLIENTE que tienen alguna de las acciones, derivados
 * de `shared/fixtures/rbac-matrix.json` (generado desde `auth/matrix.py`) y
 * rotulados con `etiquetaDeRol`, en el orden de `ETIQUETA_ROL`.
 *
 * Los roles INTERNOS de TAKAB quedan fuera: a quien le falta el permiso se le
 * dice a quién de SU organización pedírselo.
 */
export function quienPuede(...acciones: AccionMatriz[]): readonly string[] {
  return Object.keys(ETIQUETA_ROL)
    .filter((r) => !INTERNOS.includes(r))
    .filter((r) => acciones.some((a) => ROLES[r]?.actions[a] === true))
    .map(etiquetaDeRol);
}

/** Acción concedida ⇒ `accion`; si no, ⇒ `quienPuede`. */
function gate(
  puede: Permisos,
  accion: AccionPaso,
  permiso: AccionMatriz,
  alternativos: AccionMatriz[] = [permiso],
): Pick<Paso, "accion" | "quienPuede"> {
  return puede[permiso] === true ? { accion } : { quienPuede: quienPuede(...alternativos) };
}

function cabezaFirmada(h: HechosDelCierre): boolean | null {
  if (h.dictamenes === null) return null;
  const head = h.dictamenes[0];
  return head !== undefined && head.signed_by !== null;
}

/**
 * El campo MOTIVO es obligatorio: clasificación vigente `real`/`indeterminado` y
 * la cabeza SIN firmar (o sin cadena). Sin la cadena cargada no se decide.
 */
export function motivoExigido(h: HechosDelCierre): boolean {
  const vigente = h.clasificacion?.vigente ?? null;
  if (vigente === null || !PIDEN_DICTAMEN.has(vigente)) return false;
  const firmada = cabezaFirmada(h);
  return firmada === false;
}

const SIN_DATO = "SIN DATO · NO SE PUDO LEER DEL SERVIDOR";

function pasoAcusar(h: HechosDelCierre, puede: Permisos): Paso {
  const base = { id: "acusar", titulo: "ACUSAR", requeridoParaCerrar: true } as const;
  if (h.incidente === null) return { ...base, estado: "sin_dato", porque: SIN_DATO };
  if (h.incidente.state !== "open") {
    return { ...base, estado: "hecho", porque: "El incidente ya fue acusado" };
  }
  return {
    ...base,
    estado: "pendiente",
    porque: "Nadie lo ha acusado todavía: el cierre lo exige",
    ...gate(puede, "ack_incident", "ack_incident"),
  };
}

function pasoSacudida(h: HechosDelCierre): Paso {
  const base = {
    id: "sacudida",
    titulo: "REVISAR LA SACUDIDA",
    requeridoParaCerrar: false,
  } as const;
  if (h.incidente === null) return { ...base, estado: "sin_dato", porque: SIN_DATO };
  const pga = h.incidente.max_pga_g;
  if (pga === null) {
    return { ...base, estado: "no_aplica", porque: "El sensor no registró PGA en este incidente" };
  }
  return { ...base, estado: "hecho", porque: `El sensor registró ${pga.toFixed(3)} g de PGA` };
}

function pasoReportes(h: HechosDelCierre): Paso {
  const base = { id: "reportes", titulo: "REPORTES DE CAMPO", requeridoParaCerrar: false } as const;
  if (h.reportes === null) return { ...base, estado: "sin_dato", porque: SIN_DATO };
  if (h.reportes.length === 0) {
    return {
      ...base,
      estado: "pendiente",
      porque: "Sin reportes de la brigada: no impide cerrar",
    };
  }
  const n = h.reportes.length;
  return {
    ...base,
    estado: "hecho",
    porque: `${n} reporte${n === 1 ? "" : "s"} de daño recibido${n === 1 ? "" : "s"}`,
  };
}

/** La explicación del paso 4 sale de la BANDA de la cabeza, que es un dato del servidor. */
function porqueDeBanda(band: string | null | undefined): string {
  switch (band) {
    case "verde":
      return "BANDA VERDE · el sistema lo firma solo tras 5 min de calma";
    case "amarillo":
      return "BANDA AMARILLA · lo confirma un brigadista, el inspector o el administrador";
    case "rojo":
      return "BANDA ROJA · solo el INSPECTOR puede firmarlo";
    default:
      return "Preliminar sin firmar · lo firma el inspector en Evaluación";
  }
}

function pasoDictamen(h: HechosDelCierre, puede: Permisos): Paso {
  const vigente = h.clasificacion?.vigente ?? null;
  // Sin clasificación todavía no se sabe si será terminal: se trata como exigible.
  const requerido = vigente === null || PIDEN_DICTAMEN.has(vigente);
  const base = { id: "dictamen", titulo: "DICTAMEN", requeridoParaCerrar: requerido } as const;
  if (h.dictamenes === null) return { ...base, estado: "sin_dato", porque: SIN_DATO };
  const head = h.dictamenes[0];
  const cerrado = h.incidente?.state === "closed";

  if (head !== undefined && head.signed_by !== null) {
    const restriccion = cerrado && head.status === "no_inhabit_inspect";
    return {
      ...base,
      estado: "hecho",
      porque: restriccion
        ? "Firmado: NO HABITAR hasta inspección. Sólo el inspector levanta la restricción"
        : "La cabeza de la cadena está firmada",
      ...(restriccion && puede.sign_dictamen === true
        ? { accion: "levantar_restriccion" as const }
        : {}),
    };
  }

  const cola = requerido ? "" : " · no hace falta para esta clasificación";
  const porque =
    head === undefined
      ? `SIN DICTAMEN · lo firma el inspector en Evaluación${cola}`
      : `${porqueDeBanda(head.band)}${cola}`;

  if (head?.band === "amarillo") {
    // AMARILLO: lo confirma quien tenga `confirm_dictamen`; quien sólo firme, firma.
    if (puede.confirm_dictamen === true) {
      return { ...base, estado: "pendiente", porque, accion: "confirm_dictamen" };
    }
    return {
      ...base,
      estado: "pendiente",
      porque,
      ...gate(puede, "firmar_en_evaluacion", "sign_dictamen", [
        "confirm_dictamen",
        "sign_dictamen",
      ]),
    };
  }
  return {
    ...base,
    estado: "pendiente",
    porque,
    ...gate(puede, "firmar_en_evaluacion", "sign_dictamen"),
  };
}

const ETIQUETA_CLASIF: Readonly<Record<string, string>> = {
  real: "REAL",
  falso_positivo: "FALSO POSITIVO",
  prueba: "PRUEBA",
  indeterminado: "INDETERMINADO",
  reproduccion: "REPRODUCCIÓN",
};

function pasoClasificar(h: HechosDelCierre, puede: Permisos): Paso {
  const base = { id: "clasificar", titulo: "CLASIFICAR", requeridoParaCerrar: true } as const;
  if (h.clasificacion === null) return { ...base, estado: "sin_dato", porque: SIN_DATO };
  const cerrado = h.incidente?.state === "closed";
  // Reclasificar (sustituir la vigente) sigue siendo posible mientras no se cierre.
  const oferta = cerrado ? {} : gate(puede, "classify_incident", "classify_incident");
  const vigente = h.clasificacion.vigente;
  if (vigente !== null) {
    return {
      ...base,
      estado: "hecho",
      porque: `Clasificado como ${ETIQUETA_CLASIF[vigente] ?? vigente.toUpperCase()}`,
      ...oferta,
    };
  }
  return {
    ...base,
    estado: "pendiente",
    porque: "Sin clasificación: el cierre la exige",
    ...oferta,
  };
}

function pasoCierre(h: HechosDelCierre, puede: Permisos): Paso {
  const base = { id: "cierre", titulo: "INFORME Y CIERRE", requeridoParaCerrar: false } as const;
  // CERRADO lo dice la fila y basta: es el dato más autoritativo de la pantalla.
  if (h.incidente?.state === "closed") {
    return { ...base, estado: "hecho", porque: "El evento está CERRADO" };
  }
  if (h.incidente === null || h.clasificacion === null || h.dictamenes === null) {
    return { ...base, estado: "sin_dato", porque: SIN_DATO };
  }
  const faltan: string[] = [];
  if (h.incidente.state === "open") faltan.push("ACUSAR");
  if (h.clasificacion.vigente === null) faltan.push("CLASIFICAR");
  if (faltan.length > 0) {
    return {
      ...base,
      estado: "bloqueado",
      exigeMotivo: motivoExigido(h),
      porque: `Antes de cerrar falta: ${faltan.join(" y ")}`,
    };
  }
  const exigeMotivo = motivoExigido(h);
  return {
    ...base,
    estado: "pendiente",
    exigeMotivo,
    porque: exigeMotivo
      ? `Sin dictamen firmado: se cierra con un MOTIVO escrito de al menos ${MOTIVO_MIN_CHARS} caracteres`
      : "Listo para cerrar",
    ...gate(puede, "close_incident", "close_incident"),
  };
}

/** Los seis pasos, en el orden del diseño. */
export function derivarPasos(hechos: HechosDelCierre, puede: Permisos): Paso[] {
  return [
    pasoAcusar(hechos, puede),
    pasoSacudida(hechos),
    pasoReportes(hechos),
    pasoDictamen(hechos, puede),
    pasoClasificar(hechos, puede),
    pasoCierre(hechos, puede),
  ];
}

/**
 * Paso 3: el recuento de reportes de daño POR TIPO, con el rótulo de
 * `triage/structural.ts` (el mismo que pinta Evaluación). Una categoría se cuenta
 * una vez por reporte que la trae; el orden es de más a menos frecuente.
 */
export function recuentoPorTipo(
  reportes: readonly { categories: readonly Record<string, unknown>[] }[],
): { tipo: string; n: number }[] {
  const cuenta = new Map<string, number>();
  for (const r of reportes) {
    const tipos = new Set(r.categories.map((c) => damageCategoryLabel(String(c.key ?? ""))));
    for (const t of tipos) cuenta.set(t, (cuenta.get(t) ?? 0) + 1);
  }
  return [...cuenta.entries()]
    .map(([tipo, n]) => ({ tipo, n }))
    .sort((a, b) => b.n - a.n || a.tipo.localeCompare(b.tipo));
}
