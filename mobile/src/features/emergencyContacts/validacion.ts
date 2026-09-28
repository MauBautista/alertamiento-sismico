// [T-9.80 · D-48] Validación de los contactos de emergencia EN EL CLIENTE.
//
// Espejo de `api/src/takab_api/schemas/contactos_emergencia.py`: mismo tope,
// mismo patrón de correo y mismo E.164. El servidor valida IGUAL —esto no lo
// sustituye—; sólo dice el problema junto al campo antes de gastar un viaje.

import type { ContactoIn } from "@takab/sdk";

/** Tope de contactos por titular. Espejo de `MAX_CONTACTOS` del servidor. */
export const MAX_CONTACTOS = 3;

/** Prefijo que se SUGIERE en el campo de teléfono; por sí solo no es un número. */
export const PREFIJO_SUGERIDO = "+52";

const NOMBRE_MAX = 80;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const E164_RE = /^\+[1-9][0-9]{7,14}$/;

/**
 * Un contacto tal como está en el formulario: los MISMOS campos que `ContactoIn` del SDK,
 * todos como texto (el teléfono vacío es «sin teléfono»). Se deriva del tipo generado
 * en vez de repetir sus claves: `sdkTypeParity.test.ts` exige UNA sola verdad del cable.
 */
export type ContactoBorrador = { [K in keyof ContactoIn]-?: string };

/** Claves `"<índice>.<campo>"` → mensaje. Vacío = todo en orden. */
export type ErroresPorCampo = Record<string, string>;

/** Vacío o el prefijo sugerido a secas = sin teléfono. */
export function normalizarTelefono(phone: string): string | null {
  const limpio = phone.trim();
  if (limpio === "" || limpio === PREFIJO_SUGERIDO) {
    return null;
  }
  return limpio;
}

export function validarContactos(contactos: ContactoBorrador[]): ErroresPorCampo {
  const errores: ErroresPorCampo = {};
  contactos.forEach((c, i) => {
    const nombre = c.display_name.trim();
    if (nombre.length === 0) {
      errores[`${i}.display_name`] = "Escriba el nombre.";
    } else if (nombre.length > NOMBRE_MAX) {
      errores[`${i}.display_name`] = `El nombre admite hasta ${NOMBRE_MAX} caracteres.`;
    }
    if (!EMAIL_RE.test(c.email.trim())) {
      errores[`${i}.email`] = "Correo inválido (nombre@dominio.mx).";
    }
    const tel = normalizarTelefono(c.phone);
    if (tel !== null && !E164_RE.test(tel)) {
      errores[`${i}.phone`] = "Teléfono en formato internacional, sin espacios: +52 y 10 dígitos.";
    }
  });
  return errores;
}

const CAMPOS = new Set(["display_name", "email", "phone"]);

const GENERAL_422 = "El servidor rechazó la lista. Revise los datos e inténtelo de nuevo.";

/** Quita el «Value error, » con el que pydantic antepone el mensaje del validador. */
function limpiarMensaje(msg: string): string {
  return msg.replace(/^Value error,\s*/i, "");
}

/**
 * Un 422 de FastAPI (`detail: [{loc, msg}]`) a errores por campo. Lo que no
 * apunta a un campo de un contacto —p. ej. más de 3— va a `general`.
 */
export function erroresDelServidor(detail: unknown): {
  campos: ErroresPorCampo;
  general: string | null;
} {
  if (!Array.isArray(detail)) {
    return { campos: {}, general: GENERAL_422 };
  }
  const campos: ErroresPorCampo = {};
  const sueltos: string[] = [];
  for (const item of detail) {
    const loc: unknown = item?.loc;
    const msg = typeof item?.msg === "string" ? limpiarMensaje(item.msg) : GENERAL_422;
    if (
      Array.isArray(loc) &&
      loc[1] === "contactos" &&
      typeof loc[2] === "number" &&
      typeof loc[3] === "string" &&
      CAMPOS.has(loc[3])
    ) {
      campos[`${loc[2]}.${loc[3]}`] = msg;
    } else if (Array.isArray(loc) && loc[1] === "contactos" && loc.length === 2) {
      sueltos.push(`Se admiten como máximo ${MAX_CONTACTOS} contactos.`);
    } else {
      sueltos.push(msg);
    }
  }
  return { campos, general: sueltos.length > 0 ? sueltos.join(" ") : null };
}
