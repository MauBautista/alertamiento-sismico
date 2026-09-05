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

type FilaGlosario = { consola: string; pinta_cifra: boolean };

const ESTADOS = glosario.estados as Record<string, FilaGlosario>;

/** El texto de ese estado en la consola. Fuente única: el glosario compartido. */
export function rotuloProcedencia(estado: string): string {
  return ESTADOS[estado]?.consola ?? ESTADOS.sin_dato_externo.consola;
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
