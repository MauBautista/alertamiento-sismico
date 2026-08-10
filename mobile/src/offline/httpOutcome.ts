// Clasificación de un fallo HTTP para la cola offline: ¿vuelve a intentarse o
// queda visible como fallido? Vive en su propio módulo (y no dentro de
// `sync.ts`) porque los emisores —`services/evidence.ts`, por ejemplo— la
// necesitan y `sync.ts` los importa a ellos: al revés habría ciclo.
export type SendOutcome =
  | { ok: true; serverId?: string | null }
  | { ok: false; retryable: boolean; error: string };

/** 401 se reintenta (la sesión puede recuperarse); 4xx de contrato NO. */
export function isRetryableStatus(status: number): boolean {
  if (status === 401 || status === 408 || status === 429) {
    return true;
  }
  return status === 0 || status >= 500;
}
