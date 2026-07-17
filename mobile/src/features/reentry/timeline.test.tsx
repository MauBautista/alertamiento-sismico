// 1.5 — la timeline deriva SOLO de datos del servidor; "Reingreso autorizado"
// JAMÁS se marca done aquí (al aprobarse, la fase saca al usuario de esta
// pantalla). El estado del check-in local se declara (guardado ≠ recibido).
import { render } from "@testing-library/react-native";

import { ReentryBlockedView } from "./ReentryBlockedView";
import { reentryTimeline } from "./timeline";

const BASE = {
  openedAt: "2026-07-16T10:00:00Z",
  hasOwnCheckin: true,
  checkinSynced: true,
  dictamenStatus: null,
  dictamenSigned: false,
};

describe("reentryTimeline — derivación pura", () => {
  it("NINGUNA combinación marca 'Reingreso autorizado' como done", () => {
    for (const hasOwnCheckin of [true, false]) {
      for (const checkinSynced of [true, false]) {
        for (const dictamenSigned of [true, false]) {
          for (const dictamenStatus of [null, "requested", "normal_operation"]) {
            const steps = reentryTimeline({
              ...BASE,
              hasOwnCheckin,
              checkinSynced,
              dictamenSigned,
              dictamenStatus,
            });
            expect(steps.find((s) => s.key === "reingreso")?.state).toBe("pending");
          }
        }
      }
    }
  });

  it("check-in encolado sin red: current con 'guardado en este dispositivo'", () => {
    const steps = reentryTimeline({ ...BASE, checkinSynced: false });
    const checkin = steps.find((s) => s.key === "checkin");
    expect(checkin?.state).toBe("current");
    expect(checkin?.detail).toMatch(/Guardado en este dispositivo/);
  });

  it("check-in recibido: done; sin dictamen: evaluación en curso", () => {
    const steps = reentryTimeline(BASE);
    expect(steps.find((s) => s.key === "checkin")?.state).toBe("done");
    const dictamen = steps.find((s) => s.key === "dictamen");
    expect(dictamen?.state).toBe("current");
    expect(dictamen?.detail).toMatch(/En espera del inspector/);
  });

  it("dictamen firmado NO habitable: done pero el reingreso sigue pending", () => {
    const steps = reentryTimeline({
      ...BASE,
      dictamenSigned: true,
      dictamenStatus: "restricted_use",
    });
    expect(steps.find((s) => s.key === "dictamen")?.state).toBe("done");
    expect(steps.find((s) => s.key === "reingreso")?.state).toBe("pending");
  });
});

describe("ReentryBlockedView (1.5)", () => {
  it("letrero rojo + punto de reunión + labels normativos SOLO del backend", async () => {
    const v = await render(
      <ReentryBlockedView
        assemblyPoint={{
          asset_id: "a-1",
          kind: "assembly_point",
          title: "Explanada norte",
          description: "Frente al acceso 2",
          zone_id: null,
          content_type: null,
          url: null,
          updated_at: "2026-07-16T10:00:00Z",
        }}
        complianceLabels={{ marco: "Texto normativo del tenant" }}
        timeline={reentryTimeline(BASE)}
      />,
    );
    expect(v.getByTestId("reentry-sign")).toHaveTextContent(/REINGRESO PROHIBIDO/);
    expect(v.getByTestId("assembly-point")).toHaveTextContent(/Explanada norte/);
    expect(v.getByTestId("compliance-labels")).toHaveTextContent(/Texto normativo del tenant/);
  });

  it("sin labels del tenant: NADA normativo en pantalla (GATE-LEGAL honesto)", async () => {
    const v = await render(
      <ReentryBlockedView
        assemblyPoint={null}
        complianceLabels={{}}
        timeline={reentryTimeline(BASE)}
      />,
    );
    expect(v.queryByTestId("compliance-labels")).toBeNull();
    expect(v.queryByTestId("assembly-point")).toBeNull();
  });
});
