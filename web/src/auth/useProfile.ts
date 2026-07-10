// Perfil de presentación del operador (T-1.49): nombre editable sobre
// /me/profile. Separado de /me (claims puros): el nombre es presentación, no
// identidad. Cacheado por TanStack Query — Topbar, OperatorMenu y el pie de
// la consola comparten la misma clave.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getProfileMeProfileGet, putProfileMeProfilePut, type ProfileOut } from "@takab/sdk";

import { useSessionStore } from "./session.store";

export const PROFILE_QUERY_KEY = ["me", "profile"] as const;

export function useProfile() {
  const authenticated = useSessionStore((s) => s.status === "authenticated");
  return useQuery({
    queryKey: PROFILE_QUERY_KEY,
    enabled: authenticated,
    staleTime: 300_000,
    queryFn: async (): Promise<ProfileOut> => {
      const res = await getProfileMeProfileGet({ throwOnError: true });
      return res.data;
    },
  });
}

export function useProfileMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (displayName: string): Promise<ProfileOut> => {
      const res = await putProfileMeProfilePut({
        body: { display_name: displayName },
        throwOnError: true,
      });
      return res.data;
    },
    onSuccess: (profile) => {
      queryClient.setQueryData(PROFILE_QUERY_KEY, profile);
    },
  });
}
