// [T-5.16 · D-28] La tipología ENSEÑA su banda; no la aplica.
//
// La aserción que gobierna el archivo: el texto que acompaña al desplegable
// tiene que decir que la banda **no se aplica al guardar**. Sin esa frase, un
// operador que elige «Industrial» y ve «0.080–0.120 g» al lado se va creyendo
// que acaba de re-armar el edificio — y no lo ha hecho, ni debe: eso se publica
// y se firma aparte (`D-28`).

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useBuildingTypes: vi.fn() }));
vi.mock("./useBuildingTypes", async () => ({
  ...(await vi.importActual<typeof import("./useBuildingTypes")>("./useBuildingTypes")),
  useBuildingTypes: mocks.useBuildingTypes,
}));

import { expectFourStates, type UiState } from "../../test-utils/states";
import BuildingTypeField from "./BuildingTypeField";
import { BUILDING_TYPES_STALE_MS } from "./useBuildingTypes";

const NOW = Date.now();

const CAT = {
  resuelve_umbrales: false,
  por_que_no_resuelve: ["a", "b", "c"],
  sin_referencia_de_pgv: "el blueprint no publica PGV por tipología",
  items: [
    { value: "hospital", label: "Hospital", banda: { pga_watch_g: 0.04, pga_trip_g: 0.06 } },
    { value: "industrial", label: "Industrial", banda: { pga_watch_g: 0.08, pga_trip_g: 0.12 } },
    {
      value: "universidad",
      label: "Universidad",
      banda: null,
      sin_banda_por_que: "el blueprint no publica banda para universidades; se calibra en sitio",
    },
  ],
};

function datos(over: Record<string, unknown> = {}) {
  return { catalog: CAT, loading: false, readError: false, dataUpdatedAt: NOW, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useBuildingTypes.mockReturnValue(datos());
});

describe("BuildingTypeField", () => {
  it("ofrece el catálogo del servidor, con SIN CLASIFICAR como opción real", () => {
    render(<BuildingTypeField value="" onChange={vi.fn()} />);
    const select = screen.getByTestId("site-building-type") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual([
      "",
      "hospital",
      "industrial",
      "universidad",
    ]);
  });

  it("con un tipo elegido enseña su banda Y dice que NO se aplica al guardar", () => {
    render(<BuildingTypeField value="industrial" onChange={vi.fn()} />);
    const hint = screen.getByTestId("site-banda-referencia");
    expect(hint).toHaveTextContent("cautela 0.080 g");
    expect(hint).toHaveTextContent("disparo 0.120 g");
    expect(hint).toHaveTextContent(/NO se aplica al guardar/i);
  });

  it("un tipo SIN banda dice por qué, en vez de enseñar la de hospital", () => {
    // Es el defecto que abre la ficha: toda la flota corriendo 0.040–0.060 g.
    render(<BuildingTypeField value="universidad" onChange={vi.fn()} />);
    const hint = screen.getByTestId("site-banda-referencia");
    expect(hint).toHaveTextContent(/se calibra en sitio/);
    expect(hint).not.toHaveTextContent("0.040");
  });

  it("sin tipo elegido no inventa ninguna banda", () => {
    render(<BuildingTypeField value="" onChange={vi.fn()} />);
    expect(screen.getByTestId("site-banda-referencia")).toHaveTextContent(/Sin tipo elegido/);
  });

  it("elegir un tipo avisa hacia arriba, no guarda nada por su cuenta", () => {
    const onChange = vi.fn();
    render(<BuildingTypeField value="" onChange={onChange} />);
    fireEvent.change(screen.getByTestId("site-building-type"), { target: { value: "hospital" } });
    expect(onChange).toHaveBeenCalledWith("hospital");
  });

  it("declara los cuatro estados obligatorios", () => {
    // El de ERROR es el que importa: un desplegable con solo «SIN CLASIFICAR»
    // se lee como «no hay tipos», que es lo contrario de «no se pudieron leer».
    const byState: Record<UiState, Record<string, unknown>> = {
      loading: { loading: true },
      error: { readError: true, catalog: null },
      empty: { catalog: { ...CAT, items: [] } },
      // Un catálogo de hace más de una hora: se conserva y se declara viejo.
      stale: { dataUpdatedAt: NOW - BUILDING_TYPES_STALE_MS - 60_000 },
    };
    expectFourStates((state) => {
      mocks.useBuildingTypes.mockReturnValue(datos(byState[state]));
      return <BuildingTypeField value="" onChange={vi.fn()} />;
    });
  });
});
