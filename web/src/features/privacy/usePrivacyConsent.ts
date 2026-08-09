import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@takab/sdk";

/**
 * T-2.79 · Estado del consentimiento del operador sobre el aviso VIGENTE.
 *
 * El estado (`missing`/`current`/`stale`/`withdrawn`) lo decide el SERVIDOR
 * comparando digests, y este hook no lo recalcula. Si lo hiciera habría dos
 * verdades y la del cliente mentiría en cuanto el aviso cambiara entre dos
 * peticiones — que es justo el modo de fallo que la tarea existe para cerrar.
 *
 * Tipos a mano y `client.get` en crudo (y no una función generada del SDK) por
 * una razón de coordinación, no de diseño: el contrato se regenera al integrar
 * y dos ramas regenerándolo a la vez chocan seguro. **Al regenerar, sustituir
 * por las funciones tipadas de `@takab/sdk`** y borrar estas interfaces.
 */

/** Umbral de dato viejo. Alto a propósito: el aviso cambia con un despliegue o
 * con un acto administrativo, no cada minuto. */
export const CONSENT_STALE_MS = 900_000;
export const CONSENT_REFETCH_MS = 300_000;

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
  notice_id: string | null;
  effective_at: string | null;
  provisional: boolean;
  provisional_reason: string;
}

export interface PrivacyConsent {
  consent_id: string;
  decision: "accept" | "withdraw";
  notice_source: "repo" | "tenant";
  notice_id: string | null;
  notice_digest: string;
  notice_version: string;
  notice_locale: string;
  via: string;
  actor_sub: string;
  decided_at: string;
}

export interface ConsentStatus {
  notice: PrivacyNotice | null;
  state: ConsentState;
  consent: PrivacyConsent | null;
  blocks_emergency_actions: false;
}

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
