// [T-6.13] «CONOCIDO Y FALLÓ ⇒ RETENIDO» — la regla, en un solo sitio.
//
// Los tres marcos de la franja de escena —simulacro, mantenimiento y modo
// demostración— llegaron cada uno a la misma conclusión por su cuenta, y la
// escribieron a mano:
//
//     const frameError  = readError !== null && !known ? readError : null;
//     const staleSince  = readError !== null &&  known ? updatedAt : null;
//
// La regla es de la casa (regla de oro 7) y no es obvia, así que merecía nombre
// en vez de tres copias:
//
//   · **Si nunca supimos nada**, el fallo ES el estado. Se pinta el error: no hay
//     dato viejo que enseñar y callarlo sería enseñar una pantalla en blanco
//     como si no pasara nada.
//   · **Si ya supimos algo**, el fallo NO borra lo que sabíamos: lo marca como
//     RETENIDO con la hora de la última lectura buena. Pintar un simulacro de
//     hace tres minutos como si siguiera vivo es exactamente lo que la regla de
//     oro 7 prohíbe; borrarlo sin decirlo, también.
//
// Los tres no se distinguían en la regla: se distinguían en QUÉ cuenta como
// conocido (un simulacro o uno armado; una ventana en la lista; una respuesta
// del modo demo) y en de dónde sale el mensaje. Eso es lo que sigue siendo de
// cada uno, y por eso entra por parámetro.

export interface LecturaDegradada {
  /** Lo que el marco pinta como ERROR. Sólo cuando no hay nada conocido. */
  error: string | null;
  /** Instante de la última lectura buena; `null` mientras la lectura viva. */
  staleSince: number | null;
}

/**
 * @param fallo      Mensaje del fallo de LECTURA, o `null` si la lectura fue bien.
 * @param conocido   ¿El servidor nos dijo algo alguna vez que siga en pantalla?
 * @param updatedAt  Instante de esa última lectura buena (epoch ms).
 */
export function staleDeLectura(
  fallo: string | null,
  conocido: boolean,
  updatedAt: number,
): LecturaDegradada {
  if (fallo === null) return { error: null, staleSince: null };
  return conocido ? { error: null, staleSince: updatedAt } : { error: fallo, staleSince: null };
}
