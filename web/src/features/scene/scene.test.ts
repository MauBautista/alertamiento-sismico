// [T-6.01] La tabla de escena: precedencia, la excepción escrita y quién autoriza.
import { describe, expect, it } from "vitest";

import type { LiveIncident } from "../console/useLiveIncidents";
import {
  DEGRADES_UNDER_ALERT,
  SCENE_PRECEDENCE,
  alertKind,
  authorizes,
  resolveScene,
  sceneAlert,
  sceneSlot,
} from "./scene";

const NADA = { alert: false, notice: false, drill: false, maintenance: false, demo: false };

function incidente(over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: "i-1",
    tenant_id: "t-1",
    site_id: "s-1",
    event_id: "EVT-1",
    opened_at: "2026-09-07T10:00:00Z",
    closed_at: null,
    severity: "critical",
    state: "open",
    trigger: "sasmex",
    max_pga_g: 0.1,
    max_pgv_cms: 1,
    ...over,
  };
}

describe("SCENE_PRECEDENCE", () => {
  it("es la tabla que decidió la ficha: alerta > aviso > simulacro > mantenimiento > demo", () => {
    expect([...SCENE_PRECEDENCE]).toEqual(["alert", "notice", "drill", "maintenance", "demo"]);
  });

  it("sin nada vivo la escena es NORMAL, que no está en la tabla: es la ausencia", () => {
    expect(resolveScene(NADA)).toBe("normal");
    expect(SCENE_PRECEDENCE).not.toContain("normal");
  });

  it("con todo vivo a la vez manda la alerta real", () => {
    expect(
      resolveScene({ alert: true, notice: true, drill: true, maintenance: true, demo: true }),
    ).toBe("alert");
  });

  it("recorre la tabla en orden: cada escena gana a las que la siguen", () => {
    expect(resolveScene({ ...NADA, drill: true, maintenance: true, demo: true })).toBe("drill");
    expect(resolveScene({ ...NADA, maintenance: true, demo: true })).toBe("maintenance");
    expect(resolveScene({ ...NADA, demo: true })).toBe("demo");
    expect(resolveScene({ ...NADA, notice: true, drill: true })).toBe("notice");
  });
});

describe("la excepción escrita", () => {
  it("bajo alerta real SOLO el simulacro se degrada; mantenimiento y demo se quedan", () => {
    // El momento en que más falta hace saber que una alarma no va a sonar es
    // justo el sismo. Cambiar esto es cambiar una decisión de T-2.71, no un
    // estilo.
    expect(DEGRADES_UNDER_ALERT).toEqual({
      notice: false,
      drill: true,
      maintenance: false,
      demo: false,
    });
  });
});

describe("authorizes · quién puede mandar sobre el simulacro", () => {
  it("SASMEX y el cuórum de la red autorizan", () => {
    expect(authorizes("sasmex")).toBe(true);
    expect(authorizes("quorum")).toBe(true);
  });

  it("un aviso instrumental, una activación manual o un origen desconocido NO", () => {
    // [U-28] Ante un AVISO instrumental la consola decía «LA ALERTA REAL
    // DOMINA». Una estación sola no actúa (T-2.32) y no domina nada.
    expect(authorizes("local_threshold")).toBe(false);
    expect(authorizes("manual")).toBe(false);
    expect(authorizes("teletransporte")).toBe(false);
    expect(authorizes(null)).toBe(false);
    expect(authorizes(undefined)).toBe(false);
  });
});

describe("sceneAlert · el incidente que define la escena", () => {
  it("es el primer crítico de la cola (ya viene ordenada por severidad)", () => {
    const cola = [
      incidente({ incident_id: "i-1", severity: "warning" }),
      incidente({ incident_id: "i-2", severity: "critical", trigger: "local_threshold" }),
      incidente({ incident_id: "i-3", severity: "critical", trigger: "sasmex" }),
    ];
    expect(sceneAlert(cola)?.incident_id).toBe("i-2");
  });

  it("sin críticos no hay escena de alerta, aunque haya avisos menores", () => {
    expect(sceneAlert([incidente({ severity: "warning" })])).toBeNull();
    expect(sceneAlert([])).toBeNull();
  });

  it("alertKind: `alert` si autoriza, `notice` si no, null sin incidente", () => {
    expect(alertKind(incidente({ trigger: "sasmex" }))).toBe("alert");
    expect(alertKind(incidente({ trigger: "quorum" }))).toBe("alert");
    expect(alertKind(incidente({ trigger: "local_threshold" }))).toBe("notice");
    expect(alertKind(incidente({ trigger: "manual" }))).toBe("notice");
    expect(alertKind(null)).toBeNull();
  });
});

// [T-7.16] LA REVISIÓN
describe("alertKind · la revisión, que la decide el SERVIDOR", () => {
  it("`in_review` es `review` venga de donde venga el incidente", () => {
    for (const trigger of ["sasmex", "quorum", "local_threshold", "manual"]) {
      expect(alertKind(incidente({ trigger, state: "in_review" }))).toBe("review");
    }
  });

  it("la revisión GANA a la autoridad de la fuente, y no al revés", () => {
    // El caso que importa: lo abrió el WR-1 —la fuente que más autoriza— y el
    // servidor ya lo movió a revisión. Seguir pintándolo rojo como «PROTÉJASE»
    // es pintar como vigente lo que el servidor ya no sostiene (regla de oro 7).
    expect(alertKind(incidente({ trigger: "sasmex", state: "in_review" }))).toBe("review");
    expect(alertKind(incidente({ trigger: "sasmex", state: "acked" }))).toBe("alert");
    expect(alertKind(incidente({ trigger: "sasmex", state: "open" }))).toBe("alert");
  });

  it("un WR-1 NUEVO gana a una revisión: `sceneAlert` sigue eligiendo por la cola", () => {
    // La cola llega ordenada por severidad y frescura (`mergeIncidents`): el
    // incidente nuevo va primero, y esta ficha no toca esa elección.
    const cola = [
      incidente({ incident_id: "nuevo", trigger: "sasmex", state: "open" }),
      incidente({ incident_id: "viejo", trigger: "sasmex", state: "in_review" }),
    ];
    expect(alertKind(sceneAlert(cola))).toBe("alert");
  });
});

describe("sceneSlot · en qué casilla de la tabla cae cada clase", () => {
  it("la tabla NO cambia: la revisión entra por una casilla que ya existía", () => {
    expect([...SCENE_PRECEDENCE]).toEqual(["alert", "notice", "drill", "maintenance", "demo"]);
  });

  it("`review` entra por `notice`, que es la casilla que no degrada nada", () => {
    expect(sceneSlot("review")).toEqual({ alert: false, notice: true });
    expect(sceneSlot("alert")).toEqual({ alert: true, notice: false });
    expect(sceneSlot("notice")).toEqual({ alert: false, notice: true });
    expect(sceneSlot(null)).toEqual({ alert: false, notice: false });
  });

  it("y por eso una revisión NO degrada el simulacro que el equipo retomó", () => {
    // Si `review` entrara por `alert`, el banner ámbar del simulacro seguiría
    // reducido a un badge después de que el sismo acabara — justo el ruido que
    // `DEGRADES_UNDER_ALERT` existe para quitar EN el peor momento, no después.
    const escena = resolveScene({ ...NADA, ...sceneSlot("review"), drill: true });
    expect(escena).toBe("notice");
    expect(DEGRADES_UNDER_ALERT.drill).toBe(true);
    expect(escena === "alert").toBe(false);
  });
});
