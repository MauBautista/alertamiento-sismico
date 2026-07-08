import { meMeGet } from "@takab/sdk";
import type { MeActions, MeResponse } from "@takab/sdk";

export type { MeActions, MeResponse };

/** Error HTTP de GET /me; el store decide (401 ⇒ sesión fuera, resto ⇒ error). */
export class MeRequestError extends Error {
  constructor(public readonly status: number) {
    super(`GET /me falló (${status})`);
    this.name = "MeRequestError";
  }
}

/** Identidad + allowed_routes/allowed_actions del rol — la fuente de los guards. */
export async function getMe(): Promise<MeResponse> {
  const { data, response } = await meMeGet();
  if (data === undefined) {
    throw new MeRequestError(response.status);
  }
  return data;
}
