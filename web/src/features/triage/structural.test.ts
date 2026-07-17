import { describe, expect, it } from "vitest";

import type { DamageReportOut } from "@takab/sdk";

import { damageReportView, orderedDamageReports, verifyLabel } from "./structural";

function report(over: Partial<DamageReportOut> = {}): DamageReportOut {
  return {
    report_id: "r-1",
    incident_id: "i-1",
    site_id: "s-1",
    zone_id: null,
    user_sub: "u-1",
    categories: [{ key: "structural", severity: "high" }],
    people_at_risk: false,
    notes: null,
    evidence_ids: [],
    ts_device: null,
    created_at: "2026-07-16T10:00:00Z",
    ...over,
  };
}

describe("damageReportView", () => {
  it("mapea categorías a etiquetas y calcula la severidad más alta", () => {
    const v = damageReportView(
      report({
        categories: [
          { key: "water_leak", severity: "low" },
          { key: "structural", severity: "critical" },
        ],
      }),
    );
    expect(v.categories.map((c) => c.label)).toEqual(["Fuga de agua", "Daño estructural"]);
    expect(v.topSeverity).toBe("critical");
  });

  it("categoría desconocida cae a su key crudo (no rompe)", () => {
    const v = damageReportView(report({ categories: [{ key: "xyz", severity: "low" }] }));
    expect(v.categories[0].label).toBe("xyz");
  });
});

describe("orderedDamageReports — personas en riesgo al frente", () => {
  it("urgentes primero, luego el más reciente", () => {
    const reports = [
      report({ report_id: "viejo", created_at: "2026-07-16T09:00:00Z" }),
      report({
        report_id: "urgente",
        people_at_risk: true,
        created_at: "2026-07-16T08:00:00Z",
      }),
      report({ report_id: "nuevo", created_at: "2026-07-16T11:00:00Z" }),
    ];
    expect(orderedDamageReports(reports).map((r) => r.reportId)).toEqual([
      "urgente",
      "nuevo",
      "viejo",
    ]);
  });
});

describe("verifyLabel — copy honesta", () => {
  it("cada estado tiene su rótulo, sin fingir", () => {
    expect(verifyLabel("verified")).toBe("HASH VERIFICADO");
    expect(verifyLabel("tampered")).toBe("HASH ALTERADO");
    expect(verifyLabel("error")).toBe("NO SE PUDO VERIFICAR");
    expect(verifyLabel("idle")).toBe("VERIFICAR HASH");
  });
});
