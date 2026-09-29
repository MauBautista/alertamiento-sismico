// T-2.02 — gate de perfil SERVER-DRIVEN (spec móvil §8 + RBAC §3).
// Regla: default-deny. El grupo de rutas sale de lo que /me responde
// (role + surface); jamás de lógica horneada en la UI.
import { gateFor, TACTICAL_ROLES } from "./profileGate";

describe("gateFor — default-deny server-driven", () => {
  it("sin sesión ⇒ no_session", () => {
    expect(gateFor(null)).toEqual({ allowed: false, reason: "no_session" });
    expect(gateFor(undefined)).toEqual({ allowed: false, reason: "no_session" });
  });

  it("occupant con superficie móvil ⇒ grupo occupant", () => {
    expect(gateFor({ role: "occupant", surface: "mobile" })).toEqual({
      allowed: true,
      group: "occupant",
    });
  });

  it.each(["brigadista", "inspector", "tenant_admin"])(
    "%s (RBAC §3 · D-42: superficie móvil o both) ⇒ grupo tactical",
    (role) => {
      expect(gateFor({ role, surface: "mobile" })).toEqual({ allowed: true, group: "tactical" });
      expect(gateFor({ role, surface: "both" })).toEqual({ allowed: true, group: "tactical" });
    },
  );

  it("superficie web pura ⇒ wrong_surface (aunque el rol fuera móvil)", () => {
    expect(gateFor({ role: "occupant", surface: "web" })).toEqual({
      allowed: false,
      reason: "wrong_surface",
    });
    expect(gateFor({ role: "brigadista", surface: "web" })).toEqual({
      allowed: false,
      reason: "wrong_surface",
    });
  });

  it("rol sin superficie móvil (p.ej. gov_operator o takab_superadmin) ⇒ role_not_mobile", () => {
    expect(gateFor({ role: "gov_operator", surface: "both" })).toEqual({
      allowed: false,
      reason: "role_not_mobile",
    });
    expect(gateFor({ role: "takab_superadmin", surface: "both" })).toEqual({
      allowed: false,
      reason: "role_not_mobile",
    });
  });

  it("rol desconocido JAMÁS pasa (default-deny)", () => {
    expect(gateFor({ role: "mystery", surface: "mobile" })).toEqual({
      allowed: false,
      reason: "role_not_mobile",
    });
  });

  // [T-9.11 · D-42] el administrador usa la app táctica completa.
  it("el set táctico es exactamente brigadista, inspector y tenant_admin (D-42)", () => {
    expect([...TACTICAL_ROLES].sort()).toEqual(["brigadista", "inspector", "tenant_admin"]);
  });

  // [T-9.81 · D-42] los alias se dieron de baja: el servidor responde 401
  // `rol_retirado` (fin de sesión) y no emite un rol viejo en /me. Si aun así
  // llegara uno, la app NO lo traduce a su heredero: default-deny.
  it.each(["security_guard", "building_admin", "soc_operator"])(
    "rol retirado %s ⇒ fuera (ya no se trata como su heredero)",
    (role) => {
      expect(gateFor({ role, surface: "mobile" })).toEqual({
        allowed: false,
        reason: "role_not_mobile",
      });
    },
  );

  it("un rol viejo con superficie web sigue fuera por la superficie", () => {
    expect(gateFor({ role: "security_guard", surface: "web" })).toEqual({
      allowed: false,
      reason: "wrong_surface",
    });
  });
});
