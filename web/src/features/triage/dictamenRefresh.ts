// [T-7.05 · C-3] CUÁNDO SE VUELVE A PREGUNTAR POR EL DICTAMEN, y cuándo se deja.
//
// MEDIDO (censo de T-7.04 §5, flujo F1b, 2026-09-12): el inspector abre la fila
// a los 3 s de `opened_at` —lo normal: la abre en cuanto la ve—, el worker
// inserta el dictamen preliminar a los 61 s (`dictamen_settle_s` = 60) y a los
// 81 s la cabecera seguía diciendo «SIN DICTAMEN», el marco DICTAMEN «SIN
// CLASIFICAR» y FIRMAR sin aparecer. El rodeo para verlo eran DOS clics —cambiar
// de fila y volver— que nadie le había enseñado al operador. Es la pantalla
// donde se FIRMA: un dato congelado presentado como vivo (regla de oro 7).
//
// POR QUÉ UNA FUNCIÓN Y NO UN NÚMERO EN EL HOOK. La causa era una ausencia
// (`useIncidentDetail.ts` no declaraba `refetchInterval`) y una ausencia no se
// puede probar: no hay nada a lo que preguntarle. Sacando la decisión aquí, el
// «cuándo» es un valor con tests y la próxima vez que alguien la cambie tiene
// que decir por qué.
//
// DOS MECANISMOS, Y NO SOBRA NINGUNO (ver `useIncidentDetail.ts`):
//
//  1. EL FRAME DEL CANAL LIVE es el bueno y llega en menos de un segundo. La
//     pasada de dictamen INSERTA en `incident_actions` (kind `dictamen`,
//     `dictamen/service.py`), el trigger `trg_incident_actions_notify` de la
//     migración 0004 lanza el NOTIFY y el hub lo reparte como `incident_action`
//     por el topic `incidents`. No hay que sondear para enterarse.
//  2. ESTE INTERVALO ES EL SUELO, no el mecanismo principal. `useLiveSocket()`
//     devuelve `null` cuando la consola corre solo-REST —degradación prevista y
//     querida (regla de oro 2)— y el hub sabe declarar un topic degradado sin
//     cerrar el socket (T-2.129). Colgar de un canal que tiene permiso para
//     estar caído el único criterio medible de esta ficha sería fiar el «≤10 s»
//     a algo que nadie garantiza.
//
// LO QUE EL SUELO NO CUBRE, DICHO AQUÍ Y NO DESCUBIERTO EN CAMPO: react-query
// sólo dispara el tick del intervalo si la ventana tiene el foco
// (`refetchIntervalInBackground || focusManager.isFocused()`, query-core 5.101)
// y `lib/queryClient.ts` además apaga `refetchOnWindowFocus` porque esto es un
// videowall. O sea: en una pestaña de fondo el suelo NO corre, y al volver el
// foco tarda hasta un periodo. Se deja así a propósito —el criterio C-3 se mide
// con el inspector delante de la pantalla, y un videowall no pierde el foco—,
// pero no se presenta como lo que no es: el que necesite refresco sin foco tiene
// que pedir `refetchIntervalInBackground` y decir por qué.
//
// ────────────────────────────────────────────────────────────────────────────
// EL SONDEO SIEMPRE TERMINA, Y SE PUEDE DEMOSTRAR (revisión adversaria f0r2).
//
// La primera versión de este módulo tenía DOS ramas que devolvían intervalo sin
// ventana ninguna: «no me pasaron la fila» y «la fecha de apertura no se puede
// leer». Un temporizador sin condición de parada sobre DOS endpoints es
// exactamente el defecto que vinimos a arreglar, aunque hoy ningún llamador
// tome esas ramas: el que llegue mañana las toma por omisión y nada se pone
// rojo. Aquí no se documentan, se ELIMINAN.
//
// La invariante que queda —y que `dictamenRefresh.test.ts` comprueba barriendo
// TODAS las formas de entrada— es: para cualquier entrada, con el reloj lo
// bastante adelantado la función devuelve `false`. O sea: todo sondeo que esta
// función autoriza tiene una hora de caducidad calculable.
//
// El precio, dicho en voz alta: un llamador que NO conozca la fila del
// incidente se queda sin el suelo de 5 s y depende del canal live. Es el precio
// correcto —ese llamador tampoco puede decir cuándo parar—, y la respuesta no
// es sondear para siempre sino pasarle la fila; por eso el tercer argumento de
// `useIncidentDetail` es OBLIGATORIO y no tiene valor por defecto.

/**
 * Cadencia del sondeo mientras la pasada automática todavía puede escribir.
 *
 * El criterio medible de C-3 es «el rótulo cambia dentro de los 10 s siguientes
 * a la emisión». El periodo tiene que caber en ese presupuesto CON la petición
 * dentro, así que no puede acercarse a los 10 s; y es la única consulta de la
 * pantalla que corre así de rápido, durante una ventana acotada y sobre un
 * endpoint que devuelve la cadena de un solo incidente.
 */
export const DICTAMEN_REFETCH_MS = 5_000;

/**
 * Cuánto tiempo desde `opened_at` puede la pasada automática seguir escribiendo.
 *
 * DERIVADA DEL WORKER QUE DE VERDAD CORRE, no del parámetro que se lee mejor.
 * `run_dictamen_pass` (api · `dictamen/service.py`) sólo mira incidentes con
 * `opened_at BETWEEN now - lookback_s AND now - settle_s`, pero su
 * `lookback_s: float = 300.0` es un DEFAULT MUERTO: `incident/engine.py` siempre
 * le pasa `lookback_s=self._lookback_s`, que viene del `--lookback` de
 * `incident/__main__.py` (default 300.0) — y ni `deploy/cloud/docker-compose.yml`
 * (`command: []`) ni `demo/soc_local.sh` pasan el flag. `dictamenRefresh.test.ts`
 * lee las TRES declaraciones y además los arrancadores, y exige que este número
 * cubra a la mayor: ensanchar la ventana del worker en cualquiera de esos sitios
 * pone rojo este fichero.
 *
 * Pasada esa ventana, la pasada automática YA NO PUEDE emitir para ese
 * incidente: seguir sondeando no es prudencia, es un temporizador que no puede
 * traer nada. Se toma el DOBLE del lookback para absorber un worker con retraso
 * o un reinicio con cola.
 *
 * Lo que llegue MÁS TARDE que esto —el dictamen de un worker atascado horas—
 * sigue llegando por el frame del canal live, que no tiene ventana.
 */
export const DICTAMEN_WATCH_MS = 600_000;

/**
 * Lo que la pantalla sabe de la FILA del incidente abierto en el detalle.
 *
 * SÓLO `openedAt`, y no es un olvido: es el ancla de la ventana del worker y no
 * hay ningún otro campo del incidente que gobierne si la pasada automática
 * puede escribir. En particular NO lleva `state` — ver `dictamenRefetchMs`.
 */
export interface IncidentRefreshHint {
  /** `incidents.opened_at`, ISO-8601. Ancla de la ventana. */
  openedAt: string;
}

/** Lo único que de una fila de la cadena decide si el worker ya no la toca. */
export interface DictamenChainRow {
  /** `dictamens.signed_by`; `null` = preliminar automático. */
  signed_by: string | null;
}

export interface DictamenRefreshInput {
  /** Incidente seleccionado; `null` = la consulta ni siquiera está habilitada. */
  incidentId: string | null;
  /** La fila; `null` cuando el llamador no la conoce (⇒ sin ventana, sin suelo). */
  incident: IncidentRefreshHint | null;
  /**
   * La cadena YA respondida. `undefined` = la consulta no ha traído nada
   * todavía, que NO es lo mismo que «no hay dictamen».
   */
  dictamens: readonly DictamenChainRow[] | undefined;
  /** Epoch ms. Entra como dato para que la decisión sea pura. */
  now: number;
}

/**
 * El valor que `refetchInterval` espera: ms entre sondeos, o `false` = ninguno.
 *
 * Se sondea mientras la PASADA AUTOMÁTICA pueda todavía escribir en esta cadena,
 * y sólo entonces. Sus tres condiciones, copiadas del worker:
 *
 *  · HAY INCIDENTE. Sin él la consulta está `enabled:false` y un intervalo sería
 *    un temporizador sobre nada.
 *  · HAY ANCLA LEGIBLE. La ventana se mide desde `opened_at`; sin fila, o con
 *    una fecha que no parsea, no hay ventana que calcular y por tanto tampoco
 *    hora de parada. Ver la cabecera del módulo: se prefiere quedarse sin suelo
 *    a montar un temporizador perpetuo.
 *  · LA CABEZA NO ESTÁ FIRMADA. Ésta es la condición de parada del propio
 *    worker: `run_dictamen_pass` hace `if row["head_signed_by"] is not None:
 *    continue` («el juicio del inspector manda»). Mientras la cabeza siga SIN
 *    firmar puede llegar una CORRECCIÓN —fila nueva con `supersedes_dictamen_id`
 *    cuando el status recalculado difiere, el caso «el quórum corroboró después
 *    del preliminar» del docstring de `dictamen/service.py`—, así que parar con
 *    la PRIMERA fila dejaba la pantalla vieja justo en el caso que más importa:
 *    el inspector a punto de firmar un veredicto ya superado. Basta con que
 *    ALGUNA fila esté firmada: `POST /incidents/{id}/dictamens` inserta siempre
 *    con `signed_by` (routers/dictamens.py), de modo que una cadena con firma
 *    tiene la cabeza firmada y el worker no vuelve a tocarla.
 *
 * Y NO MIRA `state`. Parecía prudente parar con el incidente cerrado, pero el
 * worker no comparte esa idea: el `_CANDIDATES_SQL` del dictamen filtra SÓLO por
 * `opened_at` (la correlación de `incident/engine.py` sí lleva `AND i.state <>
 * 'closed'` — la diferencia es deliberada, no un descuido). Un incidente cerrado
 * dentro de la ventana todavía recibe su preliminar o su corrección, y apagar
 * ahí el refresco reintroducía el defecto de C-3 por la puerta de atrás.
 */
export function dictamenRefetchMs(input: DictamenRefreshInput): number | false {
  const { incidentId, incident, dictamens, now } = input;
  if (incidentId === null || incident === null) {
    return false;
  }
  if (dictamens !== undefined && dictamens.some((d) => d.signed_by !== null)) {
    return false;
  }
  const openedAt = Date.parse(incident.openedAt);
  if (Number.isNaN(openedAt)) {
    return false;
  }
  return now - openedAt > DICTAMEN_WATCH_MS ? false : DICTAMEN_REFETCH_MS;
}
