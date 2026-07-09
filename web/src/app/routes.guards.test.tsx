import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ALL_ROUTES, ME_FIXTURES, MOBILE_ONLY_ROLES, WEB_ROLES } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";

type RouteKey = (typeof ALL_ROUTES)[number];

const URL_BY_ROUTE: Record<RouteKey, string> = {
  "/console": "/console",
  "/fleet": "/fleet",
  "/triage": "/triage",
  "/tenants": "/tenants",
  "/building": "/building/S-001",
};

const HEADING_BY_ROUTE: Record<RouteKey, string> = {
  "/console": "CONSOLA C4I",
  "/fleet": "Flota Edge y Estado de Gabinetes",
  "/triage": "Triage Estructural e Historial",
  "/tenants": "Matriz Multi-Tenant y Umbrales",
  "/building": "DASHBOARD EDIFICIO",
};

describe("guards de routing — matriz 10 roles × 5 rutas (criterio central T-1.26)", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
  });

  const matrix = [...WEB_ROLES, ...MOBILE_ONLY_ROLES].flatMap((role) =>
    ALL_ROUTES.map((routeKey) => ({ role, routeKey })),
  );

  it.each(matrix)("$role → $routeKey", ({ role, routeKey }) => {
    const me = ME_FIXTURES[role];
    seedAuthenticated(me);
    const url = URL_BY_ROUTE[routeKey];
    const router = renderRoutesAt(url);

    if (me.allowed_routes.length === 0) {
      // Rol mobile-only: ninguna URL protegida rinde contenido web.
      expect(screen.getByText("SIN SUPERFICIE WEB")).toBeInTheDocument();
    } else if (me.allowed_routes.includes(routeKey)) {
      expect(screen.getByRole("heading", { name: HEADING_BY_ROUTE[routeKey] })).toBeInTheDocument();
    } else {
      expect(screen.getByRole("heading", { name: "SIN ACCESO" })).toBeInTheDocument();
    }
    // Bloqueo IN-PLACE: la URL del deep-link nunca cambia estando autenticado.
    expect(router.state.location.pathname).toBe(url);
  });
});

describe("estados de sesión en rutas protegidas", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
  });

  it("booting ⇒ splash (sin redirect)", () => {
    // resetSessionStoreForTests deja status "booting".
    const router = renderRoutesAt("/console");
    expect(screen.getByText(/INICIANDO CONSOLA/)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/console");
  });

  it("anonymous ⇒ redirect a / con state.returnTo", () => {
    useSessionStore.setState({ status: "anonymous" });
    const router = renderRoutesAt("/fleet");
    expect(router.state.location.pathname).toBe("/");
    expect(router.state.location.state).toEqual({ returnTo: "/fleet" });
    expect(screen.getByRole("heading", { name: "CONSOLA SOC" })).toBeInTheDocument();
  });

  it("error ⇒ ErrorScreen y REINTENTAR llama refreshMe", () => {
    const refreshMe = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ status: "error", error: "ECONNREFUSED", refreshMe });
    renderRoutesAt("/console");
    expect(screen.getByRole("heading", { name: "ERROR DE SESIÓN" })).toBeInTheDocument();
    expect(screen.getByText("ECONNREFUSED")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(refreshMe).toHaveBeenCalledTimes(1);
  });

  it("el dashboard de edificio muestra el siteId del deep-link", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    renderRoutesAt("/building/S-001");
    expect(screen.getByText("S-001")).toBeInTheDocument();
  });

  it("ruta inexistente ⇒ 404", () => {
    useSessionStore.setState({ status: "anonymous" });
    renderRoutesAt("/no-existe");
    expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
  });
});
