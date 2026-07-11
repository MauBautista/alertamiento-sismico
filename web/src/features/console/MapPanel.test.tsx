import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

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
    // setStyle borra el estilo previo: las sources desaparecen hasta que el
    // siguiente style.load las re-agregue (semántica real de MapLibre).
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

import MapPanel, {
  FALLBACK_STYLE,
  criticalFeatures,
  pulseAt,
  siteSeverity,
  sitesToFeatureCollection,
} from "./MapPanel";

function site(id: string, over: Partial<MapSiteState> = {}): MapSiteState {
  return {
    site_id: id,
    tenant_id: "t-1",
    name: `Sitio ${id}`,
    criticality: "high",
    lon: -98.3,
    lat: 19.06,
    last_bucket: null,
    max_pga_g: null,
    max_pgv_cms: null,
    open_incident: null,
    ...over,
  };
}

const CRITICAL = site("crit", {
  open_incident: {
    incident_id: "i-1",
    severity: "critical",
    state: "open",
    opened_at: "2026-07-08T10:00:00Z",
  },
});

describe("pulseAt (puro) — opacidad SIEMPRE válida para MapLibre (0..1)", () => {
  it("delta negativo del rAF (vsync previo al start) no produce opacidad > 1", () => {
    // Regresión del bug cazado por el smoke de navegador: 1 - phase daba
    // 1.0021… y MapLibre rechaza >1. El delta se clampa a 0.
    const p = pulseAt(-2.1);
    expect(p.strokeOpacity).toBeLessThanOrEqual(1);
    expect(p.strokeOpacity).toBe(1);
    expect(p.radius).toBe(15);
  });

  it("barrido de un periodo completo se mantiene en rango", () => {
    for (let d = 0; d <= 1600; d += 37) {
      const { radius, strokeOpacity } = pulseAt(d);
      expect(strokeOpacity).toBeGreaterThanOrEqual(0);
      expect(strokeOpacity).toBeLessThanOrEqual(1);
      expect(radius).toBeGreaterThanOrEqual(15);
      expect(radius).toBeLessThanOrEqual(60);
    }
  });
});

describe("builders del mapa (puros)", () => {
  it("severidad efectiva: incidente abierto manda; sin incidente = ok", () => {
    expect(siteSeverity(site("a"))).toBe("ok");
    expect(siteSeverity(CRITICAL)).toBe("critical");
  });

  it("GeoJSON con color y flag critical por sitio", () => {
    const fc = sitesToFeatureCollection([site("a"), CRITICAL]);
    expect(fc.features).toHaveLength(2);
    expect(fc.features[0].properties).toMatchObject({ color: "#00E676", critical: false });
    expect(fc.features[1].properties).toMatchObject({ color: "#FF5252", critical: true });
    expect(criticalFeatures([site("a"), CRITICAL]).features).toHaveLength(1);
  });
});

describe("MapPanel", () => {
  beforeEach(() => {
    mocks.handlers.clear();
    mocks.sources.clear();
    vi.clearAllMocks();
  });

  it("crea el mapa, agrega capas al style.load y despacha el clic en site-core", () => {
    const onSelectSite = vi.fn();
    render(<MapPanel sites={[CRITICAL]} onSelectSite={onSelectSite} />);
    expect(mocks.Map).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();

    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    expect(mocks.map.addSource).toHaveBeenCalledWith("sites", expect.anything());
    expect(mocks.map.addSource).toHaveBeenCalledWith("critical", expect.anything());
    expect(mocks.map.addLayer).toHaveBeenCalled();

    mocks.handlers.get("click:site-core")?.({
      features: [{ properties: { site_id: "crit" } }],
    });
    expect(onSelectSite).toHaveBeenCalledWith("crit");
  });

  // Aquí vivían "mmi-severa" (55px) y "mmi-alta" (100px), rotuladas INTENSIDAD
  // MMI y conectadas a NADA. Como `circle-radius` de MapLibre es en PÍXELES DE
  // PANTALLA, el mismo anillo afirmaba ~22 km de radio en zoom 8.5 y ~1 km en
  // zoom 13: la banda cambiaba de significado físico con cada zoom. Sin
  // magnitud (NULL) ni PGA calibrado no hay isosista honesta que dibujar, así
  // que no se dibuja ninguna (regla de oro 7). El mapa de intensidades es el
  // mini-ShakeMap del BLUEPRINT §14 — fase futura.
  it("NO pinta bandas de intensidad: ni capas MMI ni una leyenda que prometa una escala inexistente", () => {
    render(<MapPanel sites={[CRITICAL]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });

    const layerIds: string[] = mocks.map.addLayer.mock.calls.map(
      (call) => (call[0] as { id: string }).id,
    );
    expect(layerIds.some((id) => id.startsWith("mmi"))).toBe(false);
    expect(screen.queryByText(/INTENSIDAD MMI/i)).not.toBeInTheDocument();
    expect(screen.getByText(/SEVERIDAD DEL SITIO/i)).toBeInTheDocument();
  });

  it("estilo remoto caído ⇒ degrada al estilo LOCAL, re-cuelga las capas y lo declara", () => {
    render(<MapPanel sites={[CRITICAL]} onSelectSite={vi.fn()} />);

    act(() => {
      mocks.handlers.get("error")?.(); // el estilo inicial nunca cargó
    });
    expect(mocks.map.setStyle).toHaveBeenCalledWith(FALLBACK_STYLE);
    expect(screen.getByTestId("map-degraded")).toHaveTextContent("SIN MAPA BASE");

    // el style.load del fallback re-agrega sources/capas: los sitios siguen vivos
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    expect(mocks.map.addSource).toHaveBeenCalledWith("sites", expect.anything());
  });

  it("un error DESPUÉS de cargar (tile suelto) NO borra el mapa base ya renderizado", () => {
    render(<MapPanel sites={[CRITICAL]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
      mocks.handlers.get("error")?.();
    });
    expect(mocks.map.setStyle).not.toHaveBeenCalled();
    expect(screen.queryByTestId("map-degraded")).toBeNull();
  });

  it("re-dimensionar el contenedor dispara map.resize() (canvas jamás en 0×0)", () => {
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => {
        cb(0);
        return 0;
      });
    try {
      render(<MapPanel sites={[]} onSelectSite={vi.fn()} />);
      // NO se dispara style.load: el pulso (rAF recursivo) no debe arrancar aquí.
      (
        globalThis as unknown as { __triggerResizeObservers: () => void }
      ).__triggerResizeObservers();
      expect(mocks.map.resize).toHaveBeenCalled();
    } finally {
      rafSpy.mockRestore();
    }
  });
});
