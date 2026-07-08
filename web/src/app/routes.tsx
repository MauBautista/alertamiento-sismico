import type { RouteObject } from "react-router";

import AuthCallbackPage from "../pages/AuthCallbackPage";
import BuildingPage from "../pages/BuildingPage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
import PlaceholderPage from "../pages/PlaceholderPage";
import AppShell from "../shell/AppShell";
import RequireSession from "./RequireSession";
import RouteGuard from "./RouteGuard";

/** Árbol único de rutas: createBrowserRouter en App, createMemoryRouter en tests. */
export const routes: RouteObject[] = [
  { path: "/", element: <LoginPage /> },
  { path: "/auth/callback", element: <AuthCallbackPage /> },
  {
    element: <RequireSession />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            path: "/console",
            element: (
              <RouteGuard routeKey="/console">
                <PlaceholderPage title="CONSOLA C4I" taskRef="T-1.27" />
              </RouteGuard>
            ),
          },
          {
            path: "/fleet",
            element: (
              <RouteGuard routeKey="/fleet">
                <PlaceholderPage title="FLOTA EDGE" taskRef="T-1.28" />
              </RouteGuard>
            ),
          },
          {
            path: "/triage",
            element: (
              <RouteGuard routeKey="/triage">
                <PlaceholderPage title="TRIAGE" taskRef="T-1.29" />
              </RouteGuard>
            ),
          },
          {
            path: "/tenants",
            element: (
              <RouteGuard routeKey="/tenants">
                <PlaceholderPage title="MULTI-TENANT" taskRef="T-1.30" />
              </RouteGuard>
            ),
          },
          {
            path: "/building/:siteId",
            element: (
              <RouteGuard routeKey="/building">
                <BuildingPage />
              </RouteGuard>
            ),
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
