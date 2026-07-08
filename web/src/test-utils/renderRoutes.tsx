import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { routes } from "../app/routes";
import type { MeResponse } from "../auth/me";
import { useSessionStore } from "../auth/session.store";

export function seedAuthenticated(me: MeResponse): void {
  useSessionStore.setState({
    status: "authenticated",
    origin: "dev",
    idToken: "tok-test",
    me,
    error: null,
  });
}

/** Monta el árbol real de rutas en un memory router y devuelve el router para
 * asertar location (bloqueo in-place vs redirect). Provee un QueryClient limpio
 * sin retries: las páginas con datos (fleet/console) caen a su estado error sin
 * red y el shell/heading sigue siendo asertable. */
export function renderRoutesAt(path: string, state?: unknown) {
  const router = createMemoryRouter(routes, {
    initialEntries: [state === undefined ? path : { pathname: path, state }],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
