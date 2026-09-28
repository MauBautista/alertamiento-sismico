import type { RouteObject } from "react-router";

import AuditPage from "../features/audit/AuditPage";
import ConsolePage from "../features/console/ConsolePage";
import FleetPage from "../features/fleet/FleetPage";
import TenantsPage from "../features/tenants/TenantsPage";
import TriagePage from "../features/triage/TriagePage";
import AuthCallbackPage from "../pages/AuthCallbackPage";
import BuildingPage from "../features/building/BuildingPage";
import CierreWizard from "../features/cierre/CierreWizard";
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
            // [T-9.41 · D-43] El asistente de cierre cuelga de la guarda de
            // `/triage`: no es una ruta nueva de `allowed_routes`, es una vista
            // del mismo permiso.
            path: "/triage/:incidentId/cierre",
            element: (
              <RouteGuard routeKey="/triage">
                <CierreWizard />
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
            path: "/audit",
            element: (
              <RouteGuard routeKey="/audit">
                <AuditPage />
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
