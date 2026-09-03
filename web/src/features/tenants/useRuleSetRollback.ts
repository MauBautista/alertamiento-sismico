// Volver a una versión anterior del rule_set (T-5.16).
//
// El servidor NO reescribe el histórico: crea una versión nueva que declara a
// cuál vuelve. Este hook es la otra mitad, y no inventa nada sobre el gabinete —
// como el publish, la sincronización la hace el worker y la verdad la trae el
// poll de `config-state`.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { rollbackRuleSetRuleSetsRuleSetIdRollbackPost } from "@takab/sdk";

/** El servidor rechaza con 409 si `base_version` ya no es la activa. */
const CONFLICT = 409;

export interface RollbackVars {
  /** La versión DESTINO: a cuál se vuelve. */
  ruleSetId: string;
  /** La versión ACTIVA que el operador tenía delante al pulsar. */
  baseVersion: number;
}

export interface RollbackState {
  volver: (vars: RollbackVars) => void;
  /** `rule_set_id` en vuelo, o `null`: solo ESE botón se deshabilita. */
  pendingId: string | null;
  error: string | null;
  conflict: boolean;
}

export function useRuleSetRollback(): RollbackState {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (vars: RollbackVars) => {
      const { data, response } = await rollbackRuleSetRuleSetsRuleSetIdRollbackPost({
        path: { rule_set_id: vars.ruleSetId },
        body: { base_version: vars.baseVersion },
      });
      if (data === undefined) {
        const err = new Error(
          response.status === CONFLICT
            ? "El rule_set cambió en el servidor mientras mirabas. Recarga y reintenta."
            : `POST /rule-sets/${vars.ruleSetId}/rollback falló (${response.status})`,
        );
        Object.assign(err, { status: response.status });
        throw err;
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["rule-sets"] });
      // El gabinete todavía NO tiene esto: lo trae el worker de sync. Se
      // invalida el estado de config para que el poll diga la verdad en vez de
      // que la pantalla la suponga.
      void qc.invalidateQueries({ queryKey: ["config-state"] });
    },
  });

  const status = (mutation.error as { status?: number } | null)?.status;
  return {
    volver: (vars) => mutation.mutate(vars),
    pendingId: mutation.isPending ? mutation.variables.ruleSetId : null,
    error: mutation.error ? mutation.error.message : null,
    conflict: status === CONFLICT,
  };
}
