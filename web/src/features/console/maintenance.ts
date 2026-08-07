// T-2.71 · Lo que la consola DICE de una ventana de mantenimiento.
//
// La mitad pura del criterio 2 ("la consola lo dice en pantalla mientras dure;
// nadie debe deducirlo"). Vive aparte del banner porque lo consumen DOS
// pantallas —el banner de la consola y la tarjeta de flota— y una ventana que
// se anunciara distinto en cada una sería peor que no anunciarla.
//
// Cuatro decisiones que este módulo defiende:
//
// 1. **El vocabulario del acuse no se inventa.** `N/M ALARMAS SILENCIADAS` +
//    `K SIN ALARMA EXISTENTE` es el mismo molde que `ackLine` en DrillBanner
//    (`N/M ACUSADOS` + `K SIN GABINETE COMANDABLE`): la lección de T-2.48 es que
//    colapsar "no había a quién mandárselo" con "no acusó" es una mentira. Aquí
//    sería peor, porque diría que una vigilancia está apagada cuando nunca
//    existió.
//
// 2. **La ventana es ADITIVA, jamás sustitutiva.** `windowCovering` devuelve la
//    ventana que tapa a un gabinete, y quien la pinta la añade AL LADO del
//    `derived_state`. Reemplazar `SIN ENLACE` por un estado neutro reproduciría
//    exactamente el cero tranquilizador que T-2.59 cerró.
//
// 3. **Nada de esto AFIRMA el silencio: lo declara medido.** El titular sale de
//    `silenced/requested`, que es lo que el servidor releyó de CloudWatch, y la
//    causa de lo que no quedó mudo sale de `mute_rule`. Un rótulo fijo
//    —«ALARMAS DE OPERACIÓN SILENCIADAS», que es lo que había— es una afirmación
//    que el mismo payload puede estar desmintiendo con un `0/N`, y con
//    `ops_muting_enabled=False` (el default de producción) SIEMPRE la desmiente.
//
// 4. **Y "medido" tampoco se supone: viene marcado.** `mute_verified=false` es
//    el acuse A CIEGAS —el `Put` salió, el `Get` que lo comprueba no se pudo
//    leer— y el servidor lo rellena con `silenced = requested` a propósito, o
//    sea con la MISMA forma que un éxito. Leer las cifras sin mirar ese flag es
//    vender una suposición como una medida: el primo hermano del punto 3, por
//    otro camino, y la razón por la que ese campo existe en el JSON.

import type { MaintenanceWindowOut } from "@takab/sdk";

import { utcClock } from "../../lib/time";

/**
 * Lo que de VERDAD quedó mudo, medido por el servidor. Cinco casos, no dos.
 *
 * - `all` — todas las pedidas quedaron mudas, y se COMPROBÓ. Es el ÚNICO caso
 *   en el que se puede afirmar que la vigilancia de ese gabinete está apagada.
 * - `assumed` — el acuse no se pudo leer: las cifras son una suposición.
 * - `partial` — parte sigue viva: el on-call VA a recibir esos correos.
 * - `none` — ninguna quedó muda: la ventana está abierta y las alarmas suenan.
 * - `none_requested` — no había ninguna que callar (gabinete sin `iot_thing`).
 *
 * **La lista es el dato y el tipo se deriva de ella**, no al revés. Un `type`
 * escrito a mano no se puede recorrer en ejecución, así que todo test que
 * quisiera cubrir "la clase entera" acababa enumerando ejemplos — y quedándose
 * ciego ante el siguiente miembro, que es exactamente lo que pasó con `assumed`.
 * Invertida, no hay forma de añadir un estado al tipo sin añadirlo al array que
 * los tests recorren.
 *
 * Salvo `assumed`, se deriva de las CIFRAS, no de `mute_rule`: la causa es otra
 * pregunta (`muteAckLine`) y mezclarlas permitiría que el titular se
 * contradijera con el acuse que lleva al lado.
 */
export const MUTE_OUTCOMES = ["all", "assumed", "partial", "none", "none_requested"] as const;

export type MuteOutcome = (typeof MUTE_OUTCOMES)[number];

/**
 * `mute_verified === false` gana ANTES que cualquier cifra, y no es un matiz.
 *
 * Cuando el `PutAlarmMuteRule` se emitió y el `GetAlarmMuteRule` que lo
 * comprueba no se pudo leer, el servidor rellena `silenced = requested` **a
 * propósito**: asume el estado peligroso —mudo— y guarda el nombre de la regla
 * para poder deshacerlo. O sea que el acuse a ciegas llega con la MISMA forma
 * que un éxito medido (`2/2`, `missing 0`, `mute_rule` con nombre). Clasificarlo
 * por las cifras lo pintaría como `all`, que es la afirmación más fuerte que
 * esta pantalla sabe hacer, sostenida por una medición que nunca ocurrió.
 *
 * Va primero también para las formas que hoy no se dan (`0/N` sin verificar): la
 * regla es "sin medición no hay cifra que clasificar", no "sin medición se
 * clasifica distinto".
 *
 * `undefined` NO es `false`: el campo es opcional en el SDK porque tiene default
 * en Pydantic, y el servidor lo emite siempre. Ausente solo puede venir de una
 * respuesta anterior a la migración 0031, y aquel servidor no tenía el camino
 * del acuse a ciegas — cuando la comprobación fallaba declaraba `0/N`. El punto
 * ciego está anclado con un test que lo declara.
 */
export function muteOutcome(w: MaintenanceWindowOut): MuteOutcome {
  if (w.mute_verified === false) return "assumed";
  if (w.requested <= 0) return "none_requested";
  if (w.silenced <= 0) return "none";
  if (w.silenced >= w.requested) return "all";
  return "partial";
}

/**
 * El TITULAR del banner. Dice lo que el servidor dice, no lo que se pretendía.
 *
 * Solo `all` lleva la afirmación «ALARMAS DE OPERACIÓN SILENCIADAS». Los otros
 * tres cargan el hecho peligroso —que alguien de guardia va a seguir recibiendo
 * correos que cree haber callado— porque la suposición por defecto de quien lee
 * «VENTANA DE MANTENIMIENTO» es justo la contraria.
 */
export function muteHeadline(w: MaintenanceWindowOut): string {
  switch (muteOutcome(w)) {
    case "all":
      return "ALARMAS DE OPERACIÓN SILENCIADAS";
    case "assumed":
      // Ni «silenciadas» ni «siguen sonando»: las dos serían afirmaciones y no
      // se midió ninguna. Lo accionable es que este es el único estado en el que
      // REABRIR VIGILANCIA hace falta de verdad — la regla existe, nadie sabe
      // sobre qué, y hasta que venza (4 h como mucho) el edificio puede estar
      // sin vigilar sin que nadie lo note.
      return "SILENCIO SUPUESTO · EL ACUSE NO SE PUDO LEER";
    case "partial":
      return "PARTE DE LAS ALARMAS DE OPERACIÓN SIGUE SONANDO";
    case "none":
      return "LAS ALARMAS DE OPERACIÓN SIGUEN SONANDO";
    case "none_requested":
      return "SIN ALARMAS DE OPERACIÓN QUE SILENCIAR";
  }
}

/**
 * `N/M ALARMAS SILENCIADAS` + POR QUÉ el resto no quedó mudo.
 *
 * `PutAlarmMuteRule` devolviendo 200 no es "silenciado", y el servidor rellena
 * `missing_names` en tres casos incompatibles:
 *
 *   (a) el silenciador está apagado (`ops_muting_enabled=False` ⇒ `client is
 *       None`) — **el default que va a producción**,
 *   (b) cualquier excepción de CloudWatch,
 *   (c) la alarma no existe (prefijo de env distinto, `iot_thing` NULL,
 *       gabinete fuera de `paged_gateways`) o la regla releída no la guardó.
 *
 * Un solo rótulo para los tres es el defecto de T-2.68: manda al operador a
 * buscar un problema de inventario cuando lo que tiene es un servidor que ni
 * llamó a CloudWatch. **`mute_rule` los separa**: en (a) y (b) el servidor
 * devuelve `rule_name=None` porque no llegó a emitir regla; en (c) la regla
 * existe y se releyó. (a) vs (b) NO se distinguen con el contrato actual, así
 * que se nombran las dos y ninguna se disfraza de la otra.
 */
export function muteAckLine(w: MaintenanceWindowOut): string {
  if (muteOutcome(w) === "assumed") {
    // `N/M ALARMAS SILENCIADAS` es el molde de lo MEDIDO. Aquí ese número lo
    // escribió el servidor asumiendo lo peor, no leyéndolo de CloudWatch:
    // reusar el molde —aunque fuera con un asterisco al lado— convertiría la
    // suposición en cifra, y las cifras se creen. Se dice lo único que consta:
    // cuántas se PIDIERON.
    return `${w.requested} ALARMAS PEDIDAS · SIN ACUSE: SE SUPONEN MUDAS, NADIE LO MIDIÓ`;
  }
  if (w.requested === 0) {
    // `0/0 SILENCIADAS` se leería como "todo en orden". No lo es ni deja de
    // serlo: sencillamente no había nada que callar, y eso se dice con palabras.
    return "SIN ALARMA QUE SILENCIAR";
  }
  const parts = [`${w.silenced}/${w.requested} ALARMAS SILENCIADAS`];
  const missing = w.missing ?? w.requested - w.silenced;
  if (missing > 0) {
    const causa =
      w.mute_rule === null
        ? "SILENCIADOR APAGADO O CON FALLO"
        : "NO EXISTEN O LA REGLA NO LAS GUARDÓ";
    parts.push(`${missing} SIN SILENCIAR: ${causa}`);
  }
  return parts.join(" · ");
}

/**
 * Hora de cierre en HH:MM UTC.
 *
 * Sin segundos a propósito, y no es cosmética: `starts_at` cae siempre en un
 * minuto exacto (`at()` de AWS tiene granularidad de minuto) y la duración es
 * múltiplo de 60 s, así que el segundo es SIEMPRE `:00`. Pintarlo sugeriría una
 * precisión que el mecanismo no tiene.
 */
export function endClock(w: MaintenanceWindowOut): string {
  return utcClock(Date.parse(w.ends_at)).slice(0, 5);
}

/**
 * Rótulo ADITIVO de la tarjeta: la hora de CIERRE, que es lo accionable.
 *
 * Y, cuando NO todas quedaron mudas, el desmentido pegado al rótulo. «EN
 * MANTENIMIENTO» a secas se lee como «sus alarmas están calladas» — es la
 * suposición por defecto de quien barre la flota, y nadie va a abrir el banner
 * para comprobarla. Si es falsa hay que romperla ahí mismo. Cuando sí lo están,
 * el rótulo se queda corto a propósito: la afirmación cierta no necesita
 * adorno, y el detalle vive en el `title` y en el banner.
 */
export function maintenanceLabel(w: MaintenanceWindowOut): string {
  const base = `EN MANTENIMIENTO HASTA ${endClock(w)} UTC`;
  switch (muteOutcome(w)) {
    case "all":
      return base;
    case "assumed":
      // El rótulo corto de `all` se reserva para la afirmación CIERTA. Aquí no
      // hay afirmación que reservar: quien barre la flota tiene que ver la duda
      // sin abrir el banner, igual que ve el silencio a medias.
      return `${base} · SILENCIO SIN COMPROBAR`;
    case "partial":
      return `${base} · SILENCIADAS EN PARTE`;
    case "none":
      return `${base} · ALARMAS SIN SILENCIAR`;
    case "none_requested":
      return `${base} · SIN ALARMA QUE SILENCIAR`;
  }
}

/**
 * La ventana que tapa a ESTE gabinete ahora mismo, o `null`.
 *
 * Se vuelve a comprobar el vencimiento contra el reloj local aunque el servidor
 * ya derive `active`: es un doble candado barato contra una respuesta vieja
 * atrapada en caché. Los dos candados fallan hacia "no hay ventana", que es el
 * lado que hace que las alarmas se anuncien de más, nunca de menos.
 *
 * Las ventanas de PLATAFORMA quedan fuera a propósito: silencian `ec2_*`, no las
 * alarmas del aparato. Pintarlas en una tarjeta de gabinete afirmaría que ESE
 * gabinete está sin vigilancia, y es falso.
 */
export function windowCovering(
  items: readonly MaintenanceWindowOut[],
  gatewayId: string,
  nowMs: number,
): MaintenanceWindowOut | null {
  for (const w of items) {
    if (w.scope !== "gateway" || w.gateway_id !== gatewayId) continue;
    if (w.closed_at !== null) continue;
    if (Date.parse(w.ends_at) <= nowMs) continue;
    return w;
  }
  return null;
}
