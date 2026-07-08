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
 * asertar location (bloqueo in-place vs redirect). */
export function renderRoutesAt(path: string, state?: unknown) {
  const router = createMemoryRouter(routes, {
    initialEntries: [state === undefined ? path : { pathname: path, state }],
  });
  render(<RouterProvider router={router} />);
  return router;
}
