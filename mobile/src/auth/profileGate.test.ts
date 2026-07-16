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

  it.each(["brigadista", "security_guard", "inspector", "building_admin"])(
    "%s (RBAC §3: superficie móvil o both) ⇒ grupo tactical",
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

  it("rol sin superficie móvil declarada (p.ej. soc_operator) ⇒ role_not_mobile", () => {
    expect(gateFor({ role: "soc_operator", surface: "both" })).toEqual({
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

  it("el set táctico es exactamente el de RBAC §3", () => {
    expect([...TACTICAL_ROLES].sort()).toEqual([
      "brigadista",
      "building_admin",
      "inspector",
      "security_guard",
    ]);
  });
});
