// [T-2.85.b] EL VOCABULARIO DE ESTADO DE LA CONSOLA — copia literal del glosario.
//
// La fuente de verdad es `shared/glossary/estados.json`, que comparten la consola
// SOC y el panel del gabinete. Quien opera mira LAS DOS pantallas —primero el
// panel en el sitio, luego la consola desde el SOC, o al revés en plena
// madrugada— y cada traducción que hace de cabeza bajo presión es un sitio donde
// se equivoca.
//
// ¿Por qué una COPIA y no un import del JSON? Porque el otro consumidor del
// glosario es `edge/takab_edge/local_api/index.html`, que se sirve como un único
// archivo estático desde un Pi sin build ni red y NO PUEDE IMPORTAR NADA. El
// formato neutral que los dos pueden leer es JSON, y traerlo a `web/` en tiempo
// de ejecución exigiría tocar `vite.config.ts` (`fs.allow`) y `package.json`.
// Así que se copia y se COMPRUEBA: `estadoGlosario.test.ts` compara este módulo
// contra el JSON por igualdad, en los dos sentidos. Mismo patrón —y por la misma
// razón física— que `@takab/design-tokens` con la paleta del panel.
//
// Estos NO son rótulos de la consola: son los estados. `OPERATIVO`, `DEGRADADO` y
// `SIN ENLACE` los PRODUCE la nube (`api/.../schemas/fleet.py::derive_fleet_state`)
// y llegan en `gateway.derived_state`; compararlos contra estas constantes es lo
// que impide que un renombrado en el productor deje la consola contando ceros en
// silencio.

/** Veredicto de la nube sobre un gabinete, tal cual llega en `derived_state`. */
export const OPERATIVO = "OPERATIVO";
/** Latido fresco, alguna métrica fuera de rango. La consola nombra las razones. */
export const DEGRADADO = "DEGRADADO";
/** El gabinete y la nube no se hablan. El edificio SIGUE PROTEGIDO (regla de oro 2). */
export const SIN_ENLACE = "SIN ENLACE";
/** No hay dato. Nunca se midió, o el módulo que lo mide no está. Jamás en verde. */
export const SD = "S/D";
/** Dado de baja en la consola central. Sigue protegiendo; deja de recibir órdenes. */
export const RETIRADO = "RETIRADO";
/** El dato existe pero es viejo: se está mirando una foto congelada. */
export const DATO_RETENIDO = "DATOS RETENIDOS";
/** El módulo que gobierna algo no responde. Lo más grave que dicen las dos pantallas. */
export const NO_CONTESTA = "NO CONTESTA";

/** Los tres veredicos que sirve `GET /fleet/gateways` en `derived_state`. */
export type EstadoDerivado = typeof OPERATIVO | typeof DEGRADADO | typeof SIN_ENLACE;
