// T-2.79 · Aviso de privacidad SERVIDO (no horneado en la app) + consentimiento.
//
// Hasta ahora esta pantalla llevaba cuatro viñetas escritas a mano en el código
// y un pie que decía "EL AVISO COMPLETO LO SIRVE SU ORGANIZACIÓN". Eso es
// exactamente el agujero que T-2.79 cierra: la persona leía un resumen del
// repositorio de la app y no había forma de decir QUÉ texto aceptó ni cuándo.
// Ahora el texto viene del servidor —el de su organización si lo publicó, si no
// el de la plataforma— y lo que se registra es el DIGEST de ese texto.
//
// El estado (`missing`/`current`/`stale`/`withdrawn`) lo decide el SERVIDOR
// comparando digests. La app no lo recalcula: si lo hiciera habría dos verdades.
//
// Tipos a mano y `client.get`/`client.post` en crudo (en vez de las funciones
// generadas de `@takab/sdk`) por coordinación, no por diseño: el contrato se
// regenera al integrar y dos ramas regenerándolo a la vez chocan. **Al
// regenerar, sustituir por las funciones tipadas y borrar estas interfaces.**
// Se sigue usando el `client` del SDK, así que la app no duplica cliente HTTP
// (spec §13.5).
import { client } from "@takab/sdk";

export type ConsentState = "missing" | "current" | "stale" | "withdrawn";

export interface PrivacyNotice {
  purpose: string;
  locale: string;
  version: string;
  title: string;
  body: string;
  paragraphs: string[];
  digest: string;
  source: "repo" | "tenant";
  provisional: boolean;
  provisional_reason: string;
}

export interface ConsentStatus {
  notice: PrivacyNotice | null;
  state: ConsentState;
  consent: { notice_digest: string; notice_version: string; decided_at: string } | null;
  blocks_emergency_actions: false;
}

/** Estado del consentimiento del portador, o `null` si el servidor no contesta.
 *
 * `null` NO se disfraza de "sin aviso": quien llama distingue "no hay aviso"
 * (`notice === null`, un `empty` honesto) de "no se pudo preguntar" (`null`, un
 * `error`). Confundirlos pintaría "no tiene nada que aceptar" con la red caída.
 */
export async function fetchConsentStatus(): Promise<ConsentStatus | null> {
  const { data } = await client.get<ConsentStatus>({ url: "/privacy/consent" });
  return data ?? null;
}

/** Registra la decisión sobre el texto que se tenía EN PANTALLA.
 *
 * El `digest` viaja siempre: sin él, el servidor tendría que adivinar sobre qué
 * texto se decidió, y si el aviso cambió entre la lectura y el botón se estaría
 * firmando algo que nadie leyó. El servidor responde 409 en ese caso y aquí se
 * devuelve `false` — la pantalla vuelve a pedir el aviso.
 */
export async function decideConsent(
  decision: "accept" | "withdraw",
  digest: string,
): Promise<boolean> {
  const { response } = await client.post({
    url: "/privacy/consent",
    body: { decision, digest, via: "mobile" },
  });
  return response.status === 201;
}

/** ¿Hay que volver a pedir el consentimiento?
 *
 * Función PURA y separada del render a propósito: es la regla de producto de
 * esta tarea y tiene que poder probarse sin montar una pantalla. `current` es el
 * único estado que no pide nada.
 *
 * Y lo que esta función NO decide: si la persona puede usar la app. Un
 * `missing` o un `stale` **jamás** bloquean el check-in de vida, el botón de
 * ayuda ni la alerta (reglas de oro 1 y 2) — en un sismo, un brigadista que no
 * puede pasar lista por un trámite es un fallo de seguridad, no de cumplimiento.
 */
export function needsConsent(state: ConsentState): boolean {
  return state !== "current";
}
