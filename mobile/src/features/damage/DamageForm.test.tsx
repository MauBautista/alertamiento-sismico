// 2.4 — el form marca prioridad máxima con personas en riesgo y arma el payload
// espejo del backend.
import { fireEvent, render } from "@testing-library/react-native";
import { useState } from "react";

import { DamageForm } from "./DamageForm";
import type { DamageKey, Severity } from "./categories";
import { buildDamageReportBody } from "./payload";

function Harness(props: { onSubmit?: (sel: Map<DamageKey, Severity>) => void }) {
  const [selected, setSelected] = useState<Map<DamageKey, Severity>>(new Map());
  return (
    <DamageForm
      busy={false}
      evidenceCount={2}
      notes=""
      onAddPhoto={jest.fn()}
      onNotes={jest.fn()}
      onSeverity={(k, s) => setSelected((p) => new Map(p).set(k, s))}
      onSubmit={() => props.onSubmit?.(selected)}
      onToggle={(k) =>
        setSelected((p) => {
          const n = new Map(p);
          if (n.has(k)) n.delete(k);
          else n.set(k, "medium");
          return n;
        })
      }
      selected={selected}
    />
  );
}

describe("DamageForm (2.4)", () => {
  it("people_trapped ⇒ banner de PRIORIDAD MÁXIMA", async () => {
    const v = await render(<Harness />);
    expect(v.queryByTestId("urgent-banner")).toBeNull();
    await fireEvent.press(v.getByTestId("cat-people_trapped").children[0] as never);
    expect(v.getByTestId("urgent-banner")).toHaveTextContent(/PERSONAS EN RIESGO/);
  });

  it("muestra el conteo de fotos forenses ligadas", async () => {
    const v = await render(<Harness />);
    expect(v.getByTestId("add-photo")).toHaveTextContent(/2 foto\(s\)/);
  });

  it("no envía sin al menos una categoría (botón deshabilitado)", async () => {
    const onSubmit = jest.fn();
    const v = await render(<Harness onSubmit={onSubmit} />);
    await fireEvent.press(v.getByTestId("submit-damage"));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("buildDamageReportBody", () => {
  it("arma categorías con severidad + evidencias + notas normalizadas", () => {
    const body = buildDamageReportBody({
      categories: [
        { key: "structural", severity: "critical" },
        { key: "people_trapped", severity: "critical", note: "2 personas" },
      ],
      notes: "  columna NE  ",
      zoneId: "z-1",
      evidenceIds: ["ev-1", "ev-2"],
      tsDevice: "2026-07-16T10:00:00Z",
    });
    expect(body.categories).toEqual([
      { key: "structural", severity: "critical" },
      { key: "people_trapped", severity: "critical", note: "2 personas" },
    ]);
    expect(body.notes).toBe("columna NE");
    expect(body.evidence_ids).toEqual(["ev-1", "ev-2"]);
    expect(body.zone_id).toBe("z-1");
  });

  it("notas vacías ⇒ null (no cadena en blanco)", () => {
    expect(
      buildDamageReportBody({
        categories: [{ key: "gas_leak", severity: "low" }],
        notes: "   ",
        zoneId: null,
        evidenceIds: [],
        tsDevice: "t",
      }).notes,
    ).toBeNull();
  });
});
