import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@takab/sdk";
import type { ConsentOut, ConsentStatusOut, NoticeOut } from "@takab/sdk";

/**
 * T-2.79 · Estado del consentimiento del operador sobre el aviso VIGENTE.
 *
 * El estado (`missing`/`current`/`stale`/`withdrawn`) lo decide el SERVIDOR
 * comparando digests, y este hook no lo recalcula. Si lo hiciera habría dos
 * verdades y la del cliente mentiría en cuanto el aviso cambiara entre dos
 * peticiones — que es justo el modo de fallo que la tarea existe para cerrar.
 *
 * [T-2.82.b] Las interfaces a mano se fueron: `ConsentStatusOut`, `NoticeOut` y
 * `ConsentOut` ya viajan en `@takab/sdk`. Los nombres locales quedan como ALIAS
 * porque el banner los importa por ese nombre — un alias no es una segunda
 * verdad, es un nombre para la única que hay.
 *
 * Se conserva `client.get`/`client.post` en crudo y NO las funciones generadas:
 * `PrivacyConsentBanner.test.tsx` sustituye `@takab/sdk` entero con `vi.mock`
 * sin `importOriginal`, así que una función generada llegaría `undefined` y el
 * fichero de test moriría entero. Los tipos entran por `import type`, que se
 * borra al compilar y no crea arista en tiempo de ejecución.
 */

/** Umbral de dato viejo. Alto a propósito: el aviso cambia con un despliegue o
 * con un acto administrativo, no cada minuto. */
export const CONSENT_STALE_MS = 900_000;
export const CONSENT_REFETCH_MS = 300_000;

/** Los cuatro estados, DERIVADOS del contrato: no se reescriben aquí. */
export type ConsentState = ConsentStatusOut["state"];

/**
 * [T-2.82.b] DISCREPANCIA REAL, anotada y no silenciada.
 *
 * El tipo a mano declaraba `notice_id`, `effective_at` y `provisional_reason`
 * como SIEMPRE presentes y `purpose` como un `string` cualquiera. El contrato
 * publicado dice otra cosa: los tres primeros son opcionales (`?:`) y `purpose`
 * es la unión `'privacy_notice' | 'whatsapp_alerts'`.
 *
 * Es la misma familia que el `provenance` que cuenta la ficha: son campos CON
 * DEFAULT, y un campo con default no sale `required` en el esquema de
 * serialización salvo que el modelo lleve `json_schema_serialization_defaults_required`.
 * `ComplianceDocOut`, `ConsentStatusOut` y `ForensicsOut` ya lo llevan; `NoticeOut`
 * **no**. Manda el contrato —es la única verdad publicada— y ningún consumidor
 * se rompe: el único que lee uno de esos campos es el banner, y lo pasa a un
 * `title` de HTML, que admite `undefined` sin fingir nada. No se ha puesto ni un
 * `!` ni un cast. Lo que queda por decidir está fuera de esta consola: si el
 * servidor los manda siempre, quien falta por corregir es `NoticeOut` en la API.
 */
export type PrivacyNotice = NoticeOut;

export type PrivacyConsent = ConsentOut;

export type ConsentStatus = ConsentStatusOut;

/**
 * Fallo de TRANSPORTE, y solo eso.
 *
 * Tenía una rama `status === 404` que devolvía "esta organización no tiene aviso
 * de privacidad publicado". Era doblemente falsa: `GET /privacy/consent`
 * responde **200 con `notice: null`** cuando no hay aviso —el estado `empty` sale
 * de ahí, no de un 404 (`api/src/takab_api/routers/privacy.py`)—, así que la rama
 * no se alcanzaba nunca; y el día que se alcanzara sería por un prefijo mal
 * montado, un proxy o un gateway, y le contaría al operador una historia sobre su
 * organización que la API jamás dijo. Un fallo de infraestructura se cuenta como
 * lo que es.
 */
class ConsentRequestError extends Error {
  constructor(status: number) {
    super(`GET /privacy/consent falló (${status})`);
    this.name = "ConsentRequestError";
  }
}

export interface PrivacyConsentData {
  status: ConsentStatus | null;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  /** El POST en vuelo: el botón tiene que poder decir que está trabajando. */
  deciding: boolean;
  decideError: string | null;
  decide: (decision: "accept" | "withdraw") => void;
  // SIN `refetch`. Se exponía y no lo llamaba nadie: el único consumidor es el
  // banner, y el banner quitó su botón REINTENTAR a propósito (vive en el shell,
  // encima de todas las pantallas, y competiría con el REINTENTAR de la pantalla
  // de debajo — lo cazó `BuildingPage.test.tsx`). Una API pública que nadie usa
  // invita a cablear justo el botón que se decidió no tener. La recuperación va
  // por `refetchInterval` y, a mano, por el POST de `decide`, que invalida la
  // consulta al registrar.
}

export function usePrivacyConsent(): PrivacyConsentData {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["privacy-consent"],
    queryFn: async (): Promise<ConsentStatus> => {
      const { data, response } = await client.get<ConsentStatus>({ url: "/privacy/consent" });
      if (data === undefined) {
        throw new ConsentRequestError(response.status);
      }
      return data;
    },
    refetchInterval: CONSENT_REFETCH_MS,
  });

  const mutation = useMutation({
    mutationFn: async (decision: "accept" | "withdraw") => {
      const digest = query.data?.notice?.digest;
      if (!digest) {
        // Sin digest no se firma nada. Mandar el POST "a ver si suena" sería
        // pedirle al servidor que decida qué texto se aceptó, que es justo lo
        // que no puede hacer.
        throw new Error("no hay aviso vigente que aceptar");
      }
      const { data, response } = await client.post<PrivacyConsent>({
        url: "/privacy/consent",
        body: { decision, digest, via: "web" },
      });
      if (data === undefined) {
        throw new Error(
          response.status === 409
            ? "el aviso cambió mientras estaba en pantalla: vuelve a leerlo"
            : `POST /privacy/consent falló (${response.status})`,
        );
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["privacy-consent"] });
    },
  });

  return {
    status: query.data ?? null,
    loading: query.isPending,
    // Con dato ya cargado manda el stale sobre el error: el consentimiento de
    // ayer sigue siendo cierto, solo dejó de estar al día.
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    deciding: mutation.isPending,
    decideError: mutation.error ? mutation.error.message : null,
    decide: (decision) => mutation.mutate(decision),
  };
}
