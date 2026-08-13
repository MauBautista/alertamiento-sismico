import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ComplianceClaimOut, ComplianceDocOut, ForensicsOut } from "@takab/sdk";

import { expectFourStates } from "../../test-utils/states";
import ComplianceDeclared from "./ComplianceDeclared";
import type { ForensicsState } from "./useForensics";

const NOTICE = "TAKAB no verifica ni certifica.";
const ABSENCE = "SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE · la ausencia no es conformidad.";
const ILEGIBLE = "ETIQUETAS ILEGIBLES · no se transcribe nada.";

// [T-2.82.b] Los fixtures van TIPADOS contra el contrato, no sueltos. Es lo que
// sustituye a la vieja «guarda de compilación» de este fichero, que esperaba a
// que el SDK publicara `compliance` — ya lo publica. Si el contrato gana un
// campo requerido, estos literales dejan de compilar y el `typecheck` lo dice;
// un fixture `unknown` habría seguido en verde mintiendo sobre el cable.
const CLAIM: ComplianceClaimOut = {
  key: "regulatory_framework",
  title: "Marco al que el cliente declara estar sujeto",
  claim: "Reglamento de Construcciones del DF, Título Sexto",
  reference: "Gaceta Oficial del DF, 29/01/2004",
};

function forensics(compliance: unknown, over: Partial<ForensicsState> = {}): ForensicsState {
  const data = {
    incident_id: "i-1",
    window_from: "2026-08-07T10:00:00Z",
    window_to: "2026-08-07T10:05:00Z",
    channels: [],
    felt_band: "unknown",
    station_count: 0,
    peers: [],
    sensors: [],
    calibrated: false,
    compliance,
  } as unknown as ForensicsOut;
  // [T-2.82.a] `dataUpdatedAt`/`staleSince` son parte del contrato del hook: un
  // panel de esta pantalla tiene que poder decir que su dato está viejo. Aquí
  // el dato es fresco salvo que la prueba diga otra cosa.
  return {
    data,
    loading: false,
    error: null,
    refetch: vi.fn(),
    dataUpdatedAt: Date.now(),
    staleSince: null,
    ...over,
  };
}

const EMPTY_DOC: ComplianceDocOut = {
  provenance: "declared_by_tenant",
  notice: NOTICE,
  items: [],
  notes: [ABSENCE],
  unreadable: null,
};

describe("ComplianceDeclared · lo que ve QUIEN FIRMA", () => {
  it("materializa los cuatro estados (regla de oro 7)", () => {
    expectFourStates((state) =>
      state === "loading" ? (
        <ComplianceDeclared forensics={forensics(EMPTY_DOC, { loading: true, data: undefined })} />
      ) : state === "error" ? (
        <ComplianceDeclared
          forensics={forensics(EMPTY_DOC, { error: "GET /forensics falló (503)", data: undefined })}
        />
      ) : state === "empty" ? (
        <ComplianceDeclared forensics={forensics(EMPTY_DOC)} />
      ) : (
        <ComplianceDeclared
          forensics={forensics({ ...EMPTY_DOC, items: [CLAIM], notes: [NOTICE] })}
          staleSince={Date.parse("2026-08-07T10:00:00Z")}
        />
      ),
    );
  });

  it("el firmante ve la afirmación, su clase y dónde lo dice", () => {
    render(
      <ComplianceDeclared
        forensics={forensics({ ...EMPTY_DOC, items: [CLAIM], notes: [NOTICE] })}
      />,
    );
    const row = screen.getByTestId("declared-claim");
    expect(within(row).getByText(CLAIM.title)).toBeTruthy();
    expect(within(row).getByText(CLAIM.claim)).toBeTruthy();
    expect(within(row).getByText(new RegExp(CLAIM.reference))).toBeTruthy();
  });

  it("el firmante ve SIEMPRE de quién es la afirmación", () => {
    render(
      <ComplianceDeclared
        forensics={forensics({ ...EMPTY_DOC, items: [CLAIM], notes: [NOTICE] })}
      />,
    );
    expect(screen.getByTestId("declared-provenance").textContent).toContain(
      "DECLARACIÓN DEL CLIENTE",
    );
  });

  it("el deslinde lo dicta el servidor, no la pantalla", () => {
    render(
      <ComplianceDeclared
        forensics={forensics({ ...EMPTY_DOC, items: [CLAIM], notes: [NOTICE] })}
      />,
    );
    expect(screen.getByTestId("declared-notes").textContent).toBe(NOTICE);
  });

  it("sin etiquetas dice que no hay ninguna DECLARADA, no que todo esté en orden", () => {
    render(<ComplianceDeclared forensics={forensics(EMPTY_DOC)} />);
    const empty = screen.getByTestId("declared-card").querySelector('[data-state="empty"]');
    expect(empty?.textContent).toContain(ABSENCE);
    expect(screen.queryByTestId("declared-claim")).toBeNull();
  });

  it("un registro ilegible se rotula y no se transcribe", () => {
    render(
      <ComplianceDeclared
        forensics={forensics({ ...EMPTY_DOC, notes: [ILEGIBLE], unreadable: ILEGIBLE })}
      />,
    );
    expect(screen.getByTestId("declared-unreadable").textContent).toContain(ILEGIBLE);
    expect(screen.queryByTestId("declared-claim")).toBeNull();
  });

  it("si el servidor NO manda el bloque, se dice — no se finge que no hay nada", () => {
    // Un servidor viejo (sin T-2.82) no trae `compliance`. Pintar "sin marco
    // declarado" sería afirmar sobre el cliente algo que nadie ha comprobado.
    render(<ComplianceDeclared forensics={forensics(undefined)} />);
    const box = screen.getByTestId("declared-card");
    expect(box.textContent).toMatch(/NO DISPONIBLE/);
    expect(box.textContent).not.toMatch(/SIN MARCO NORMATIVO DECLARADO/);
  });

  it("[T-2.82.b] el bloque que se pinta es el del contrato, sin tipo local de por medio", () => {
    // Lo que antes era una guarda de compilación esperando al SDK ahora es una
    // afirmación sobre el contrato YA publicado: `compliance` es propio de
    // `ForensicsOut` y su forma es `ComplianceDocOut`. La asignación de abajo es
    // el ancla — si el contrato dejara de declararlo, no compilaría.
    const { data } = forensics(EMPTY_DOC);
    if (data === undefined) throw new Error("fixture sin `data`");
    const doc: ComplianceDocOut = data.compliance;
    expect(doc.notes).toEqual([ABSENCE]);
  });
});
