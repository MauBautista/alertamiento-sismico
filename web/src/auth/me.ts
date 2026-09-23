import { meMeGet } from "@takab/sdk";
import type { MeActions, MeResponse } from "@takab/sdk";

import { isSessionExpiredBody, isSessionExpiredHeader } from "./sessionLimit";

export type { MeActions, MeResponse };

/** Error HTTP de GET /me; el store decide (401 ⇒ sesión fuera, resto ⇒ error). */
export class MeRequestError extends Error {
  constructor(
    public readonly status: number,
    /**
     * [T-8.03] El 401 es el del TOPE de sesión (D-38: `sesion_expirada`), no un
     * token vencido. El store lo trata al revés que al otro: NO renueva, porque
     * Cognito seguiría refrescando y la API rechazaría en bucle.
     */
    public readonly sessionExpired = false,
  ) {
    super(`GET /me falló (${status})`);
    this.name = "MeRequestError";
  }
}

/** Identidad + allowed_routes/allowed_actions del rol — la fuente de los guards. */
export async function getMe(): Promise<MeResponse> {
  const { data, error, response } = await meMeGet();
  if (data === undefined) {
    const expired =
      response.status === 401 &&
      (isSessionExpiredHeader(response.headers.get("WWW-Authenticate")) ||
        isSessionExpiredBody(error));
    throw new MeRequestError(response.status, expired);
  }
  return data;
}
