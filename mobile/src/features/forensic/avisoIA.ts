// [T-7.27 · D-32] EL AVISO DE QUE LA FOTO PUEDE SALIR DEL INMUEBLE.
//
// Módulo PURO: sólo el texto. Lo pinta `app/camera.tsx` sobre el visor y sobre
// la revisión, y NO ENTRA EN EL SELLO. Eso lo vigilan dos guardas distintas y
// hacen falta las dos: `watermark.test.ts` (bloque T-7.27) comprueba que no se
// cuela en las funciones puras —la lista de líneas y el manifiesto—, y
// `tests/app/camera-states.test.tsx` (bloque «lo que se HORNEA en el JPEG»)
// mide el subárbol de `composeRef`, que es lo único que view-shot cuece en el
// bitmap y en el SHA-256. La segunda no existía y la primera no la sustituía.
//
// ---------------------------------------------------------------------------
// POR QUÉ EXISTE, Y POR QUÉ NO BASTABA EL QUE YA HABÍA
// ---------------------------------------------------------------------------
// Esta pantalla ya avisaba de una cosa —«METADATOS RETENIDOS · SNAPSHOT <iso>
// · sin conexión»—, y es un aviso sobre la FIABILIDAD del sello: de qué
// instante salieron el PGA y el incidente con los que se hornea. No dice nada
// del DESTINO de la imagen, que es lo que `D-32` cambió: la capa narrativa
// recibe las fotos del reporte de daños, redimensionadas y leídas de S3, y
// eso las saca del edificio hacia OpenRouter (Estados Unidos) y el proveedor
// del modelo. Mandar la fotografía de un inmueble a un tercero es exactamente
// lo que `RESIDENCIA-DE-DATOS-TAKAB.md` existe para declarar, y esta pantalla
// es el único sitio del sistema donde la persona que la toma puede enterarse
// a tiempo.
//
// ---------------------------------------------------------------------------
// LAS CUATRO DECISIONES DEL TEXTO — cada una cierra una forma de mentir
// ---------------------------------------------------------------------------
//  1. **«PUEDE», no «se envía».** La capa narrativa nace apagada y se enciende
//     **por despliegue** (`TAKAB_API_OPENROUTER_ENABLED`, T-7.26). Ojo al
//     alcance, porque esta línea decía «y por cliente» y eso hoy es falso:
//     medido el 2026-09-21 en `narrative/__init__.py::select_provider`, el
//     interruptor es del despliegue ENTERO — no hay forma de tenerla encendida
//     para un cliente con cláusula firmada y apagada para su vecino sin ella
//     (`RESIDENCIA-DE-DATOS-TAKAB.md §3.1`). Un aviso en indicativo sería falso
//     en todo sitio que no la encienda, y un aviso que se descubre falso deja
//     de leerse — incluido el día que sí sea cierto. El teléfono, además, NO
//     sabe si está encendida: preguntarlo sería inventarse un dato de servidor
//     para decorar un deslinde.
//  2. **Se dice a dónde va, no sólo que «se procesa con IA».** Sin «FUERA DE
//     MÉXICO» la frase deja creer que ocurre dentro del mismo sistema donde ya
//     viven sus datos, que es precisamente la confusión que el documento de
//     residencia desmonta.
//  3. **Se declara el límite (regla de oro 1).** La prosa jamás toca el
//     veredicto, la clasificación ni el tier. Si el brigadista cree que la
//     máquina juzga el daño que está fotografiando, el aviso le ha enseñado el
//     sistema al revés y además le desplaza la responsabilidad.
//  4. **Se dice lo que viaja, MEDIDO, y hoy es menos que ayer.** Este punto
//     decía que la marca de agua horneada viajaba dentro del JPEG con hora,
//     GPS e identificador de operador. Era cierto cuando se escribió y dejó de
//     serlo el 2026-09-21: la banda se TAPA antes de salir
//     (`api/src/takab_api/narrative/marca.py`), y lo que se tapa se mide sobre
//     los píxeles contra la geometría que declara este mismo módulo — no se
//     supone. Lo descubrió el escéptico de `T-7.27` decodificando el base64
//     del cuerpo real: la foto llevaba PINTADOS los dos identificadores que la
//     lista blanca de texto retiene a propósito.
//
//     Así que el aviso dice lo que hoy es verdad: sale la IMAGEN DEL DAÑO, sin
//     el sello. Ni «sus datos no viajan» (falso: viaja la fotografía de su
//     inmueble) ni «viaja con su identificador» (falso desde el tapado).
//     Prometer de más asusta sin motivo; prometer de menos es lo que este
//     repositorio lleva una fase entera cazando.
//
// Lo que este aviso NO es: un consentimiento. Nadie firma nada tocando una
// pantalla, y la cláusula contractual sigue pendiente
// (`PENDIENTES-MAURICIO §4.7`). Esto es información, que es lo que el software
// sí puede entregar.

/** Titular. Es lo primero que se lee, y por eso lleva el hecho, no la etiqueta. */
export const AVISO_IA_TITULO = "ESTA FOTO PUEDE SALIR DEL INMUEBLE";

/** Qué sale, a dónde y con qué va pegado. */
export const AVISO_IA_ALCANCE =
  "Si este despliegue tiene encendida la redacción asistida, la imagen se envía FUERA DE MÉXICO " +
  "a un proveedor de inteligencia artificial para que describa el daño en el informe. Se envía " +
  "SIN el sello: se tapa antes de salir la franja con la hora, la ubicación y su identificador " +
  "de operador. Tampoco viajan su nombre ni su teléfono.";

/** El límite duro, en la misma pantalla y no en un documento que nadie abre. */
export const AVISO_IA_LIMITE =
  "LA IA NO DECIDE: no clasifica el daño, no firma el dictamen y no cambia ninguna alerta.";

/**
 * Las tres líneas, en orden fijo y todas a la vista.
 *
 * Nada de «ver más»: la lección de T-2.104 que ya cita `watermark.ts` es que
 * lo que se lee primero manda, y un deslinde escondido no deslinda.
 */
export function avisoIALineas(): string[] {
  return [AVISO_IA_TITULO, AVISO_IA_ALCANCE, AVISO_IA_LIMITE];
}
