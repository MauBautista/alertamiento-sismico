// [T-6.26 · U-40] EL VEREDICTO DEL DICTAMEN, EN EL IDIOMA DEL OCUPANTE.
//
// La fuente de verdad es `shared/glossary/dictamen.json`, que comparten la
// consola SOC y esta app. El valor crudo sale del CHECK de `dictamens.status`
// (db/schema.sql) y lo firma un inspector; a partir de ahí lo leen dos públicos
// muy distintos, y `inhabit_monitor` no significa NADA para quien sólo quiere
// saber si puede volver a su casa. La línea de tiempo lo imprimía tal cual.
//
// ¿Por qué una COPIA y no un import del JSON? Porque el otro consumidor es
// `web/`, y `web/` y `mobile/` son dos builds distintos: ninguno puede importar
// el módulo del otro, y traer el JSON en tiempo de ejecución exigiría tocar la
// configuración del bundler de los dos. Así que se copia y se COMPRUEBA:
// `veredicto.test.ts` compara este módulo contra el JSON por igualdad, en los
// dos sentidos. Mismo patrón —y por la misma razón— que `estadoGlosario` de la
// consola.

/** Los cuatro status que un inspector puede firmar, en orden del DDL. */
export const VEREDICTOS = [
  "normal_operation",
  "inhabit_monitor",
  "restricted",
  "no_inhabit_inspect",
] as const;

export type Veredicto = (typeof VEREDICTOS)[number];

/** Lo que se le dice al OCUPANTE. El registro del operador vive en la consola. */
export const TEXTO_OCUPANTE: Record<Veredicto, string> = {
  normal_operation: "EDIFICIO APROBADO PARA REINGRESO",
  inhabit_monitor: "REINGRESO APROBADO · BAJO MONITOREO",
  restricted: "REINGRESO RESTRINGIDO",
  no_inhabit_inspect: "NO HABITABLE · REQUIERE INSPECCIÓN",
};

/**
 * Traduce un status a lo que lee el ocupante.
 *
 * Un valor que no esté en el glosario NO se degrada a «operación normal» ni se
 * imprime crudo: se dice que hay dictamen y no se promete nada. Inventarle un
 * significado a lo que no entendemos —o enseñar el identificador— son las dos
 * formas de fallar aquí, y la segunda es la que había.
 */
export function textoOcupante(status: string | null | undefined): string {
  if (status == null) {
    return "SIN DICTAMEN";
  }
  return TEXTO_OCUPANTE[status as Veredicto] ?? "DICTAMEN TÉCNICO EMITIDO";
}
