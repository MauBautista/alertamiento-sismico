import type { RouteObject } from "react-router";

import ConsolePage from "../features/console/ConsolePage";
import FleetPage from "../features/fleet/FleetPage";
import TenantsPage from "../features/tenants/TenantsPage";
import TriagePage from "../features/triage/TriagePage";
import AuthCallbackPage from "../pages/AuthCallbackPage";
import BuildingPage from "../pages/BuildingPage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
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
                <ConsolePage />
              </RouteGuard>
            ),
          },
          {
            path: "/fleet",
            element: (
              <RouteGuard routeKey="/fleet">
                <FleetPage />
              </RouteGuard>
            ),
          },
          {
            path: "/triage",
            element: (
              <RouteGuard routeKey="/triage">
                <TriagePage />
              </RouteGuard>
            ),
          },
          {
            path: "/tenants",
            element: (
              <RouteGuard routeKey="/tenants">
                <TenantsPage />
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
