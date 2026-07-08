import { QueryClient } from "@tanstack/react-query";

/**
 * Query cache del SOC: la frescura la gobiernan el WS (invalidación/merge) y
 * los pollers de cada feature — no el foco de ventana (esto es un videowall).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 5_000,
      },
    },
  });
}
