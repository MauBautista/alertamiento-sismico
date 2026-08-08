import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TenantOut } from "@takab/sdk";

import { expectFourStates } from "../../test-utils/states";
import ComplianceLabelsCard from "./ComplianceLabelsCard";
import type { ComplianceData, ComplianceMutation, ComplianceDoc } from "./useComplianceLabels";

const mocks = vi.hoisted(() => ({
  useComplianceLabels: vi.fn(),
  useSaveComplianceLabels: vi.fn(),
}));

vi.mock("./useComplianceLabels", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./useComplianceLabels")>()),
  useComplianceLabels: mocks.useComplianceLabels,
  useSaveComplianceLabels: mocks.useSaveComplianceLabels,
}));

const TENANT: TenantOut = {
  tenant_id: "t-1",
  code: "HOSP",
  name: "Hospital Uno",
  isolation_mode: "logical",
  vertical: null,
  visibility: "private",
  status: "active",
  plan_code: "mvp",
  row_version: "774100",
  created_at: "2026-01-01T00:00:00Z",
};

const NOTICE = "TAKAB no verifica ni certifica.";
const ABSENCE = "SIN MARCO NORMATIVO DECLARADO · la ausencia no significa cumplimiento.";
const ILEGIBLE = "ETIQUETAS ILEGIBLES · no se transcribe nada.";

const CLAIM = {
  key: "regulatory_framework",
  title: "Marco al que el cliente declara estar sujeto",
  claim: "Reglamento de Construcciones del DF, Título Sexto",
  reference: "Gaceta Oficial del DF, 29/01/2004",
};

function doc(over: Partial<ComplianceDoc> = {}): ComplianceDoc {
  return {
    tenant_id: "t-1",
    provenance: "declared_by_tenant",
    notice: NOTICE,
    items: [],
    notes: [ABSENCE],
    unreadable: null,
    updated_at: null,
    updated_by: null,
    ...over,
  };
}

function data(over: Partial<ComplianceData> = {}): ComplianceData {
  return {
    doc: doc(),
    loading: false,
    error: null,
    staleSince: null,
    refetch: vi.fn(),
    ...over,
  };
}

function mutation(over: Partial<ComplianceMutation> = {}): ComplianceMutation {
  return { save: vi.fn(), pending: false, error: null, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useComplianceLabels.mockReturnValue(data());
  mocks.useSaveComplianceLabels.mockReturnValue(mutation());
});

function card(canEdit = true) {
  return <ComplianceLabelsCard tenant={TENANT} canEdit={canEdit} />;
}

describe("ComplianceLabelsCard · los cuatro estados (regla de oro 7)", () => {
  it("materializa loading, error, empty y stale", () => {
    expectFourStates((state) => {
      mocks.useComplianceLabels.mockReturnValue(
        data({
          loading: state === "loading",
          error: state === "error" ? "GET /compliance-labels falló (503)" : null,
          staleSince: state === "stale" ? Date.parse("2026-08-07T10:00:00Z") : null,
          doc: state === "stale" ? doc({ items: [CLAIM], notes: [NOTICE] }) : doc(),
        }),
      );
      return card();
    });
  });

  it("el VACÍO se lee como ausencia declarada, jamás como conformidad", () => {
    render(card());
    const empty = screen.getByTestId("compliance-card").querySelector('[data-state="empty"]');
    expect(empty?.textContent).toContain(ABSENCE);
  });
});

describe("ComplianceLabelsCard · qué se ve", () => {
  it("cada afirmación sale con su CLASE y con dónde lo dice", () => {
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ items: [CLAIM], notes: [NOTICE] }) }),
    );
    render(card());
    const row = screen.getByTestId("compliance-claim");
    expect(within(row).getByText(CLAIM.title)).toBeTruthy();
    expect(within(row).getByText(CLAIM.claim)).toBeTruthy();
    expect(within(row).getByText(new RegExp(CLAIM.reference))).toBeTruthy();
  });

  it("el deslinde del SERVIDOR se pinta tal cual, no uno inventado aquí", () => {
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ items: [CLAIM], notes: [NOTICE] }) }),
    );
    render(card());
    expect(screen.getByTestId("compliance-notes").textContent).toBe(NOTICE);
  });

  it("un registro ilegible se rotula y NO se transcribe nada", () => {
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ items: [], notes: [ILEGIBLE], unreadable: ILEGIBLE }) }),
    );
    render(card());
    expect(screen.getByTestId("compliance-unreadable").textContent).toContain(ILEGIBLE);
    expect(screen.queryByTestId("compliance-claim")).toBeNull();
  });

  it("la tarjeta declara SIEMPRE que es una declaración del cliente", () => {
    // También cuando no hay nada declarado: el rótulo es del apartado, no del dato.
    render(card());
    expect(screen.getByTestId("compliance-provenance").textContent).toContain(
      "DECLARACIÓN DEL CLIENTE",
    );
  });
});

describe("ComplianceLabelsCard · quién edita", () => {
  it("sin permiso no hay formulario", () => {
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ items: [CLAIM], notes: [NOTICE] }) }),
    );
    render(card(false));
    expect(screen.queryByTestId("compliance-form")).toBeNull();
    // …pero sí se LEE: el marco declarado importa a quien no puede tocarlo.
    expect(screen.getByTestId("compliance-claim")).toBeTruthy();
  });

  it("con permiso, añadir manda la afirmación nueva con su referencia", () => {
    const save = vi.fn();
    mocks.useSaveComplianceLabels.mockReturnValue(mutation({ save }));
    render(card());
    fireEvent.change(screen.getByLabelText(/Clase de afirmación/), {
      target: { value: "internal_protocol" },
    });
    fireEvent.change(screen.getByLabelText(/Qué declara el cliente/), {
      target: { value: "Plan interno 2026" },
    });
    fireEvent.change(screen.getByLabelText(/Dónde lo dice/), {
      target: { value: "Acta del comité, 14/03/2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Añadir/ }));
    expect(save).toHaveBeenCalledWith({
      items: [
        {
          key: "internal_protocol",
          claim: "Plan interno 2026",
          reference: "Acta del comité, 14/03/2026",
        },
      ],
      base_updated_at: null,
    });
  });

  it("añadir CONSERVA lo ya declarado (el PUT reemplaza el documento entero)", () => {
    const save = vi.fn();
    mocks.useSaveComplianceLabels.mockReturnValue(mutation({ save }));
    mocks.useComplianceLabels.mockReturnValue(
      data({
        doc: doc({ items: [CLAIM], notes: [NOTICE], updated_at: "2026-08-07T10:00:00Z" }),
      }),
    );
    render(card());
    fireEvent.change(screen.getByLabelText(/Clase de afirmación/), {
      target: { value: "internal_protocol" },
    });
    fireEvent.change(screen.getByLabelText(/Qué declara el cliente/), {
      target: { value: "Plan interno 2026" },
    });
    fireEvent.change(screen.getByLabelText(/Dónde lo dice/), {
      target: { value: "Acta del comité" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Añadir/ }));
    expect(save).toHaveBeenCalledWith({
      items: [
        { key: CLAIM.key, claim: CLAIM.claim, reference: CLAIM.reference },
        { key: "internal_protocol", claim: "Plan interno 2026", reference: "Acta del comité" },
      ],
      base_updated_at: "2026-08-07T10:00:00Z",
    });
  });

  it("sin referencia el botón no deja añadir, y dice por qué", () => {
    render(card());
    fireEvent.change(screen.getByLabelText(/Clase de afirmación/), {
      target: { value: "internal_protocol" },
    });
    fireEvent.change(screen.getByLabelText(/Qué declara el cliente/), {
      target: { value: "Plan interno 2026" },
    });
    const btn = screen.getByRole("button", { name: /Añadir/ });
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(btn.getAttribute("title")).toMatch(/dónde lo dice/i);
  });

  it("sin el texto de la afirmación tampoco deja añadir", () => {
    render(card());
    fireEvent.change(screen.getByLabelText(/Clase de afirmación/), {
      target: { value: "internal_protocol" },
    });
    fireEvent.change(screen.getByLabelText(/Dónde lo dice/), { target: { value: "Acta" } });
    expect(screen.getByRole("button", { name: /Añadir/ }).hasAttribute("disabled")).toBe(true);
  });

  it("el desplegable NO deja teclear una norma: solo clases del catálogo", () => {
    render(card());
    const select = screen.getByLabelText(/Clase de afirmación/) as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    const values = [...select.options].map((o) => o.value).filter(Boolean);
    expect(values.length).toBeGreaterThan(0);
    for (const v of values) {
      expect(v).not.toMatch(/nom|iso|nfpa/i);
    }
  });

  it("un registro ilegible bloquea la edición en vez de pisarlo a ciegas", () => {
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ notes: [ILEGIBLE], unreadable: ILEGIBLE }) }),
    );
    render(card());
    expect(screen.queryByTestId("compliance-form")).toBeNull();
  });

  it("retirar una afirmación manda el resto", () => {
    const save = vi.fn();
    mocks.useSaveComplianceLabels.mockReturnValue(mutation({ save }));
    mocks.useComplianceLabels.mockReturnValue(
      data({ doc: doc({ items: [CLAIM], notes: [NOTICE] }) }),
    );
    render(card());
    fireEvent.click(screen.getByRole("button", { name: /Retirar/ }));
    expect(save).toHaveBeenCalledWith({ items: [], base_updated_at: null });
  });

  it("un error de guardado se muestra, no se traga", () => {
    mocks.useSaveComplianceLabels.mockReturnValue(
      mutation({ error: "SIN PERMISO · solo el dueño de la plataforma carga etiquetas." }),
    );
    render(card());
    expect(screen.getByRole("alert").textContent).toMatch(/SIN PERMISO/);
  });
});
