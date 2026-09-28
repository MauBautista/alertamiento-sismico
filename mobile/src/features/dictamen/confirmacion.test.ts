// [T-9.33 · D-43] La vista PURA de CONFIRMAR DICTAMEN: qué se le explica a la
// brigada y qué puede hacer, derivado SOLO de la cabeza de la cadena y de su
// `basis` (la procedencia que dejó la regla determinista `dictamen-v2`).
import type { DictamenOut } from "@takab/sdk";

import {
  banda,
  confirmacionView,
  edificioEnCalma,
  incidenteDeConfirmacion,
  firmanteDe,
  incidenteAConfirmar,
  selloDeFirma,
} from "./confirmacion";

function cabeza(over: Partial<DictamenOut> = {}): DictamenOut {
  return {
    dictamen_id: "d-1",
    incident_id: "i-1",
    tenant_id: "t-1",
    status: "inhabit_monitor",
    band: "amarillo",
    signed_by: null,
    signature_kind: null,
    supersedes_dictamen_id: null,
    created_at: "2026-09-27T10:00:00Z",
    basis: {
      rule_set_version: "dictamen-v2",
      band: "amarillo",
      evidence: {
        pga_g: 0.055,
        calibrated: true,
        active_sensors: 2,
        uncalibrated_sensors: 0,
        damage_reports: 0,
        damage_categories: [],
      },
      params: { verde_max_g: 0.04, rojo_min_g: 0.1 },
      motivos: ["pga_banda_amarilla"],
    },
    ...over,
  };
}

describe("banda", () => {
  it("la columna manda; sin columna, se deriva del status (desconocido ⇒ rojo)", () => {
    expect(banda({ band: "verde", status: "no_inhabit_inspect" })).toBe(
      "verde",
    );
    expect(banda({ band: null, status: "normal_operation" })).toBe("verde");
    expect(banda({ band: null, status: "inhabit_monitor" })).toBe("amarillo");
    expect(banda({ band: null, status: "restricted" })).toBe("rojo");
    expect(banda({ band: "raro", status: "otro" })).toBe("rojo");
  });
});

describe("confirmacionView", () => {
  it("sin cadena ⇒ vacío honesto", () => {
    expect(confirmacionView(undefined, "calma").tipo).toBe("sin_dictamen");
  });

  it("AMARILLO sin firmar ⇒ confirmable, con el porqué de la PGA contra sus umbrales", () => {
    const v = confirmacionView(cabeza(), "calma");
    expect(v.tipo).toBe("confirmable");
    if (v.tipo !== "confirmable") return;
    expect(v.dictamenId).toBe("d-1");
    expect(v.banda).toBe("amarillo");
    expect(v.titulo).toBe("DICTAMEN AMARILLO · HABITAR CON MONITOREO");
    expect(v.porque).toContain(
      "La aceleración máxima medida (0.055 g) está entre 0.04 g y 0.1 g.",
    );
    expect(v.revision.length).toBeGreaterThanOrEqual(3);
  });

  it("explica daños no estructurales, falta de calibración y falta de PGA", () => {
    const v = confirmacionView(
      cabeza({
        basis: {
          evidence: {
            pga_g: null,
            calibrated: false,
            active_sensors: 2,
            uncalibrated_sensors: 1,
            damage_reports: 1,
            damage_categories: ["water_leak"],
          },
          params: { verde_max_g: 0.04, rojo_min_g: 0.1 },
          motivos: ["sin_pga", "sin_calibracion", "dano:water_leak"],
        },
      }),
      "calma",
    );
    if (v.tipo !== "confirmable") throw new Error(v.tipo);
    expect(v.porque).toEqual([
      "No hay aceleración medida en el edificio: sin ese dato no se puede dar el verde.",
      "1 de 2 sensores activos no tiene calibración declarada: sus lecturas son relativas.",
      "Se reportó un daño: fuga de agua.",
    ]);
  });

  it("un motivo que la app no conoce se dice sin inventarle significado", () => {
    const v = confirmacionView(
      cabeza({ basis: { motivos: ["nuevo_motivo"] } }),
      "calma",
    );
    if (v.tipo !== "confirmable") throw new Error(v.tipo);
    expect(v.porque).toEqual(["Otro motivo registrado por la regla."]);
  });

  it("una basis sin motivos (fila vieja) no se queda en blanco", () => {
    const v = confirmacionView(cabeza({ basis: {} }), "calma");
    if (v.tipo !== "confirmable") throw new Error(v.tipo);
    expect(v.porque).toEqual(["La regla no dejó el detalle de la evaluación."]);
  });

  it("ROJO sin firmar ⇒ NO se confirma: lo firma el inspector", () => {
    const v = confirmacionView(
      cabeza({ status: "no_inhabit_inspect", band: "rojo" }),
      "calma",
    );
    expect(v.tipo).toBe("solo_inspector");
  });

  // [F3·r3] La nube responde 409 a confirmar un VERDE (lo firma el sistema tras
  // la gracia) y a una fila sin banda (no es salida de la regla v2): la app no
  // ofrece un botón que siempre falla.
  it("VERDE sin firmar ⇒ NO se confirma: lo firma el sistema", () => {
    const v = confirmacionView(
      cabeza({ status: "normal_operation", band: "verde" }),
      "calma",
    );
    expect(v.tipo).toBe("lo_firma_el_sistema");
  });

  it("fila sin banda (histórica) sin firmar ⇒ NO se confirma: la firma el inspector", () => {
    const v = confirmacionView(
      cabeza({ status: "inhabit_monitor", band: null }),
      "calma",
    );
    expect(v.tipo).toBe("solo_inspector");
  });

  it("cabeza ya firmada ⇒ nada que confirmar, y dice por quién", () => {
    const v = confirmacionView(
      cabeza({ signed_by: "u-9", signature_kind: "confirmation" }),
      "calma",
    );
    expect(v.tipo).toBe("ya_firmado");
    if (v.tipo !== "ya_firmado") return;
    expect(v.firmante).toBe("CONFIRMADO POR PERSONAL AUTORIZADO");
  });
});

describe("selloDeFirma (sale del signature_kind y la banda, nunca de signed_by)", () => {
  it("cada tipo tiene su rótulo; el histórico (NULL) es el del inspector", () => {
    expect(selloDeFirma({ signature_kind: "inspector" })).toBe(
      "FIRMA DIGITAL · INSPECTOR",
    );
    expect(selloDeFirma({ signature_kind: null })).toBe(
      "FIRMA DIGITAL · INSPECTOR",
    );
    expect(selloDeFirma({})).toBe("FIRMA DIGITAL · INSPECTOR");
    expect(selloDeFirma({ signature_kind: "system" })).toBe(
      "EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA",
    );
    expect(selloDeFirma({ signature_kind: "confirmation" })).toBe(
      "CONFIRMADO POR PERSONAL AUTORIZADO",
    );
  });

  // [F3·r3] El sistema dice CON QUÉ banda emitió; la confirmación, QUIÉN (su rol).
  it("sistema lleva la banda; confirmación lleva el ROL de quien confirma", () => {
    expect(selloDeFirma({ signature_kind: "system", band: "verde" })).toBe(
      "EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA · BANDA VERDE",
    );
    expect(
      selloDeFirma({
        signature_kind: "confirmation",
        confirmed_by_role: "brigadista",
      }),
    ).toBe("CONFIRMADO POR BRIGADISTA");
    expect(
      selloDeFirma({
        signature_kind: "confirmation",
        confirmed_by_role: "tenant_admin",
      }),
    ).toBe("CONFIRMADO POR ADMINISTRADOR");
    // Una banda que no se entiende no se imprime (no se inventa un color).
    expect(selloDeFirma({ signature_kind: "system", band: "morado" })).toBe(
      "EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA",
    );
  });

  it("un tipo desconocido NO se atribuye al inspector", () => {
    expect(selloDeFirma({ signature_kind: "otro" })).toBe("FIRMA DIGITAL");
  });
});

describe("firmanteDe (NUNCA un identificador interno)", () => {
  const UUID = "70000000-1111-2222-3333-444444444444";
  it("cada tipo dice QUIÉN por su papel, jamás el signed_by", () => {
    expect(firmanteDe({ signature_kind: "system", signed_by: null })).toBe(
      "SISTEMA",
    );
    expect(firmanteDe({ signature_kind: "inspector", signed_by: UUID })).toBe(
      "INSPECTOR",
    );
    expect(firmanteDe({ signature_kind: null, signed_by: UUID })).toBe(
      "INSPECTOR",
    );
    expect(
      firmanteDe({
        signature_kind: "confirmation",
        signed_by: UUID,
        confirmed_by_role: "brigadista",
      }),
    ).toBe("BRIGADISTA");
    expect(
      firmanteDe({ signature_kind: "confirmation", signed_by: UUID }),
    ).toBe("PERSONAL AUTORIZADO");
    expect(firmanteDe({ signature_kind: "otro", signed_by: UUID })).toBe("—");
    for (const k of ["system", "inspector", null, "confirmation", "otro"]) {
      expect(firmanteDe({ signature_kind: k, signed_by: UUID })).not.toMatch(
        /70000000/,
      );
    }
  });
});

describe("incidenteAConfirmar (la entrada desde el panel táctico)", () => {
  const estado = (reason: string | null, over: Record<string, unknown> = {}) =>
    ({
      incident: null,
      reentry: {
        blocked: reason !== null,
        dictamen_signed: false,
        dictamen_status: "inhabit_monitor",
        incident_id: "i-9",
        reason,
      },
      ...over,
    }) as unknown as Parameters<typeof incidenteAConfirmar>[0];

  it("pendiente_confirmacion + confirm_dictamen ⇒ el incidente del reingreso", () => {
    expect(
      incidenteAConfirmar(estado("pendiente_confirmacion"), {
        confirm_dictamen: true,
      }),
    ).toBe("i-9");
  });

  it("sin el permiso, u otro motivo, o sin incidente ⇒ null", () => {
    expect(
      incidenteAConfirmar(estado("pendiente_confirmacion"), {}),
    ).toBeNull();
    expect(
      incidenteAConfirmar(estado("pendiente_confirmacion"), undefined),
    ).toBeNull();
    expect(
      incidenteAConfirmar(estado("pendiente_confirmacion"), {
        confirm_dictamen: false,
      }),
    ).toBeNull();
    expect(
      incidenteAConfirmar(estado("pendiente_dictamen"), {
        confirm_dictamen: true,
      }),
    ).toBeNull();
    expect(
      incidenteAConfirmar(estado("no_habitable"), { confirm_dictamen: true }),
    ).toBeNull();
    expect(
      incidenteAConfirmar(estado(null), { confirm_dictamen: true }),
    ).toBeNull();
    const sinId = estado("pendiente_confirmacion");
    (sinId.reentry as { incident_id?: string | null }).incident_id = null;
    expect(incidenteAConfirmar(sinId, { confirm_dictamen: true })).toBeNull();
  });

  it("sin incident_id en el reingreso usa el incidente abierto", () => {
    const e = estado("pendiente_confirmacion", {
      incident: { incident_id: "i-abierto" },
    });
    (e.reentry as { incident_id?: string | null }).incident_id = null;
    expect(incidenteAConfirmar(e, { confirm_dictamen: true })).toBe(
      "i-abierto",
    );
  });
});

// [D-49 · R1] Nada se confirma con el edificio en movimiento: la app no ofrece el
// botón y explica por qué (la nube respondería 409 «vuelva a calma»).
describe("[D-49 · R1] confirmar exige el edificio en calma", () => {
  it("AMARILLO sin firmar con el edificio en movimiento ⇒ espere a la calma, SIN botón", () => {
    const v = confirmacionView(cabeza(), "movimiento");
    expect(v.tipo).toBe("espere_calma");
    if (v.tipo !== "espere_calma") return;
    expect(v.explicacion).toMatch(/espere a que el edificio vuelva a calma/i);
    expect(v.porque.length).toBeGreaterThan(0);
  });

  it("calma desconocida (sin mobile-state) ⇒ tampoco se ofrece, y lo dice", () => {
    const v = confirmacionView(cabeza(), "desconocida");
    expect(v.tipo).toBe("espere_calma");
    if (v.tipo !== "espere_calma") return;
    expect(v.explicacion).toMatch(/no se pudo comprobar/i);
  });

  it("VERDE, ROJO y firmado se explican igual con movimiento (su causa manda)", () => {
    expect(
      confirmacionView(
        cabeza({ band: "verde", status: "normal_operation" }),
        "movimiento",
      ).tipo,
    ).toBe("lo_firma_el_sistema");
    expect(
      confirmacionView(
        cabeza({ band: "rojo", status: "restricted" }),
        "movimiento",
      ).tipo,
    ).toBe("solo_inspector");
    expect(
      confirmacionView(cabeza({ signed_by: "u-1" }), "movimiento").tipo,
    ).toBe("ya_firmado");
  });

  it("edificioEnCalma: EXACTAMENTE el criterio de `reingreso.en_calma` (sólo latest_tier)", () => {
    const e = (phase: string, latest_tier: string | null) =>
      ({ phase, latest_tier }) as Parameters<typeof edificioEnCalma>[0];
    expect(edificioEnCalma(e("shaking_concluded", "normal"))).toBe("calma");
    expect(edificioEnCalma(e("reentry_blocked", null))).toBe("calma");
    expect(edificioEnCalma(e("reentry_blocked", "watch"))).toBe("movimiento");
    expect(edificioEnCalma(e("idle", "evacuate_or_hold"))).toBe("movimiento");
    // La fase NO decide: la nube (routers/dictamens.confirm_dictamen) sólo mira el
    // último tier. Con la fase `alert_active` y el tier `normal`/null la nube
    // ACEPTA confirmar; la app no puede negarlo con un «espere a la calma» que la
    // nube no exige (divergencia ⇒ botón oculto sin motivo real).
    expect(edificioEnCalma(e("alert_active", null))).toBe("calma");
    expect(edificioEnCalma(e("alert_active", "normal"))).toBe("calma");
    expect(edificioEnCalma(e("building_movement", "normal"))).toBe("calma");
    expect(edificioEnCalma(e("alert_active", "restricted"))).toBe("movimiento");
    expect(edificioEnCalma(undefined)).toBe("desconocida");
    expect(edificioEnCalma(null)).toBe("desconocida");
  });
});

describe("[D-49 · R2] la entrada a CONFIRMAR, venga de donde venga el AMARILLO", () => {
  const PUEDE = { confirm_dictamen: true };
  const estado = (over: Record<string, unknown>) =>
    ({
      phase: "reentry_blocked",
      latest_tier: "normal",
      incident: null,
      reentry: {
        blocked: true,
        dictamen_signed: false,
        dictamen_status: "inhabit_monitor",
        incident_id: "i-viejo",
        reason: "pendiente_confirmacion",
      },
      ...over,
    }) as unknown as Parameters<typeof incidenteAConfirmar>[0];

  it("lo decide el TIER, como la nube: con movimiento NO se ofrece; la fase sola no lo niega", () => {
    expect(
      incidenteAConfirmar(
        estado({ phase: "alert_active", latest_tier: "evacuate_or_hold" }),
        PUEDE,
      ),
    ).toBeNull();
    expect(
      incidenteAConfirmar(
        estado({ phase: "building_movement", latest_tier: "watch" }),
        PUEDE,
      ),
    ).toBeNull();
    // Tier `normal`: la nube ACEPTA la confirmación; la app no la esconde por la fase.
    expect(incidenteAConfirmar(estado({ phase: "alert_active" }), PUEDE)).toBe(
      "i-viejo",
    );
  });

  it("AMARILLO de un incidente ANTERIOR con otro abierto ⇒ el del reingreso, no el abierto", () => {
    const e = estado({
      phase: "shaking_concluded",
      incident: { incident_id: "i-abierto" },
    });
    expect(incidenteAConfirmar(e, PUEDE)).toBe("i-viejo");
    expect(incidenteDeConfirmacion(e)).toBe("i-viejo");
  });

  it("AMARILLO del ABIERTO (sin incident_id en reentry) ⇒ el abierto", () => {
    const e = estado({
      phase: "shaking_concluded",
      incident: { incident_id: "i-abierto" },
    });
    (e.reentry as { incident_id?: string | null }).incident_id = null;
    expect(incidenteAConfirmar(e, PUEDE)).toBe("i-abierto");
  });

  it("incidenteDeConfirmacion sin razón pendiente ⇒ el abierto primero (la push)", () => {
    const e = estado({
      incident: { incident_id: "i-abierto" },
      reentry: { blocked: false, incident_id: "i-viejo", reason: null },
    });
    expect(incidenteDeConfirmacion(e)).toBe("i-abierto");
    expect(incidenteDeConfirmacion(undefined)).toBeNull();
  });
});
