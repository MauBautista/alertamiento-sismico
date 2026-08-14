import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ALL_ROUTES, ME_FIXTURES, MOBILE_ONLY_ROLES, WEB_ROLES } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";

type RouteKey = (typeof ALL_ROUTES)[number];

const URL_BY_ROUTE: Record<RouteKey, string> = {
  "/console": "/console",
  "/fleet": "/fleet",
  "/triage": "/triage",
  "/tenants": "/tenants",
  "/audit": "/audit",
  "/building": "/building/S-001",
};

const HEADING_BY_ROUTE: Record<RouteKey, string> = {
  "/console": "Monitoreo en Vivo",
  "/fleet": "Flota Edge y Estado de Gabinetes",
  "/triage": "Evaluación Estructural Post-Sismo",
  "/tenants": "Matriz Multi-Tenant y Umbrales",
  "/audit": "Bitácora de Auditoría",
  "/building": "DASHBOARD EDIFICIO",
};

describe("guards de routing — matriz 10 roles × 6 rutas (criterio central T-1.26)", () => {
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

  // [T-2.134] Aquí vivía «error ⇒ ErrorScreen y REINTENTAR llama refreshMe». El
  // estado `"error"` se retiró por no tener productor desde `T-2.123`, y con él
  // la pantalla. Lo que este caso cubría —«/me no contesta ⇒ el muro responde
  // in-place, con reintento»— lo cubre hoy el degradado, que es el estado que sí
  // se produce, y con más exigencia: `degraded-session.test.tsx` comprueba
  // además que no se pide ni un dato en las 6 rutas.
  it("degraded ⇒ el muro deniega IN-PLACE, sin rebotar al login", () => {
    useSessionStore.setState({ status: "degraded", error: "ECONNREFUSED", me: null });
    const router = renderRoutesAt("/console");
    expect(router.state.location.pathname).toBe("/console");
    expect(screen.getByRole("heading", { name: "CONSOLA EN MODO DEGRADADO" })).toBeInTheDocument();
    expect(screen.getByText("ECONNREFUSED")).toBeInTheDocument();
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
