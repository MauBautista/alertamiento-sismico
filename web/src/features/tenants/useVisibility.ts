import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listVisibilityGrantsVisibilityGrantsGet,
  revokeVisibilityGrantVisibilityGrantsGrantIdDelete,
  upsertVisibilityGrantVisibilityGrantsPost,
} from "@takab/sdk";
import type { VisibilityGrantCreate, VisibilityGrantOut } from "@takab/sdk";

class VisibilityRequestError extends Error {
  constructor(status: number) {
    super(`/visibility-grants falló (${status})`);
    this.name = "VisibilityRequestError";
  }
}

async function fetchGrants(grantee: string): Promise<VisibilityGrantOut[]> {
  const { data, response } = await listVisibilityGrantsVisibilityGrantsGet({
    query: { grantee_tenant_id: grantee },
  });
  if (data === undefined) {
    throw new VisibilityRequestError(response.status);
  }
  return data;
}

export interface VisibilityData {
  grants: VisibilityGrantOut[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Grants entrantes de un cliente (qué puede ver de otros). Solo superadmin llega aquí. */
export function useVisibilityGrants(grantee: string | null, enabled: boolean): VisibilityData {
  const q = useQuery({
    queryKey: ["visibility-grants", grantee],
    queryFn: () => fetchGrants(grantee as string),
    enabled: enabled && grantee !== null,
    staleTime: 30_000,
  });
  return {
    grants: q.data ?? [],
    loading: q.isPending && enabled && grantee !== null,
    error: q.error ? q.error.message : null,
    refetch: () => void q.refetch(),
  };
}

export interface VisibilityMutations {
  grant: (body: VisibilityGrantCreate) => void;
  revoke: (grantId: string) => void;
  pending: boolean;
  error: string | null;
}

export function useVisibilityMutations(grantee: string | null): VisibilityMutations {
  const qc = useQueryClient();
  const invalidate = (): void => {
    void qc.invalidateQueries({ queryKey: ["visibility-grants", grantee] });
  };
  const upsert = useMutation({
    mutationFn: async (body: VisibilityGrantCreate): Promise<VisibilityGrantOut> => {
      const { data, response } = await upsertVisibilityGrantVisibilityGrantsPost({ body });
      if (data === undefined) {
        throw new VisibilityRequestError(response.status);
      }
      return data;
    },
    onSuccess: invalidate,
  });
  const del = useMutation({
    // El revoke devuelve 204 (sin cuerpo): se valida por status, no por `data`.
    mutationFn: async (grantId: string): Promise<void> => {
      const { response } = await revokeVisibilityGrantVisibilityGrantsGrantIdDelete({
        path: { grant_id: grantId },
      });
      if (response.status >= 400) {
        throw new VisibilityRequestError(response.status);
      }
    },
    onSuccess: invalidate,
  });
  return {
    grant: (body) => upsert.mutate(body),
    revoke: (grantId) => del.mutate(grantId),
    pending: upsert.isPending || del.isPending,
    error: upsert.error?.message ?? del.error?.message ?? null,
  };
}
