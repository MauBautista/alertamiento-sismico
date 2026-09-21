// [T-5.10] Procedencia de la cifra sísmica EXTERNA, en la consola.
//
// **Con procedencia, o no se pinta.** TAKAB mide lo que pasó en un edificio; la
// magnitud, el epicentro, la profundidad y la hora de origen los publica una
// fuente oficial. Las dos cosas se leen en la misma pantalla y se confunden con
// facilidad, porque **una cifra sin procedencia se lee como propia**.
//
// El vocabulario NO se escribe aquí: se lee de `shared/glossary/procedencia.json`,
// que comparten las tres superficies (panel del gabinete, consola y app). El
// panel no puede importar nada —se sirve como un archivo estático desde el Pi—,
// así que el punto de encuentro tiene que ser un JSON.

import glosario from "../../../../shared/glossary/procedencia.json";

export type EstadoProcedencia =
  | "sin_dato_externo"
  | "consultando"
  | "preliminar"
  | "confirmado"
  | "sin_correlacion";

type FilaGlosario = { consola: string; pinta_cifra: boolean; significa: string };

const ESTADOS = glosario.estados as Record<string, FilaGlosario>;

/**
 * Los estados que DECLARA el glosario, en el orden en que los declara.
 *
 * Existe para que las pantallas se deriven de él en vez de enumerarlo: una lista
 * escrita a mano en la consola es una segunda verdad sobre el mismo hecho, y
 * cuando el glosario estrene un sexto estado la lista de aquí seguiría en cinco
 * — con el estado nuevo cayendo silenciosamente en el `else` de turno. Es el
 * mismo censo que `api/src/takab_api/procedencia.py::estados()`.
 */
export const ESTADOS_PROCEDENCIA: string[] = Object.keys(ESTADOS);

/** ¿El glosario compartido declara este estado? Sin esto, un estado nuevo se
 * traduce con el rótulo de otro y nadie se entera. */
export function esEstadoConocido(estado: string): boolean {
  return Object.prototype.hasOwnProperty.call(ESTADOS, estado);
}

/** El texto de ese estado en la consola. Fuente única: el glosario compartido. */
export function rotuloProcedencia(estado: string): string {
  return ESTADOS[estado]?.consola ?? ESTADOS.sin_dato_externo.consola;
}

/**
 * QUÉ SIGNIFICA ese estado, con las palabras del glosario.
 *
 * Es lo que permite que una pantalla explique los cinco hechos sin escribirlos
 * cinco veces: el texto vive donde vive el vocabulario, y las tres superficies
 * cuentan lo mismo. `null` en un estado que el glosario no declara — declarar la
 * ignorancia es oficio de quien pinta, y ese texto no puede salir de aquí.
 */
export function significadoProcedencia(estado: string): string | null {
  return ESTADOS[estado]?.significa ?? null;
}

/**
 * ¿Este estado autoriza a pintar la cifra externa?
 *
 * Solo `preliminar` y `confirmado`. Los otros tres son formas distintas de no
 * tener el dato — y las tres se pintan **con su texto**, nunca con un hueco: un
 * hueco se lee como «no pasó nada», que es justo lo contrario de «no lo sé».
 */
export function pintaCifra(estado: string): boolean {
  return ESTADOS[estado]?.pinta_cifra === true;
}

/**
 * La procedencia como una línea legible: fuente y hora de consulta.
 *
 * Va SIEMPRE junto a la cifra. Sin ella la cifra no se pinta, así que devolver
 * `null` aquí es la señal de que no hay nada que mostrar.
 */
export function citaDeProcedencia(
  fuente: string | null | undefined,
  consultadaEn: string | null | undefined,
): string | null {
  if (!fuente || !consultadaEn) return null;
  const d = new Date(consultadaEn);
  if (Number.isNaN(d.getTime())) return null;
  return `${fuente} · consultado ${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
