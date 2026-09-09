// [T-2.28] Capa de catálogo histórico del MapPanel: toggle, datos y clic.
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogEarthquakeOut } from "@takab/sdk";

const mocks = vi.hoisted(() => {
  const handlers = new Map<string, (event?: unknown) => void>();
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  const map = {
    on: vi.fn((event: string, layerOrCb: unknown, cb?: (event?: unknown) => void) => {
      if (typeof layerOrCb === "function") handlers.set(event, layerOrCb as () => void);
      else if (cb) handlers.set(`${event}:${layerOrCb as string}`, cb);
    }),
    addSource: vi.fn((id: string) => {
      sources.set(id, { setData: vi.fn() });
    }),
    addLayer: vi.fn(),
    getSource: vi.fn((id: string) => sources.get(id)),
    getLayer: vi.fn(() => undefined),
    setStyle: vi.fn(() => {
      sources.clear();
    }),
    setPaintProperty: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
  };
  return { handlers, sources, map, Map: vi.fn(() => map) };
});

vi.mock("maplibre-gl", () => ({ default: { Map: mocks.Map } }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import MapPanel, { CATALOG_COLOR, catalogToFeatureCollection } from "./MapPanel";

const QUAKES: CatalogEarthquakeOut[] = [
  {
    ref_id: "r-19s",
    catalog_key: "SSN-2017-09-19-PUE",
    magnitude: 7.1,
    depth_km: 57,
    lat: 18.4,
    lon: -98.72,
    origin_time: "2017-09-19T18:14:00Z",
    place: "Axochiapan, Morelos",
    source: "SSN",
    source_ref: "x",
    notes: null,
  },
  {
    ref_id: "r-19s-usgs",
    catalog_key: "USGS-us2000ar20",
    magnitude: 7.1,
    depth_km: 48,
    lat: 18.55,
    lon: -98.49,
    origin_time: "2017-09-19T18:14:00Z",
    place: "Puebla twin (USGS)",
    source: "USGS",
    source_ref: "y",
    notes: null,
  },
];

beforeEach(() => {
  mocks.handlers.clear();
  mocks.sources.clear();
  vi.clearAllMocks();
});

describe("catalogToFeatureCollection", () => {
  it("pinta AMBOS gemelos SSN/USGS y marca el seleccionado", () => {
    const fc = catalogToFeatureCollection(QUAKES, "r-19s");
    expect(fc.features).toHaveLength(2);
    expect(fc.features[0].properties).toMatchObject({
      ref_id: "r-19s",
      label: `M 7.1 · 2017 · SSN`,
      selected: true,
    });
    expect(fc.features[1].properties["selected"]).toBe(false);
    expect(CATALOG_COLOR).toBe("#7CE7FF");
  });
});

describe("MapPanel · capa catálogo", () => {
  const renderPanel = (selected: string | null, onSelectCatalog = vi.fn()) => {
    render(
      <MapPanel
        sites={[]}
        epicenters={[]}
        onSelectSite={vi.fn()}
        catalog={QUAKES}
        selectedCatalogId={selected}
        onSelectCatalog={onSelectCatalog}
      />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    return onSelectCatalog;
  };

  it("la capa nace OFF y el toggle la enciende (setData con los 13 no antes)", () => {
    renderPanel(null);
    const toggle = screen.getByTestId("catalog-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    act(() => {
      toggle.click();
    });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    const calls = mocks.sources.get("catalog")?.setData.mock.calls ?? [];
    const last = calls[calls.length - 1]?.[0] as ReturnType<typeof catalogToFeatureCollection>;
    expect(last.features).toHaveLength(2);
  });

  it("clic en un ◇ del catálogo emite su ref_id", () => {
    const spy = renderPanel(null);
    act(() => {
      mocks.handlers.get("click:catalog-mark")?.({
        features: [{ properties: { ref_id: "r-19s" } }],
      });
    });
    expect(spy).toHaveBeenCalledWith("r-19s");
  });

  it("con sismo seleccionado y capa ON muestra el hint del paso 2", () => {
    renderPanel("r-19s");
    act(() => {
      screen.getByTestId("catalog-toggle").click();
    });
    expect(screen.getByTestId("catalog-step2")).toHaveTextContent(
      "PASO 2 · SELECCIONE UNA ESTACIÓN EN EL MAPA",
    );
  });
});

/**
 * [T-6.14] EL MAPA ARMADO. Con un sismo del catálogo elegido, el siguiente clic
 * en una estación abre la COMPARATIVA en vez del detalle. El aviso existía —el
 * «PASO 2» de arriba— pero vivía en la tercera leyenda, abajo a la izquierda,
 * y encima estaba condicionado a que la capa siguiera encendida: apagar el
 * histórico borraba el aviso y dejaba el mapa armado EN SILENCIO. El operador
 * pincha una estación esperando su detalle y le sale otra pantalla.
 */
describe("MapPanel · la comparativa armada se DECLARA y se puede desarmar", () => {
  const renderPanel = (selected: string | null, onSelectCatalog = vi.fn()) => {
    render(
      <MapPanel
        sites={[]}
        epicenters={[]}
        onSelectSite={vi.fn()}
        catalog={QUAKES}
        selectedCatalogId={selected}
        onSelectCatalog={onSelectCatalog}
      />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    return onSelectCatalog;
  };

  it("armado, el mapa lo dice en su esquina de estado y nombra el sismo", () => {
    renderPanel("r-19s");
    const aviso = screen.getByTestId("map-armado");
    expect(aviso).toHaveAttribute("role", "status");
    expect(aviso).toHaveTextContent(/COMPARATIVA ARMADA/);
    // Qué va a pasar con el próximo clic, dicho antes de que pase.
    expect(aviso).toHaveTextContent(/estación/i);
    // Y de qué sismo se está hablando: el mapa tiene 13 ◇ iguales.
    expect(aviso).toHaveTextContent(/M 7.1/);
  });

  it("sin armar no hay aviso: no se alarma por lo que no está pasando", () => {
    renderPanel(null);
    expect(screen.queryByTestId("map-armado")).not.toBeInTheDocument();
  });

  it("el aviso vive AUNQUE la capa esté apagada (armado es armado)", () => {
    // Defensa en profundidad: el desarmado de abajo es lo que evita este caso,
    // pero si un día el padre arma sin capa, el mapa no puede callarse.
    const { rerender } = render(
      <MapPanel sites={[]} epicenters={[]} onSelectSite={vi.fn()} catalog={QUAKES} />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    rerender(
      <MapPanel
        sites={[]}
        epicenters={[]}
        onSelectSite={vi.fn()}
        catalog={QUAKES}
        selectedCatalogId="r-19s"
        onSelectCatalog={vi.fn()}
      />,
    );
    expect(screen.getByTestId("map-armado")).toBeInTheDocument();
  });

  it("APAGAR el histórico desarma la comparativa", () => {
    const spy = renderPanel("r-19s");
    act(() => {
      screen.getByTestId("catalog-toggle").click(); // ON
    });
    expect(spy).not.toHaveBeenCalled();
    act(() => {
      screen.getByTestId("catalog-toggle").click(); // OFF
    });
    expect(spy).toHaveBeenCalledWith(null);
  });

  it("el botón de capas hace lo MISMO que el de la leyenda", () => {
    // Son dos mandos del mismo interruptor; que uno desarme y el otro no sería
    // peor que no desarmar ninguno.
    const spy = renderPanel("r-19s");
    act(() => {
      screen.getByTestId("layer-catalog").click(); // ON
      screen.getByTestId("layer-catalog").click(); // OFF
    });
    expect(spy).toHaveBeenCalledWith(null);
  });

  it("CANCELAR desde el propio aviso desarma", () => {
    const spy = renderPanel("r-19s");
    act(() => {
      screen.getByTestId("map-desarmar").click();
    });
    expect(spy).toHaveBeenCalledWith(null);
  });

  it("encender el histórico no desarma nada", () => {
    const spy = renderPanel(null);
    act(() => {
      screen.getByTestId("catalog-toggle").click();
    });
    expect(spy).not.toHaveBeenCalled();
  });
});
