import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

const mocks = vi.hoisted(() => {
  const handlers = new Map<string, (event?: unknown) => void>();
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  const layers = new Set<string>();
  const map = {
    on: vi.fn((event: string, layerOrCb: unknown, cb?: (event?: unknown) => void) => {
      if (typeof layerOrCb === "function") handlers.set(event, layerOrCb as () => void);
      else if (cb) handlers.set(`${event}:${layerOrCb as string}`, cb);
    }),
    addSource: vi.fn((id: string) => {
      sources.set(id, { setData: vi.fn() });
    }),
    addLayer: vi.fn((layer: { id: string }) => {
      layers.add(layer.id);
    }),
    getSource: vi.fn((id: string) => sources.get(id)),
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    // setStyle borra el estilo previo: las sources desaparecen hasta que el
    // siguiente style.load las re-agregue (semántica real de MapLibre).
    setStyle: vi.fn(() => {
      sources.clear();
      layers.clear();
    }),
    setPaintProperty: vi.fn(),
    setLayoutProperty: vi.fn(),
    getZoom: vi.fn(() => 8.5),
    getBounds: vi.fn(() => ({
      getWest: () => -100,
      getSouth: () => 18,
      getEast: () => -97,
      getNorth: () => 20,
    })),
    resize: vi.fn(),
    remove: vi.fn(),
  };
  return { handlers, sources, layers, map, Map: vi.fn(() => map) };
});

vi.mock("maplibre-gl", () => ({ default: { Map: mocks.Map } }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import MapPanel, {
  epicentersToFeatureCollection,
  FALLBACK_STYLE,
  FELT_COLOR,
  pulseAt,
  sitesToFeatureCollection,
  staticRingsFeatureCollection,
  trippedFeatures,
} from "./MapPanel";
import {
  LINK_DEGRADADO,
  LINK_OPERATIVO,
  LINK_SIN_ENLACE,
  LINK_SIN_GABINETE,
  coreOpacity,
} from "./link";
import { kmToPixels, staticRings } from "./wavefront";

function site(id: string, over: Partial<MapSiteState> = {}): MapSiteState {
  return {
    site_id: id,
    tenant_id: "t-1",
    name: `Sitio ${id}`,
    // Por defecto un sitio REAL: la marca de demo es la excepción, no el caso base.
    code: `site-${id}`,
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

  it("el epicentro corroborado muestra CUÁNTAS estaciones lo formaron (quórum, T-1.71)", () => {
    const fc = epicentersToFeatureCollection([
      {
        event_id: "e-q",
        source: "local_quorum",
        lon: -98.2,
        lat: 19.0,
        magnitude: null,
        depth_km: null,
        detected_at: "2026-07-08T10:00:00Z",
        node_count: 3,
      },
      {
        event_id: "e-cat",
        source: "ssn",
        lon: -99.1,
        lat: 16.8,
        magnitude: 5.4,
        depth_km: 20,
        detected_at: "2026-07-08T10:00:00Z",
        node_count: null,
      },
    ]);
    // Quórum sin magnitud: rotula la CORROBORACIÓN, no un número inventado.
    expect(fc.features[0].properties).toMatchObject({ label: "EPICENTRO · 3 est.", node_count: 3 });
    // Evento de catálogo sin node_count: no se inventa una cuenta de estaciones.
    expect(fc.features[1].properties).toMatchObject({ label: "M 5.4" });
  });
});

describe("[T-2.46] el ENLACE no usa el canal de color", () => {
  it("un enlace caído deja el NÚCLEO HUECO y apaga el punto, sin tocar `color`", () => {
    const caido = site("down", { felt: "trip", link_state: LINK_SIN_ENLACE });
    const vivo = site("up", { felt: "trip", link_state: LINK_OPERATIVO });
    const [f0, f1] = sitesToFeatureCollection([caido, vivo]).features;
    // El color sigue diciendo EXCLUSIVAMENTE qué midió el edificio.
    expect(f0.properties.color).toBe(FELT_COLOR.trip);
    expect(f1.properties.color).toBe(FELT_COLOR.trip);
    // Y el enlace se dice por otros canales.
    expect(f0.properties.link_down).toBe(true);
    expect(f1.properties.link_down).toBe(false);
    expect(f0.properties.link_opacity).toBeLessThan(f1.properties.link_opacity as number);
  });

  it("cada estado trae su glifo; SIN GABINETE y SIN ENLACE NO se confunden", () => {
    const fc = sitesToFeatureCollection([
      site("a", { link_state: LINK_SIN_ENLACE }),
      site("b", { link_state: LINK_SIN_GABINETE }),
      site("c", { link_state: LINK_DEGRADADO }),
      site("d", { link_state: LINK_OPERATIVO }),
    ]);
    const glyphs = fc.features.map((f) => f.properties.link_glyph);
    expect(glyphs[0]).toBe("⊘");
    expect(glyphs[1]).toBe("○");
    expect(glyphs[2]).toBe("▲");
    expect(glyphs[3]).toBe(""); // el sano no lleva ruido visual
    expect(glyphs[0]).not.toBe(glyphs[1]);
  });

  it("un sitio sin `link_state` (snapshot viejo) NO se pinta como enlace vivo", () => {
    const f = sitesToFeatureCollection([site("x")]).features[0];
    expect(f.properties.link).toBe(LINK_SIN_GABINETE);
    expect(f.properties.link_opacity).toBe(coreOpacity(LINK_SIN_GABINETE));
  });
});

describe("[T-2.47] anillos estáticos con radio FÍSICO", () => {
  const EPI = {
    event_id: "E",
    source: "sasmex",
    lon: -99.1,
    lat: 16.8,
    magnitude: null,
    depth_km: null,
    detected_at: "2026-08-04T12:00:00Z",
  };

  it("el radio en píxeles CAMBIA con el zoom para que los km no cambien", () => {
    const z8 = staticRingsFeatureCollection([EPI], 8);
    const z9 = staticRingsFeatureCollection([EPI], 9);
    const r8 = z8.features[0].properties.radius_px as number;
    const r9 = z9.features[0].properties.radius_px as number;
    expect(r9).toBeCloseTo(r8 * 2, 6);
    expect(r8).toBeCloseTo(kmToPixels(staticRings()[0].km, EPI.lat, 8), 6);
  });

  it("seis anillos rotulados por fase y tiempo, sin cuenta regresiva", () => {
    const fc = staticRingsFeatureCollection([EPI], 8);
    expect(fc.features).toHaveLength(6);
    const labels = fc.features.map((f) => f.properties.label);
    expect(labels).toContain("P +5s");
    expect(labels).toContain("S +20s");
    // CLAUDE.md §8: animación sí, T-MINUS no.
    expect(labels.some((l) => String(l).includes("T-"))).toBe(false);
  });
});

describe("MapPanel", () => {
  beforeEach(() => {
    mocks.handlers.clear();
    mocks.sources.clear();
    mocks.layers.clear();
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

  it("[T-2.46] SEGUNDA leyenda de ENLACE, separada de la del movimiento del suelo", () => {
    render(
      <MapPanel
        sites={[
          site("a", { link_state: LINK_OPERATIVO }),
          site("b", { link_state: LINK_SIN_ENLACE }),
          site("c", { link_state: LINK_SIN_GABINETE }),
        ]}
        epicenters={[]}
        onSelectSite={vi.fn()}
      />,
    );
    const legend = screen.getByTestId("map-legend-link");
    expect(legend).toHaveTextContent(/Enlace con la estación/i);
    // Cuenta por estado, y los dos "caídos" siguen separados.
    expect(legend).toHaveTextContent(`${LINK_SIN_ENLACE} · 1`);
    expect(legend).toHaveTextContent(`${LINK_SIN_GABINETE} · 1`);
    // La leyenda de sacudida sigue siendo OTRA caja.
    expect(screen.getByText(/SACUDIDA MEDIDA EN EL EDIFICIO/i)).toBeInTheDocument();
    expect(legend).not.toHaveTextContent(/SACUDIDA MEDIDA/i);
  });

  it("[T-2.46] la capa de glifo del enlace sale de la fuente de sitios", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const layers: Array<{ id: string; source: string }> = mocks.map.addLayer.mock.calls.map(
      (call) => call[0] as { id: string; source: string },
    );
    const glyph = layers.find((l) => l.id === "site-link");
    expect(glyph?.source).toBe("sites");
  });

  it("[T-5.05] el rótulo DEMO es su propia capa sobre la fuente de sitios", () => {
    // Sin capa, la propiedad `demo_glyph` no la pintaría nadie y el censo de
    // arriba estaría comprobando un dato que no llega a ninguna pantalla.
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const layers: Array<{ id: string; source: string; paint?: Record<string, unknown> }> =
      mocks.map.addLayer.mock.calls.map((call) => call[0] as never);
    const demo = layers.find((l) => l.id === "site-demo");
    expect(demo?.source).toBe("sites");
    // Gris, NO ámbar: el ámbar de esta consola ya es simulacro y dato retenido.
    expect(demo?.paint?.["text-color"]).toBe("#8A9CB1");
  });

  it("[T-2.47] recargar con un incidente VIEJO no arranca anillos fantasma", () => {
    const viejo = {
      event_id: "e-viejo",
      source: "sasmex",
      lon: -99.1,
      lat: 16.8,
      magnitude: null,
      depth_km: null,
      detected_at: new Date(Date.now() - 30 * 60_000).toISOString(),
    };
    render(<MapPanel sites={[CRITICAL]} epicenters={[viejo]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    expect(screen.getByTestId("waves-idle")).toBeInTheDocument();
    expect(screen.queryByTestId("waves-model")).toBeNull();
    // Y las capas de onda quedan explícitamente ocultas, no "por defecto".
    const hidden = mocks.map.setLayoutProperty.mock.calls.filter(
      (c) => c[0] === "wave-p" && c[2] === "none",
    );
    expect(hidden.length).toBeGreaterThan(0);
  });

  it("[T-2.47] con epicentro localizado y fresco declara el MODELO, sin T-MINUS", () => {
    const fresco = {
      event_id: "e-vivo",
      source: "local_quorum",
      lon: -99.1,
      lat: 16.8,
      magnitude: null,
      depth_km: null,
      detected_at: new Date(Date.now() - 5_000).toISOString(),
      node_count: 3,
    };
    render(<MapPanel sites={[CRITICAL]} epicenters={[fresco]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const note = screen.getByTestId("waves-model");
    expect(note).toHaveTextContent(/MODELO DE UNA CAPA · ESTIMACIÓN/);
    // CLAUDE.md §8: ni cuenta regresiva ni magnitud preliminar.
    expect(note).not.toHaveTextContent(/T-\d/);
    expect(note).not.toHaveTextContent(/MAGNITUD/i);
  });

  it("[T-2.47] un SOLO rAF, compuertado a 20 fps, avanza el frente y conmuta el dash", () => {
    // El rAF se captura en vez de ejecutarse: el loop es recursivo y un mock que
    // invoca el callback en el acto se cuelga.
    const frames: FrameRequestCallback[] = [];
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      frames.push(cb);
      return frames.length;
    });
    try {
      const fresco = {
        event_id: "e-vivo",
        source: "sasmex",
        lon: -99.1,
        lat: 16.8,
        magnitude: null,
        depth_km: null,
        detected_at: new Date(Date.now() - 5_000).toISOString(),
      };
      render(<MapPanel sites={[CRITICAL]} epicenters={[fresco]} onSelectSite={vi.fn()} />);
      act(() => {
        mocks.handlers.get("style.load")?.();
      });
      act(() => {
        frames[frames.length - 1](1000);
      });

      const paint = (layer: string, prop: string) =>
        mocks.map.setPaintProperty.mock.calls.filter((c) => c[0] === layer && c[1] === prop);

      // Radio del frente P: PÍXELES derivados de km, y estrictamente positivo a
      // los 5 s del origen. La S va por detrás (velocidad menor).
      const p = paint("wave-p", "circle-radius");
      const s = paint("wave-s", "circle-radius");
      expect(p.length).toBeGreaterThan(0);
      expect(p.at(-1)?.[2]).toBeGreaterThan(0);
      expect(s.at(-1)?.[2] as number).toBeLessThan(p.at(-1)?.[2] as number);
      // Dash conmutado: una propiedad de PINTURA, no geometría reescrita.
      expect(paint("wave-link", "line-dasharray").length).toBeGreaterThan(0);

      // Compuerta: un frame a +10 ms no vuelve a pintar nada…
      const antes = mocks.map.setPaintProperty.mock.calls.length;
      act(() => {
        frames[frames.length - 1](1010);
      });
      expect(mocks.map.setPaintProperty.mock.calls.length).toBe(antes);
      // …pero el loop SIGUE agendado (un solo rAF, nunca dos).
      expect(frames.length).toBeGreaterThan(2);

      // …y a +50 ms sí.
      act(() => {
        frames[frames.length - 1](1060);
      });
      expect(mocks.map.setPaintProperty.mock.calls.length).toBeGreaterThan(antes);
    } finally {
      rafSpy.mockRestore();
    }
  });

  it("[T-2.47] pasados los 180 s el frente se apaga SOLO, sin esperar snapshot", () => {
    const frames: FrameRequestCallback[] = [];
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      frames.push(cb);
      return frames.length;
    });
    try {
      // Fresco al montar (arranca), pero el reloj avanza más allá de la ventana.
      const casiViejo = {
        event_id: "e-borde",
        source: "sasmex",
        lon: -99.1,
        lat: 16.8,
        magnitude: null,
        depth_km: null,
        detected_at: new Date(Date.now() - 179_000).toISOString(),
      };
      const nowSpy = vi.spyOn(Date, "now");
      const real = Date.now();
      nowSpy.mockReturnValue(real);
      render(<MapPanel sites={[CRITICAL]} epicenters={[casiViejo]} onSelectSite={vi.fn()} />);
      act(() => {
        mocks.handlers.get("style.load")?.();
      });
      expect(screen.getByTestId("waves-model")).toBeInTheDocument();

      // El reloj cruza los 180 s sin que llegue ningún snapshot nuevo.
      nowSpy.mockReturnValue(real + 5_000);
      act(() => {
        frames[frames.length - 1](2000);
      });
      expect(screen.getByTestId("waves-idle")).toBeInTheDocument();
      nowSpy.mockRestore();
    } finally {
      rafSpy.mockRestore();
    }
  });

  it("[T-2.50] las capas se conmutan y el estado se declara en el botón", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    for (const key of ["stations", "epicenters", "catalog", "link", "waves"]) {
      expect(screen.getByTestId(`layer-${key}`)).toBeInTheDocument();
    }
    const link = screen.getByTestId("layer-link");
    expect(link).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(link);
    expect(link).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("map-legend-link")).toBeNull();
    expect(mocks.map.setLayoutProperty).toHaveBeenCalledWith("site-link", "visibility", "none");
  });

  it("[T-2.50] moveend reporta SOLO las estaciones del viewport", () => {
    const onViewportChange = vi.fn();
    const dentro = site("in", { lon: -98.3, lat: 19.06 });
    const fuera = site("out", { lon: -110, lat: 30 });
    render(
      <MapPanel
        sites={[dentro, fuera]}
        epicenters={[]}
        onSelectSite={vi.fn()}
        onViewportChange={onViewportChange}
      />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    onViewportChange.mockClear();
    act(() => {
      mocks.handlers.get("moveend")?.();
    });
    expect(onViewportChange).toHaveBeenCalledWith(["in"]);
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

// [T-5.05] EN EL MAPA, UN SITIO SIMULADO ERA INDISTINGUIBLE DE UNO REAL.
//
// El censo va por IGUALDAD y en las DOS mitades. La segunda —que nada real se
// marque— es la que de verdad importa: rotular de demostración un edificio con
// gente dentro es peor que no rotular ninguno, porque destruye la confianza en
// todo lo demás que pinta la pantalla.
describe("sitesToFeatureCollection · la marca de demostración", () => {
  const MIXTA = [
    site("site-sim-001"),
    site("site-sim-020"),
    site("site-dev"),
    site("site-cholula-a"),
    // El caso que un `includes("sim")` marcaría mal: un edificio real.
    site("site-simon-01"),
  ].map((s) => ({ ...s, code: s.site_id }));

  it("marca EXACTAMENTE los simulados, ni uno más ni uno menos", () => {
    const fc = sitesToFeatureCollection(MIXTA);
    const marcados = fc.features
      .filter((f) => f.properties.demo === true)
      .map((f) => f.properties.site_id)
      .sort();
    expect(marcados).toEqual(["site-sim-001", "site-sim-020"]);
  });

  it("el rótulo va vacío en los reales: cero ruido en producción", () => {
    const fc = sitesToFeatureCollection(MIXTA);
    const glifos = fc.features.map((f) => f.properties.demo_glyph);
    expect(glifos).toEqual(["DEMO", "DEMO", "", "", ""]);
  });

  it("con la flota real entera, ni una marca (el caso desplegado)", () => {
    const fc = sitesToFeatureCollection(
      [site("site-dev"), site("site-cholula-a")].map((s) => ({ ...s, code: s.site_id })),
    );
    expect(fc.features.filter((f) => f.properties.demo === true)).toEqual([]);
  });
});
