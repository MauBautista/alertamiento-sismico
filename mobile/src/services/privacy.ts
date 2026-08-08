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

/** El servidor no pudo decir en qué estado está el consentimiento.
 *
 * Es un desenlace DISTINTO de "no hay aviso publicado", y por eso es una
 * excepción y no un `null`: un `null` se colaba hasta la pantalla y se pintaba
 * como "su organización no tiene aviso" — una ausencia AFIRMADA sin haberla
 * comprobado (regla de oro 7).
 */
export class ConsentUnavailableError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`no se pudo consultar el aviso de privacidad (HTTP ${status || "sin respuesta"})`);
    this.name = "ConsentUnavailableError";
    this.status = status;
  }
}

function esExitosa(status: number): boolean {
  return status >= 200 && status < 300;
}

/** Estado del consentimiento del portador.
 *
 * LANZA `ConsentUnavailableError` si el servidor no lo pudo decir. El cliente
 * del SDK NO lanza en errores HTTP (solo con `throwOnError`, que la app no
 * activa: `services/sdk.ts`), así que un 500 llegaba aquí como `data:
 * undefined` y salía como `null` indistinguible de "no hay aviso". Quien llama
 * tiene que poder separar "no hay aviso" (200 con `notice: null`, un `empty`
 * honesto) de "no se pudo preguntar" (esta excepción, un `error`).
 */
export async function fetchConsentStatus(): Promise<ConsentStatus> {
  const { data, response } = await client.get<ConsentStatus>({ url: "/privacy/consent" });
  const status = response?.status ?? 0;
  if (!esExitosa(status) || data === undefined || data === null) {
    throw new ConsentUnavailableError(status);
  }
  return data;
}

/** Desenlace de registrar la decisión. NUNCA un booleano.
 *
 * `false` valía igual para un 409 (el aviso cambió bajo el lector) que para un
 * 503 (la nube no escribe) que para un 403, y quien llamaba los trataba a los
 * tres como "no puedes pasar". Eso dejaba al ocupante encerrado en el
 * onboarding —sin check-in de vida ni botón de pánico— con la nube medio
 * caída. Son tres cosas distintas y solo una habla del consentimiento.
 *
 * - `recorded`: 201, quedó registrado con su digest.
 * - `superseded`: 409, el aviso cambió entre la lectura y el botón; no se
 *   registró nada, y el servidor seguirá diciendo `missing`/`stale` — se
 *   vuelve a pedir desde Cuenta, que es un sitio que no bloquea.
 * - `unrecorded`: no se pudo registrar (red, 5xx, 4xx). Igual que arriba: el
 *   servidor conserva la verdad y la app volverá a preguntar.
 *
 * El cuarto desenlace posible del flujo —que la persona **no haya decidido**—
 * no cabe aquí: es el estado previo a pulsar, y es el ÚNICO que legítimamente
 * retiene a alguien en la pantalla.
 */
export type ConsentOutcome = "recorded" | "superseded" | "unrecorded";

/** Registra la decisión sobre el texto que se tenía EN PANTALLA.
 *
 * El `digest` viaja siempre: sin él, el servidor tendría que adivinar sobre qué
 * texto se decidió, y si el aviso cambió entre la lectura y el botón se estaría
 * firmando algo que nadie leyó (el servidor responde 409 en ese caso).
 *
 * Es una función TOTAL: no lanza ni siquiera con la red caída. Si lo hiciera,
 * cualquier `await decideConsent(...)` sin `try` sería otro cerrojo posible
 * sobre el camino al check-in de vida.
 */
export async function decideConsent(
  decision: "accept" | "withdraw",
  digest: string,
): Promise<ConsentOutcome> {
  try {
    const { response } = await client.post({
      url: "/privacy/consent",
      body: { decision, digest, via: "mobile" },
    });
    const status = response?.status ?? 0;
    if (status === 201) {
      return "recorded";
    }
    return status === 409 ? "superseded" : "unrecorded";
  } catch {
    // `fetch` rechazado: sin red no hay registro, y no hay nada que decidir.
    return "unrecorded";
  }
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
