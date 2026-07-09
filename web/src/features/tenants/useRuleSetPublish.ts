import { useMutation, useQueryClient } from "@tanstack/react-query";

import { publishRuleSetRuleSetsRuleSetIdPublishPost, putRuleSetRuleSetsPut } from "@takab/sdk";

class PublishError extends Error {
  constructor(
    resource: string,
    readonly status: number,
  ) {
    super(
      status === 409
        ? "El rule_set cambió en el servidor mientras editabas. Recarga y reintenta."
        : `${resource} falló (${status})`,
    );
    this.name = "PublishError";
  }
}

export interface PublishVars {
  tenantId: string;
  config: Record<string, unknown>;
  /** Versión activa sobre la que se construyó `config`; null si no había ninguna. */
  baseVersion: number | null;
}

export interface PublishState {
  apply: (vars: PublishVars) => void;
  pending: boolean;
  error: string | null;
  /** true cuando el servidor devolvió 409: alguien más publicó mientras editábamos. */
  conflict: boolean;
  /** Versión de `rule_sets` creada por el último PUT de ESTA sesión. */
  publishedVersion: number | null;
  reset: () => void;
}

/** El servidor rechaza el PUT con 409 si `base_version` no es la activa. */
const CONFLICT = 409;

/**
 * `PUT /rule-sets` (versión nueva, activa) + `POST /rule-sets/{id}/publish`.
 *
 * `publish` responde 202 `pending_sync`: NO sincroniza al edge — eso lo hace el
 * worker de T-1.23. Por eso este hook no afirma nada sobre el gabinete; sólo
 * invalida `config-state` para que el poll traiga la verdad.
 *
 * `PUT` NO escribe `audit_log` (sólo `publish` audita `rule_set_publish`): la UI
 * no debe prometer que cada guardado queda auditado.
 */
export function useRuleSetPublish(): PublishState {
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({ tenantId, config, baseVersion }: PublishVars) => {
      const put = await putRuleSetRuleSetsPut({
        body: {
          scope_type: "tenant",
          scope_id: tenantId,
          config,
          // Sin esto el PUT reemplaza el blob entero a ciegas y revierte en silencio
          // lo que otro haya cambiado (p. ej. `relays.siren`).
          base_version: baseVersion,
        },
      });
      if (put.data === undefined) {
        throw new PublishError("PUT /rule-sets", put.response.status);
      }
      const published = await publishRuleSetRuleSetsRuleSetIdPublishPost({
        path: { rule_set_id: put.data.rule_set_id },
      });
      if (published.data === undefined) {
        throw new PublishError("POST /rule-sets/{id}/publish", published.response.status);
      }
      return published.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["rule-sets"] });
      void qc.invalidateQueries({ queryKey: ["config-state"] });
    },
    onError: () => {
      // Un 409 significa que nuestra copia está vieja: hay que traer la del servidor.
      void qc.invalidateQueries({ queryKey: ["rule-sets"] });
    },
  });

  const status = mutation.error instanceof PublishError ? mutation.error.status : null;

  return {
    apply: (vars) => mutation.mutate(vars),
    pending: mutation.isPending,
    error: mutation.error?.message ?? null,
    conflict: status === CONFLICT,
    publishedVersion: mutation.data?.version ?? null,
    reset: () => mutation.reset(),
  };
}
