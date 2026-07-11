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
  epicentersToFeatureCollection,
  FALLBACK_STYLE,
  FELT_COLOR,
  pulseAt,
  sitesToFeatureCollection,
  trippedFeatures,
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
    felt: "unknown",
    felt_pga_g: null,
    felt_pgv_cms: null,
    calibrated: true,
    ...over,
  };
}

/** Edificio que REALMENTE disparó: midió por encima de su umbral. */
const CRITICAL = site("crit", {
  felt: "trip",
  felt_pga_g: 0.12,
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
  it("el color es la SACUDIDA MEDIDA, no la severidad de la alerta", () => {
    // El caso que motiva todo esto: SASMEX abre el incidente en `critical`, pero
    // el edificio no llegó a moverse (`felt: normal`). El punto NO puede ir rojo:
    // el aviso es del canal de alerta, no una medida de este inmueble.
    const avisadoPeroQuieto = site("a", {
      felt: "normal",
      open_incident: {
        incident_id: "i-1",
        severity: "critical",
        state: "open",
        opened_at: "2026-07-08T10:00:00Z",
      },
    });
    const fc = sitesToFeatureCollection([avisadoPeroQuieto]);
    expect(fc.features[0].properties).toMatchObject({
      color: FELT_COLOR.normal,
      felt: "normal",
      tripped: false,
    });
  });

  it("sin dato es GRIS, jamás verde: 'no reportó' no es 'no se movió'", () => {
    const fc = sitesToFeatureCollection([site("a", { felt: "unknown" })]);
    expect(fc.features[0].properties).toMatchObject({ color: FELT_COLOR.unknown });
    expect(FELT_COLOR.unknown).not.toBe(FELT_COLOR.normal);
  });

  it("el pulso marca a los que SUPERARON SU UMBRAL DE DISPARO", () => {
    const tripped = site("t", { felt: "trip" });
    const fc = sitesToFeatureCollection([site("a", { felt: "normal" }), tripped]);
    expect(fc.features[1].properties).toMatchObject({ color: FELT_COLOR.trip, tripped: true });
    expect(trippedFeatures([site("a", { felt: "normal" }), tripped]).features).toHaveLength(1);
  });

  it("el sitio sin calibrar se marca: su PGA es RELATIVO, no una intensidad física", () => {
    const fc = sitesToFeatureCollection([
      site("a", { calibrated: false }),
      site("b", { calibrated: true }),
    ]);
    expect(fc.features[0].properties).toMatchObject({ calibrated: false });
    expect(fc.features[1].properties).toMatchObject({ calibrated: true });
  });

  it("el epicentro es un punto PROPIO, con la magnitud solo si existe", () => {
    const fc = epicentersToFeatureCollection([
      {
        event_id: "e-1",
        source: "ssn",
        lon: -99.1,
        lat: 16.8,
        magnitude: 7.1,
        depth_km: 20,
        detected_at: "2026-07-08T10:00:00Z",
      },
      {
        event_id: "e-2",
        source: "manual",
        lon: -98.2,
        lat: 19.0,
        magnitude: null,
        depth_km: null,
        detected_at: "2026-07-08T10:00:00Z",
      },
    ]);
    expect(fc.features[0].geometry.coordinates).toEqual([-99.1, 16.8]);
    expect(fc.features[0].properties).toMatchObject({ label: "M 7.1" });
    // Sin magnitud NO se inventa un número: se rotula el evento.
    expect(fc.features[1].properties).toMatchObject({ label: "EPICENTRO" });
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
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={onSelectSite} />);
    expect(mocks.Map).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();

    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    expect(mocks.map.addSource).toHaveBeenCalledWith("sites", expect.anything());
    expect(mocks.map.addSource).toHaveBeenCalledWith("tripped", expect.anything());
    expect(mocks.map.addSource).toHaveBeenCalledWith("epicenters", expect.anything());
    expect(mocks.map.addLayer).toHaveBeenCalled();

    mocks.handlers.get("click:site-core")?.({
      features: [{ properties: { site_id: "crit" } }],
    });
    expect(onSelectSite).toHaveBeenCalledWith("crit");
  });

  it("el EPICENTRO es su propia capa, separada de los edificios", () => {
    render(
      <MapPanel
        sites={[CRITICAL]}
        epicenters={[
          {
            event_id: "e-1",
            source: "ssn",
            lon: -99.1,
            lat: 16.8,
            magnitude: 7.1,
            depth_km: 20,
            detected_at: "2026-07-08T10:00:00Z",
          },
        ]}
        onSelectSite={vi.fn()}
      />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const layers: Array<{ id: string; source: string }> = mocks.map.addLayer.mock.calls.map(
      (call) => call[0] as { id: string; source: string },
    );
    const epi = layers.filter((l) => l.source === "epicenters");
    expect(epi.length).toBeGreaterThan(0);
    // El epicentro NUNCA sale de la fuente de edificios: no es un edificio.
    expect(epi.every((l) => l.source !== "sites")).toBe(true);
    // Y con un epicentro localizado NO se declara su ausencia.
    expect(screen.queryByTestId("map-no-epicenter")).toBeNull();
  });

  it("sin epicentro localizado lo DECLARA, en vez de plantarlo sobre el edificio", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    expect(screen.getByTestId("map-no-epicenter")).toHaveTextContent("SIN EPICENTRO LOCALIZADO");
  });

  // Aquí vivían "mmi-severa" (55px) y "mmi-alta" (100px), rotuladas INTENSIDAD
  // MMI y conectadas a NADA. Como `circle-radius` de MapLibre es en PÍXELES DE
  // PANTALLA, el mismo anillo afirmaba ~22 km de radio en zoom 8.5 y ~1 km en
  // zoom 13: la banda cambiaba de significado físico con cada zoom. Sin
  // magnitud (NULL) ni PGA calibrado no hay isosista honesta que dibujar, así
  // que no se dibuja ninguna (regla de oro 7). El mapa de intensidades es el
  // mini-ShakeMap del BLUEPRINT §14 — fase futura.
  it("NO pinta bandas de intensidad: ni capas MMI ni una leyenda que prometa una escala inexistente", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });

    const layerIds: string[] = mocks.map.addLayer.mock.calls.map(
      (call) => (call[0] as { id: string }).id,
    );
    expect(layerIds.some((id) => id.startsWith("mmi"))).toBe(false);
    expect(screen.queryByText(/INTENSIDAD MMI/i)).not.toBeInTheDocument();
    // La leyenda dice lo que el color ES: lo que midió el edificio.
    expect(screen.getByText(/SACUDIDA MEDIDA EN EL EDIFICIO/i)).toBeInTheDocument();
  });

  it("estilo remoto caído ⇒ degrada al estilo LOCAL, re-cuelga las capas y lo declara", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);

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
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
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
      render(<MapPanel sites={[]} epicenters={[]} onSelectSite={vi.fn()} />);
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
