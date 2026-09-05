// [T-5.12] Clasificar un incidente, y la tasa que sale de hacerlo.
//
// Lo que fija:
//  1. **Corregir INSERTA**: la pantalla manda `supersedes_id` con la vigente, y
//     el historial enseña las dos. No hay «editar» porque la base no lo permite.
//  2. **Los sin clasificar salen SIEMPRE**, junto al porcentaje. Un porcentaje
//     calculado sobre lo clasificado, con lo no clasificado escondido, se lee
//     como una medición y es una muestra sesgada por quién tuvo tiempo.
//  3. **Sin nada clasificado la tasa dice S/D, no 0 %.** Un cero afirmaría que no
//     hubo falsos positivos; lo que pasa es que nadie miró.
//  4. Los cuatro estados obligatorios de las dos superficies (regla de oro 7).

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useClassification: vi.fn(), useClassificationStats: vi.fn() }));
vi.mock("./useClassification", async () => {
  const real = await vi.importActual<typeof import("./useClassification")>("./useClassification");
  return {
    ...real,
    useClassification: mocks.useClassification,
    useClassificationStats: mocks.useClassificationStats,
  };
});

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import { ClassificationPanel, FalsePositiveRate, tasaLegible } from "./ClassificationPanel";

const NOW = Date.parse("2026-09-02T18:00:00Z");

const VIGENTE = {
  classification_id: "c-1",
  incident_id: "i-1",
  classification: "real",
  note: "",
  classified_by: "u-1",
  classified_at: "2026-09-02T17:00:00Z",
  supersedes_id: null,
  current: true,
};

function cadena(over: Record<string, unknown> = {}) {
  return {
    items: [],
    current: null,
    loading: false,
    readError: false,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    clasificar: vi.fn(),
    pending: false,
    ...over,
  };
}

function tasa(over: Record<string, unknown> = {}) {
  return {
    stats: {
      since: "2026-06-04T18:00:00Z",
      until: "2026-09-02T18:00:00Z",
      total: 10,
      unclassified: 4,
      by_classification: { real: 4, falso_positivo: 2, prueba: 0, indeterminado: 0 },
      false_positive_rate: 2 / 6,
    },
    loading: false,
    readError: false,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  resetSessionStoreForTests();
  useSessionStore.setState({ me: ME_FIXTURES.soc_operator });
  mocks.useClassification.mockReturnValue(cadena());
  mocks.useClassificationStats.mockReturnValue(tasa());
});

afterEach(() => vi.clearAllMocks());

describe("ClassificationPanel", () => {
  it("sin clasificar lo dice, y no inventa una clasificación", () => {
    render(<ClassificationPanel incidentId="i-1" />);
    expect(screen.getByTestId("classification-current")).toHaveTextContent("SIN CLASIFICAR");
  });

  it("ofrece las cuatro del catálogo, INDETERMINADO incluido como una más", () => {
    // No es el estado donde caen los que nadie miró: se elige como las otras.
    render(<ClassificationPanel incidentId="i-1" />);
    for (const v of ["real", "falso_positivo", "prueba", "indeterminado"]) {
      expect(screen.getByTestId(`classify-${v}`)).toBeInTheDocument();
    }
  });

  it("clasificar por primera vez no sustituye a nadie", () => {
    const c = cadena();
    mocks.useClassification.mockReturnValue(c);
    render(<ClassificationPanel incidentId="i-1" />);
    fireEvent.click(screen.getByTestId("classify-falso_positivo"));
    expect(c.clasificar).toHaveBeenCalledWith({
      classification: "falso_positivo",
      supersedesId: undefined,
    });
  });

  it("corregir SUSTITUYE a la vigente: no edita, inserta", () => {
    const c = cadena({ items: [VIGENTE], current: VIGENTE });
    mocks.useClassification.mockReturnValue(c);
    render(<ClassificationPanel incidentId="i-1" />);
    fireEvent.click(screen.getByTestId("classify-falso_positivo"));
    expect(c.clasificar).toHaveBeenCalledWith({
      classification: "falso_positivo",
      supersedesId: "c-1",
    });
  });

  it("con una corrección, el historial enseña las DOS", () => {
    const previa = { ...VIGENTE, classification_id: "c-0", current: false };
    const nueva = { ...VIGENTE, classification_id: "c-1", classification: "falso_positivo" };
    mocks.useClassification.mockReturnValue(cadena({ items: [nueva, previa], current: nueva }));
    render(<ClassificationPanel incidentId="i-1" />);
    const hist = screen.getByTestId("classification-history");
    expect(hist).toHaveTextContent("VIGENTE");
    expect(hist).toHaveTextContent("SUSTITUIDA");
  });

  it("quien no puede clasificar no ve botones", () => {
    useSessionStore.setState({ me: ME_FIXTURES.inspector });
    mocks.useClassification.mockReturnValue(cadena({ items: [VIGENTE], current: VIGENTE }));
    render(<ClassificationPanel incidentId="i-1" />);
    expect(screen.queryByTestId("classify-real")).toBeNull();
  });

  it("declara los cuatro estados obligatorios", () => {
    const byState: Record<UiState, Record<string, unknown>> = {
      loading: { loading: true },
      error: { readError: true },
      empty: {},
      stale: { items: [VIGENTE], current: VIGENTE, readError: true },
    };
    useSessionStore.setState({ me: ME_FIXTURES.inspector }); // sin botones: `empty` es empty
    expectFourStates((state) => {
      mocks.useClassification.mockReturnValue(cadena(byState[state]));
      return <ClassificationPanel incidentId="i-1" />;
    });
  });
});

describe("FalsePositiveRate", () => {
  it("pinta la tasa Y cuántos hay sin clasificar", () => {
    render(<FalsePositiveRate />);
    expect(screen.getByTestId("fp-rate-value")).toHaveTextContent("33.3 %");
    expect(screen.getByTestId("fp-unclassified")).toHaveTextContent("4 DE 10 SIN CLASIFICAR");
  });

  it("sin nada clasificado dice S/D y por qué, jamás 0 %", () => {
    mocks.useClassificationStats.mockReturnValue(
      tasa({
        stats: {
          since: "2026-06-04T18:00:00Z",
          until: "2026-09-02T18:00:00Z",
          total: 7,
          unclassified: 7,
          by_classification: { real: 0, falso_positivo: 0, prueba: 0, indeterminado: 0 },
          false_positive_rate: null,
        },
      }),
    );
    render(<FalsePositiveRate />);
    expect(screen.getByTestId("fp-rate-value")).toHaveTextContent("S/D");
    expect(screen.getByTestId("false-positive-rate")).toHaveTextContent("nadie miró");
  });

  it("declara los cuatro estados obligatorios", () => {
    const byState: Record<UiState, Record<string, unknown>> = {
      loading: { loading: true },
      error: { readError: true, stats: null },
      empty: { stats: { ...tasa().stats, total: 0, unclassified: 0 } },
      stale: { readError: true },
    };
    expectFourStates((state) => {
      mocks.useClassificationStats.mockReturnValue(tasa(byState[state]));
      return <FalsePositiveRate />;
    });
  });
});

describe("tasaLegible", () => {
  it("sin dato dice S/D, no cero", () => {
    expect(tasaLegible(null)).toBe("S/D");
    expect(tasaLegible(0)).toBe("0.0 %");
    expect(tasaLegible(0.1234)).toBe("12.3 %");
  });
});
