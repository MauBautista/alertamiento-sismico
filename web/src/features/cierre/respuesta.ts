// [T-9.41] Leer una respuesta del cliente hey-api SIN suponer la rama.
//
// El cliente no lanza con un 4xx/5xx: devuelve `{ data, error, response }`. Lo
// que sigue es el mismo criterio de `console/useIncidentAck.ts`: una respuesta
// sin `data`, con `error` o con status ≥ 400 NO consta como hecha.

/** El `detail` textual de un error de FastAPI, si lo trae. */
export function detailOf(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() !== "" ? detail : null;
}

export interface Respuesta<T> {
  data?: T;
  error?: unknown;
  response?: { status: number } | Response;
}

/** `{ ok, data }` o `{ status, detail }` del fallo. */
export function leer<T>(
  res: Respuesta<T>,
): { ok: true; data: T } | { ok: false; status: number | null; detail: string | null } {
  const status = res.response?.status ?? null;
  const error = "error" in res ? res.error : undefined;
  if (error !== undefined || res.data === undefined || status === null || status >= 400) {
    return { ok: false, status, detail: detailOf(error) };
  }
  return { ok: true, data: res.data };
}
