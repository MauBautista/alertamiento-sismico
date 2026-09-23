// [T-6.01] La tabla de escena: precedencia, la excepción escrita y quién autoriza.
import { describe, expect, it } from "vitest";

import type { LiveIncident } from "../console/useLiveIncidents";
import {
  DEGRADES_UNDER_ALERT,
  SCENE_PRECEDENCE,
  alertKind,
  authorizes,
  autorizaEvacuacion,
  nodosQueCorroboran,
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

/** Sin snapshot del mapa: nadie sabe todavía si la red corroboró. */
const SIN_RED: never[] = [];

describe("authorizes · quién puede mandar sobre el simulacro", () => {
  it("SASMEX y el cuórum de la red autorizan", () => {
    expect(authorizes(incidente({ trigger: "sasmex" }), SIN_RED)).toBe(true);
    expect(authorizes(incidente({ trigger: "quorum" }), SIN_RED)).toBe(true);
  });

  it("un aviso instrumental, una activación manual o un origen desconocido NO", () => {
    // [U-28] Ante un AVISO instrumental la consola decía «LA ALERTA REAL
    // DOMINA». Una estación sola no actúa (T-2.32) y no domina nada.
    for (const trigger of ["local_threshold", "manual", "teletransporte"]) {
      expect(authorizes(incidente({ trigger }), SIN_RED), trigger).toBe(false);
    }
    expect(autorizaEvacuacion(null, null)).toBe(false);
    expect(autorizaEvacuacion(undefined, null)).toBe(false);
  });
});

// [T-8.10 · A-063] LA CONSOLA Y EL TELÉFONO APLICAN LA MISMA REGLA.
//
// El motor de correlación NO reescribe `trigger`: enlaza `event_id` y escribe
// `meta.node_count` en el evento. El servidor (`incident/autoridad.py`) y, por
// él, el teléfono autorizan por `trigger` O por `node_count ≥ quorum_min_nodes`;
// la consola miraba solo el `trigger`. Mismo incidente: panel rojo, teléfono
// «EVACÚE», consola ámbar «SIN ACTUACIÓN». Estos casos son, uno a uno, los de
// `api/tests/incident/test_autoridad.py`.
describe("autorizaEvacuacion · espejo de `incident/autoridad.py`", () => {
  it("SASMEX autoriza siempre", () => {
    expect(autorizaEvacuacion("sasmex", null)).toBe(true);
  });

  it.each([null, 0, 1, 2])("una estación sola NO autoriza (node_count=%s)", (nodos) => {
    expect(autorizaEvacuacion("local_threshold", nodos)).toBe(false);
  });

  it("el cuórum de red autoriza SIN reescribir el trigger", () => {
    expect(autorizaEvacuacion("local_threshold", 3)).toBe(true);
    expect(autorizaEvacuacion("local_threshold", 8)).toBe(true);
  });

  it("el trigger `quorum` también autoriza", () => {
    expect(autorizaEvacuacion("quorum", null)).toBe(true);
  });

  it("manual y desconocido NO autorizan (default-deny)", () => {
    expect(autorizaEvacuacion("manual", null)).toBe(false);
    expect(autorizaEvacuacion("origen_del_futuro", null)).toBe(false);
  });

  it("el mínimo es un parámetro, no un 3 escrito dentro de la regla", () => {
    expect(autorizaEvacuacion("local_threshold", 4, 5)).toBe(false);
    expect(autorizaEvacuacion("local_threshold", 5, 5)).toBe(true);
  });
});

describe("nodosQueCorroboran · el `node_count` del evento del incidente", () => {
  const EPI = [
    { event_id: "EVT-OTRO", node_count: 9 },
    { event_id: "EVT-1", node_count: 3 },
  ];

  it("sale del epicentro de SU evento, no del primero que haya", () => {
    expect(nodosQueCorroboran(incidente({ event_id: "EVT-1" }), EPI)).toBe(3);
  });

  it("sin evento enlazado, o sin ese evento en el snapshot, no hay cuenta (null, no 0)", () => {
    expect(nodosQueCorroboran(incidente({ event_id: null }), EPI)).toBeNull();
    expect(nodosQueCorroboran(incidente({ event_id: "EVT-NADA" }), EPI)).toBeNull();
    expect(nodosQueCorroboran(incidente(), [{ event_id: "EVT-1", node_count: null }])).toBeNull();
  });

  it("un umbral local que la red corroboró AUTORIZA; con otro evento corroborado, NO", () => {
    const local = incidente({ trigger: "local_threshold", event_id: "EVT-1" });
    expect(authorizes(local, EPI)).toBe(true);
    expect(alertKind(local, EPI)).toBe("alert");
    const ajeno = incidente({ trigger: "local_threshold", event_id: "EVT-SOLO" });
    expect(authorizes(ajeno, EPI)).toBe(false);
    expect(alertKind(ajeno, EPI)).toBe("notice");
  });

  it("dos estaciones no son cuórum: el aviso sigue siendo aviso", () => {
    const local = incidente({ trigger: "local_threshold", event_id: "EVT-1" });
    expect(alertKind(local, [{ event_id: "EVT-1", node_count: 2 }])).toBe("notice");
  });

  it("la revisión sigue ganando a la autoridad, también a la de la red", () => {
    const local = incidente({ trigger: "local_threshold", event_id: "EVT-1", state: "in_review" });
    expect(alertKind(local, EPI)).toBe("review");
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
    expect(alertKind(incidente({ trigger: "sasmex" }), SIN_RED)).toBe("alert");
    expect(alertKind(incidente({ trigger: "quorum" }), SIN_RED)).toBe("alert");
    expect(alertKind(incidente({ trigger: "local_threshold" }), SIN_RED)).toBe("notice");
    expect(alertKind(incidente({ trigger: "manual" }), SIN_RED)).toBe("notice");
    expect(alertKind(null, SIN_RED)).toBeNull();
  });
});

// [T-7.16] LA REVISIÓN
describe("alertKind · la revisión, que la decide el SERVIDOR", () => {
  it("`in_review` es `review` venga de donde venga el incidente", () => {
    for (const trigger of ["sasmex", "quorum", "local_threshold", "manual"]) {
      expect(alertKind(incidente({ trigger, state: "in_review" }), SIN_RED)).toBe("review");
    }
  });

  it("la revisión GANA a la autoridad de la fuente, y no al revés", () => {
    // El caso que importa: lo abrió el WR-1 —la fuente que más autoriza— y el
    // servidor ya lo movió a revisión. Seguir pintándolo rojo como «PROTÉJASE»
    // es pintar como vigente lo que el servidor ya no sostiene (regla de oro 7).
    expect(alertKind(incidente({ trigger: "sasmex", state: "in_review" }), SIN_RED)).toBe("review");
    expect(alertKind(incidente({ trigger: "sasmex", state: "acked" }), SIN_RED)).toBe("alert");
    expect(alertKind(incidente({ trigger: "sasmex", state: "open" }), SIN_RED)).toBe("alert");
  });

  it("un WR-1 NUEVO gana a una revisión: `sceneAlert` sigue eligiendo por la cola", () => {
    // La cola llega ordenada por severidad y frescura (`mergeIncidents`): el
    // incidente nuevo va primero, y esta ficha no toca esa elección.
    const cola = [
      incidente({ incident_id: "nuevo", trigger: "sasmex", state: "open" }),
      incidente({ incident_id: "viejo", trigger: "sasmex", state: "in_review" }),
    ];
    expect(alertKind(sceneAlert(cola), SIN_RED)).toBe("alert");
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
