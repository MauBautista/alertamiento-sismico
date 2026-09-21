import { act, fireEvent, render, screen } from "@testing-library/react";
import { cssVariables } from "@takab/design-tokens";
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
  arrivalsFeatureCollection,
  epicentersToFeatureCollection,
  FALLBACK_STYLE,
  FELT_COLOR,
  FELT_GLYPH,
  pulseAt,
  sitesToFeatureCollection,
  staticRingsFeatureCollection,
  trippedFeatures,
} from "./MapPanel";
import type { ShakemapOut } from "./shakemap";
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

describe("[T-6.09] la banda de sacudida no viaja SOLO en el color", () => {
  it("`watch` y `normal` se distinguen sin mirar el color", () => {
    // El defecto: ámbar (#FFC107) y verde (#00E676) con el MISMO radio. Bajo
    // deuteranopía —el 6 % de los hombres— los dos tiran a un amarillo
    // parecido, y son la diferencia entre «superó cautela» y «bajo umbral».
    expect(FELT_GLYPH.watch).not.toBe(FELT_GLYPH.normal);
    expect(FELT_GLYPH.watch.trim()).not.toBe("");
  });

  it("el que NO tiene nada que decir no dice nada; el que no midió dice que no sabe", () => {
    // Misma doctrina que el glifo de enlace: el ruido visual se reserva al
    // problema. Y `unknown` gana marca propia porque «no reportó» no es «no se
    // movió» (regla de oro 7) y hasta hoy solo lo decía el gris.
    expect(FELT_GLYPH.normal).toBe("");
    expect(FELT_GLYPH.unknown).toBe("?");
    expect(FELT_GLYPH.trip).not.toBe(FELT_GLYPH.watch);
  });

  it("no reusa el vocabulario del ENLACE: dos alfabetos que dicen cosas distintas", () => {
    // `⊘ ▲ ○` ya significan «sin enlace / degradado / sin gabinete». Un ▲ que
    // según la capa signifique «cautela» o «enlace degradado» no es un glifo:
    // es una adivinanza.
    const enlace = new Set(["⊘", "▲", "○", "✳", "◇"]);
    for (const [banda, glifo] of Object.entries(FELT_GLYPH)) {
      expect(enlace.has(glifo), `${banda} usa \`${glifo}\`, que ya significa otra cosa`).toBe(
        false,
      );
    }
  });

  it("cada sitio lleva su glifo en la fuente, derivado de la MISMA banda que el color", () => {
    const fc = sitesToFeatureCollection([
      site("a", { felt: "trip" }),
      site("b", { felt: "watch" }),
      site("c", { felt: "normal" }),
      site("d", { felt: "unknown" }),
    ]);
    expect(fc.features.map((f) => f.properties.felt_glyph)).toEqual([
      FELT_GLYPH.trip,
      FELT_GLYPH.watch,
      FELT_GLYPH.normal,
      FELT_GLYPH.unknown,
    ]);
    // Y el color no se mueve: el glifo se SUMA al canal de color, no lo sustituye.
    expect(fc.features[1].properties.color).toBe(FELT_COLOR.watch);
  });

  it("una banda que el server estrene no se pinta como «bajo umbral»", () => {
    // `felt` viene del rule_set. Si mañana llega una banda nueva, un default
    // que caiga en verde afirmaría que el edificio está tranquilo.
    const f = sitesToFeatureCollection([site("x", { felt: "banda_nueva" })]).features[0];
    expect(f.properties.color).toBe(FELT_COLOR.unknown);
    expect(f.properties.felt_glyph).toBe(FELT_GLYPH.unknown);
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

  // [T-7.24] LA GUARDA `DIF-shakemap.a` VIVÍA AQUÍ, y decía en NEGATIVO lo que
  // esta consola no podía prometer: «no pinta bandas de intensidad». Nació de un
  // defecto medido — dos capas `circle` (`mmi-severa` 55 px, `mmi-alta` 100 px)
  // rotuladas INTENSIDAD MMI y conectadas a NADA, con el radio en PÍXELES DE
  // PANTALLA: el mismo anillo afirmaba ~22 km de radio a zoom 8.5 y ~1 km a zoom
  // 13, o sea que cambiaba de significado físico con cada rueda del ratón.
  //
  // Hoy el mini-ShakeMap existe (`GET /incidents/{id}/shakemap`) y la guarda se
  // SUSTITUYE por la que afirma en POSITIVO lo que lo hace honesto. Las dos
  // negaciones que mataron a aquellas capas se conservan dentro —ni `mmi*` ni
  // «INTENSIDAD MMI», y ninguna capa con significado físico en unidades de
  // pantalla—, porque lo que las mató no ha cambiado: sigue sin haber escala de
  // intensidad, y `dictamen/model.py::NO_MMI` está impreso en documentos ya
  // FIRMADOS diciendo que TAKAB no reporta intensidad macrosísmica ni isosistas.
  describe("[T-7.24] el mapa de la sacudida dice de dónde sale CADA valor", () => {
    /** Snapshot completo: tres anillos modelados y un inmueble que midió. */
    const SHAKEMAP: ShakemapOut = {
      incident_id: "i-1",
      estado: "completo",
      // Siempre presente aunque esté vacío: el contrato lo declara así para que
      // la consola no tenga que distinguir «no vino» de «vino sin nada».
      fuera_de_alcance: [],
      calculado_en: "2026-09-14T10:41:30Z",
      ley: "ATTEN-LAW v1",
      cobertura_km: 25,
      epicentro: {
        lat: 17.8,
        lon: -99.0,
        depth_km: 20,
        magnitud: 7.1,
        fuente: "SSN",
        procedencia: "confirmado",
        catalog_key: "SSN-2026-001",
      },
      observado: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [-98.2404, 19.3139] },
            properties: {
              site_id: "crit",
              site_code: "site-cholula-a",
              site_name: "Cholula A",
              procedencia: "measured",
              pga_g: 0.083,
              pgv_cms: 2.1,
              dist_km: 120,
              hypo_km: 129,
              pga_g_modelada: 0.041,
              residuo_log10: 0.306,
              medido_en: "2026-09-14T10:00:35Z",
              voto_contado: true,
            },
          },
        ],
      },
      modelado: {
        type: "FeatureCollection",
        features: [0.02, 0.08].map((pga, i) => ({
          type: "Feature" as const,
          geometry: {
            type: "Polygon" as const,
            coordinates: [
              [
                [-99.1, 17.9],
                [-98.9, 17.9],
                [-98.9, 17.7],
                [-99.1, 17.7],
                [-99.1, 17.9],
              ],
            ],
          },
          properties: {
            procedencia: "modeled" as const,
            pga_g: pga,
            radio_km: [130, 66][i],
            umbral: ["pga_watch_g", "pga_trip_g"][i],
          },
        })),
      },
    };

    /**
     * Tope de un radio CONSTANTE en píxeles para que siga leyéndose como un
     * marcador y no como un área. No es un número a ojo: los marcadores de este
     * mapa miden 9 y 14-15 px, y las dos bandas MMI que costaron la guarda
     * `DIF-shakemap.a` medían 55 y 100.
     */
    const MARCADOR_MAX_PX = 20;

    /** Las especificaciones de capa tal como se le pasaron a MapLibre. */
    function capas(): Array<Record<string, unknown>> {
      return mocks.map.addLayer.mock.calls.map((call) => call[0] as Record<string, unknown>);
    }
    function capa(id: string): Record<string, unknown> {
      const encontrada = capas().find((l) => l["id"] === id);
      expect(encontrada, `la capa ${id} no se agregó al mapa`).toBeDefined();
      return encontrada!;
    }
    /** Lo último que se le dio a esa fuente (las capas nacen vacías). */
    function datos(id: string): { features: Array<{ properties: Record<string, unknown> }> } {
      const source = mocks.sources.get(id);
      expect(source, `la fuente ${id} no existe`).toBeDefined();
      const llamadas = source!.setData.mock.calls;
      expect(llamadas.length, `nadie alimentó la fuente ${id}`).toBeGreaterThan(0);
      return llamadas[llamadas.length - 1][0] as {
        features: Array<{ properties: Record<string, unknown> }>;
      };
    }
    function montar(props: Partial<Parameters<typeof MapPanel>[0]> = {}) {
      const salida = render(
        <MapPanel
          sites={[CRITICAL]}
          epicenters={[]}
          onSelectSite={vi.fn()}
          shakemap={SHAKEMAP}
          {...props}
        />,
      );
      act(() => {
        mocks.handlers.get("style.load")?.();
      });
      return salida;
    }

    it("cada valor viaja con su PROCEDENCIA, y medido y modelado NO se mezclan", () => {
      montar();
      for (const f of datos("shakemap-observado").features) {
        expect(f.properties["procedencia"]).toBe("measured");
      }
      for (const f of datos("shakemap-modelado").features) {
        expect(f.properties["procedencia"]).toBe("modeled");
      }
      // Y el valor va pegado a su procedencia en el MISMO rasgo: quien los junte
      // en una lista no puede perderla por el camino (`D-08` · `§A.3`).
      expect(datos("shakemap-observado").features[0].properties).toMatchObject({
        procedencia: "measured",
        pga_g: 0.083,
        label: "0.083 g · ×2.0",
      });
    });

    it("lo MEDIDO y lo MODELADO no comparten codificación: disco relleno vs anillo discontinuo", () => {
      montar();
      const punto = capa("shakemap-punto");
      const anillo = capa("shakemap-anillo");
      expect(punto["type"]).toBe("circle");
      expect(anillo["type"]).toBe("line");
      expect((anillo["paint"] as Record<string, unknown>)["line-dasharray"]).toBeDefined();
      // Dos fuentes distintas: ni un rasgo puede acabar dibujado por la capa de
      // la otra procedencia.
      expect(punto["source"]).not.toBe(anillo["source"]);
    });

    it("NINGUNA capa con significado físico se dibuja en unidades de PANTALLA", () => {
      // ⚠️ ÉSTE es el pecado que mató a `mmi-severa` y `mmi-alta`. El anillo
      // afirma «aquí el modelo predice 0.02 g» y tiene que seguir afirmándolo a
      // cualquier zoom: su geometría es un POLÍGONO EN GRADOS que materializa el
      // lector (`shakemap/lectura.py::circulo`), no un radio en píxeles.
      //
      // ⚠️⚠️ Y ES UN BARRIDO, no una consulta. La guarda que sustituyó a
      // `DIF-shakemap.a` miraba UNA capa por su id (`capa("shakemap-anillo")`),
      // así que el pecado se podía re-cometer con cualquier otro nombre: un
      // escéptico colgó `shakemap-banda-alta` —`circle-radius: 100` PÍXELES
      // sobre la fuente del MODELO— y las 2 523 pruebas de web siguieron verdes.
      // La guarda vieja sí barría el conjunto (`id.startsWith("mmi")`) y la
      // sustitución lo estrechó.
      //
      // ⚠️⚠️⚠️ Y la corrección se quedó CORTA: barría por FUENTE, pero sólo las
      // que empiezan por `shakemap-`. Medido: la MISMA capa pecadora
      // (`circle-radius: 100`) colgada de una fuente llamada `pga-banda` pasaba
      // entera, con las 57 pruebas de este bloque en verde. Un censo acotado por
      // el nombre de la fuente es un censo que bendice al que se cambia el
      // nombre — la tercera vez que esta ficha lo aprende. Aquí se barre EL
      // CONJUNTO, y luego se juzga cada fuente del mapa de la sacudida por lo
      // que afirma.
      montar();

      // BARRIDO 1 · TODAS las capas, sin lista blanca que mantener. El
      // invariante no necesita saber qué afirma cada capa: un radio en PÍXELES
      // no puede afirmar extensión. O el radio viaja en el rasgo (`radius_px`,
      // rehecho en `zoomend`, que es como se dibujan km de verdad), o es un
      // número de MARCADOR y un marcador no pasa de `MARCADOR_MAX_PX`.
      const fisico = (radio: unknown): boolean =>
        JSON.stringify(radio ?? null).includes("radius_px");
      /** Los números que hay dentro de una expresión de MapLibre, a cualquier nivel. */
      const pixeles = (v: unknown): number[] =>
        typeof v === "number" ? [v] : Array.isArray(v) ? v.flatMap(pixeles) : [];
      expect(capas().length, "no se colgó ninguna capa del mapa").toBeGreaterThan(0);
      for (const espec of capas()) {
        const radio = ((espec["paint"] ?? {}) as Record<string, unknown>)["circle-radius"];
        if (radio === undefined || fisico(radio)) continue;
        for (const px of pixeles(radio)) {
          expect(
            px,
            `${String(espec["id"])} (fuente «${String(espec["source"])}»): ${px} px ya no se lee como marcador, se lee como área`,
          ).toBeLessThanOrEqual(MARCADOR_MAX_PX);
        }
      }

      // BARRIDO 2 · y las capas del mapa de la sacudida, además, por lo que
      // afirma la fuente de la que cuelgan, con default-deny para una fuente
      // nueva que este censo no sepa juzgar.
      const delMapa = capas().filter((l) => String(l["source"] ?? "").startsWith("shakemap-"));
      expect(delMapa.length, "el mapa de la sacudida no colgó ninguna capa").toBeGreaterThan(0);
      for (const especificacion of delMapa) {
        const id = String(especificacion["id"]);
        const fuente = String(especificacion["source"]);
        const paint = (especificacion["paint"] ?? {}) as Record<string, unknown>;
        const enPantalla = Object.keys(paint).filter((k) => k.startsWith("circle-"));
        if (fuente === "shakemap-modelado") {
          // El MODELO afirma EXTENSIÓN. Sus rasgos son polígonos en grados, así
          // que cualquier propiedad `circle-*` aquí es, por construcción, una
          // extensión dibujada en píxeles de pantalla.
          expect(enPantalla, `${id} dibuja el MODELO en unidades de pantalla`).toEqual([]);
        } else if (fuente === "shakemap-observado") {
          const radio = paint["circle-radius"];
          if (radio !== undefined) {
            // Un marcador NO afirma extensión: afirma un valor EN ESE PUNTO, y
            // por eso su radio es constante. Atarlo al dato lo convertiría en
            // una burbuja que se lee como área de influencia.
            expect(typeof radio, `${id}: el radio del marcador depende del dato`).toBe("number");
            // Y tiene que seguir leyéndose como un marcador. Los de este mapa
            // miden 9-15 px; el pecado de `DIF-shakemap.a` medía 55 y 100.
            expect(
              radio as number,
              `${id}: ${String(radio)} px ya no se lee como marcador, se lee como área`,
            ).toBeLessThanOrEqual(MARCADOR_MAX_PX);
          }
        } else if (fuente === "shakemap-cobertura") {
          // El halo mide 25 km DE TERRENO: su radio se recalcula con el zoom y
          // viaja en el rasgo, nunca como número en el `paint`.
          expect(paint["circle-radius"], `${id}: la cobertura mide km, no píxeles`).toEqual([
            "get",
            "radius_px",
          ]);
        } else {
          // DEFAULT-DENY. Una capa colgada de una fuente que este censo no sabe
          // juzgar se declara aquí, con lo que afirma y en qué unidades. Un
          // censo que se calla ante lo que no conoce es el que dejó pasar
          // `shakemap-banda-alta`.
          expect.fail(`la capa ${id} cuelga de «${fuente}»: este censo no sabe qué afirma`);
        }
      }
      for (const f of datos("shakemap-modelado").features as unknown as Array<{
        geometry: { type: string; coordinates: number[][][] };
      }>) {
        expect(f.geometry.type).toBe("Polygon");
        for (const [lon, lat] of f.geometry.coordinates[0]) {
          expect(Math.abs(lon)).toBeLessThanOrEqual(180);
          expect(Math.abs(lat)).toBeLessThanOrEqual(90);
        }
      }
      // Y el halo de cobertura llega con su radio ya en píxeles del zoom actual,
      // derivado de los km que declara el snapshot.
      const halo = datos("shakemap-cobertura").features[0].properties;
      expect(halo["cobertura_km"]).toBe(25);
      expect(halo["radius_px"]).toBeGreaterThan(0);
    });

    it("`SIN COBERTURA` es un estado PROPIO de la leyenda, con su radio Y CON SU CAPA", () => {
      montar();
      const leyenda = screen.getByTestId("map-legend-pga");
      expect(leyenda).toHaveTextContent(/SIN COBERTURA/);
      // Con su cifra: sin el radio, «sin cobertura» no se puede ni discutir.
      expect(leyenda).toHaveTextContent(/25 km/);
      // ⚠️ Y con una capa que de verdad la pinte. Esta guarda comprobaba el
      // texto y el «25 km» y nada más, así que bendecía una clave de color
      // huérfana: `PGA_SIN_COBERTURA` sólo existía como `background` de una
      // muestra de la leyenda y NINGUNA capa del mapa la usaba. Una leyenda que
      // explica algo que no está en pantalla es, estructuralmente, la leyenda
      // MMI que esta tarea vino a cerrar.
      const tinta = cssVariables["--tk-pga-sin-cobertura"];
      const usan = capas().filter((l) => JSON.stringify(l["paint"] ?? {}).includes(tinta));
      expect(
        usan.map((l) => String(l["id"])),
        `la leyenda promete la tinta ${tinta} y ninguna capa la pinta`,
      ).not.toEqual([]);
      // Y la pinta como BORDE: el halo marca el límite, no tiñe un área.
      const paint = (usan[0]["paint"] ?? {}) as Record<string, unknown>;
      expect(paint["circle-stroke-color"]).toBe(tinta);
      expect(paint["circle-color"], "un relleno teñiría media pantalla").toBe("rgba(0,0,0,0)");
    });

    it("sin NINGUNA medida no hay halo, y la leyenda no promete la cobertura de nada", () => {
      // La fila colgaba de `shakemap !== undefined`, no de que hubiera algo que
      // cubrir: un incidente sin snapshot calculado imprimía «SIN COBERTURA · A
      // MÁS DE 25 km DE UN INMUEBLE INSTRUMENTADO» justo al lado de «ESTE
      // INCIDENTE AÚN NO TIENE SNAPSHOT».
      montar({
        shakemap: { ...SHAKEMAP, estado: "pendiente", calculado_en: null, modelado: null },
      });
      expect(datos("shakemap-cobertura").features).toEqual([]);
      expect(screen.getByTestId("map-legend-pga")).not.toHaveTextContent(/SIN COBERTURA/);
      expect(screen.getByTestId("shakemap-pendiente")).toBeInTheDocument();
    });

    it("la leyenda conserva la frase honesta y escribe el modelo COMO modelo", () => {
      montar();
      // La frase de la leyenda vieja sigue en pantalla: el color de un edificio
      // es lo que ÉL midió, no la severidad de la alerta.
      expect(screen.getByText(/SACUDIDA MEDIDA EN EL EDIFICIO/i)).toBeInTheDocument();
      const leyenda = screen.getByTestId("map-legend-pga");
      expect(leyenda).toHaveTextContent(/MODELO/);
      expect(leyenda).toHaveTextContent(/ATTEN-LAW v1/);
      expect(leyenda).toHaveTextContent(/ESTIMACIÓN/);
      // Y sigue sin haber escala de intensidad que prometer.
      expect(capas().some((l) => String(l["id"]).startsWith("mmi"))).toBe(false);
      expect(screen.queryByText(/INTENSIDAD MMI/i)).not.toBeInTheDocument();
      expect(leyenda).not.toHaveTextContent(/MMI/);
    });

    it("sin epicentro ni magnitud la capa modelada NO se dibuja, y se DECLARA", () => {
      montar({
        shakemap: { ...SHAKEMAP, estado: "solo_observado", epicentro: null, modelado: null },
      });
      expect(datos("shakemap-modelado").features).toEqual([]);
      expect(datos("shakemap-observado").features).toHaveLength(1);
      expect(screen.getByTestId("shakemap-sin-modelo")).toHaveTextContent(/NO SE MODELA/i);
      // Y la leyenda tampoco explica un anillo que no está: la fila del MODELO
      // cuelga de que haya modelo, no de que exista la capa.
      expect(screen.getByTestId("map-legend-pga")).not.toHaveTextContent(/ANILLO DISCONTINUO/);
      expect(screen.getByTestId("map-legend-pga")).toHaveTextContent(/MEDIDO EN EL EDIFICIO/);
    });

    it("pendiente, sin datos y error se declaran cada uno con su causa", () => {
      const { unmount } = montar({
        shakemap: { ...SHAKEMAP, estado: "pendiente", calculado_en: null, modelado: null },
      });
      expect(screen.getByTestId("shakemap-pendiente")).toBeInTheDocument();
      unmount();

      const sinDatos = render(
        <MapPanel
          sites={[CRITICAL]}
          epicenters={[]}
          onSelectSite={vi.fn()}
          shakemap={{
            ...SHAKEMAP,
            estado: "sin_datos",
            observado: { type: "FeatureCollection", features: [] },
          }}
        />,
      );
      expect(screen.getByTestId("shakemap-sin-datos")).toHaveTextContent(
        /SIN INMUEBLES INSTRUMENTADOS/i,
      );
      sinDatos.unmount();

      render(
        <MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} shakemapError={true} />,
      );
      expect(screen.getByTestId("shakemap-error")).toHaveTextContent(/NO DISPONIBLE/i);
    });

    it("apagar la capa se lleva su leyenda Y TODAS sus capas, no una", () => {
      // Mismo trato que la leyenda de ENLACE (T-2.46). Una leyenda que describe
      // una capa apagada explica algo que no está en pantalla.
      //
      // ⚠️ La lista de ids se DERIVA de lo que se colgó del mapa, no se teclea.
      // Escrita a mano, esta guarda sólo comprobaba `shakemap-anillo`: reducir
      // el grupo a ese único id dejaba el interruptor apagando la leyenda y los
      // anillos mientras los discos, sus valores y los rótulos seguían pintados
      // — y los 50 tests de este fichero seguían verdes.
      montar();
      const ids = capas()
        .filter((l) => String(l["source"] ?? "").startsWith("shakemap-"))
        .map((l) => String(l["id"]));
      expect(ids.length, "el grupo SACUDIDA tiene más de una capa").toBeGreaterThan(1);
      mocks.map.setLayoutProperty.mockClear();
      fireEvent.click(screen.getByTestId("layer-shakemap"));
      expect(screen.queryByTestId("map-legend-pga")).toBeNull();
      for (const id of ids) {
        expect(
          mocks.map.setLayoutProperty,
          `${id} se quedó pintada después de apagar SACUDIDA`,
        ).toHaveBeenCalledWith(id, "visibility", "none");
      }
    });

    it("el inmueble que NO publicó nada se pinta HUECO, y lo dice", () => {
      // El relleno es lo que afirma que HAY un valor. Sustituir el `case` por un
      // `["get","color"]` pinta relleno a un sitio que no midió —o sea, como si
      // tuviera valor— y ninguna prueba lo veía: la propiedad `medido` se
      // probaba pura y su único consumidor, el `paint`, no se probaba; ninguna
      // prueba del DOM montaba jamás un punto con `pga_g: null`.
      montar({
        shakemap: {
          ...SHAKEMAP,
          estado: "solo_observado",
          modelado: null,
          observado: {
            type: "FeatureCollection",
            features: [
              {
                ...SHAKEMAP.observado.features[0],
                properties: {
                  ...SHAKEMAP.observado.features[0].properties,
                  pga_g: null,
                  pgv_cms: null,
                  residuo_log10: null,
                },
              },
            ],
          },
        },
      });
      const props = datos("shakemap-observado").features[0].properties;
      expect(props["medido"]).toBe(false);
      expect(props["label"]).toBe("SIN MEDIDA EN LA VENTANA");
      // Y el `paint` DERIVA el relleno de esa propiedad, con transparencia total
      // cuando no hay medida.
      const relleno = (capa("shakemap-punto")["paint"] as Record<string, unknown>)["circle-color"];
      expect(Array.isArray(relleno), "el relleno del disco no depende de `medido`").toBe(true);
      const expr = relleno as unknown[];
      expect(expr[0]).toBe("case");
      expect(expr[1]).toEqual(["get", "medido"]);
      expect(String(expr[3]).replace(/\s/g, ""), "sin medida el disco tiene que ir HUECO").toBe(
        "rgba(0,0,0,0)",
      );
      // Un sitio que no midió tampoco da cobertura: rodearlo diría que sí.
      expect(datos("shakemap-cobertura").features).toEqual([]);
    });

    it("un estado que no se sabe leer SUPRIME los puntos aunque los haya, y lo declara", () => {
      // `pintaObservado` es un gate REAL y no un adorno, pero ninguna prueba lo
      // podía demostrar: las fixtures de `pendiente` y `sin_datos` llegaban con
      // `observado.features: []`, así que «no pinta» y «no hay» se veían igual.
      // Aquí el snapshot TRAE una medida y aun así no se pinta ninguna, porque
      // no se sabe qué significa el estado que la acompaña.
      montar({ shakemap: { ...SHAKEMAP, estado: "recalculando" } });
      expect(SHAKEMAP.observado.features.length).toBe(1);
      expect(datos("shakemap-observado").features).toEqual([]);
      expect(datos("shakemap-modelado").features).toEqual([]);
      expect(screen.getByTestId("shakemap-no-interpretable")).toHaveTextContent(/recalculando/);
      // Y NO se fecha: «CALCULADO …» sobre un mapa que se acaba de declarar
      // ilegible lo vuelve a presentar como un mapa válido y reciente.
      expect(screen.queryByTestId("shakemap-calculado")).toBeNull();
    });

    it("el snapshot que se declara SIN DATOS y trae una medida pinta la medida", () => {
      // El rótulo lo escribió un worker; la medida, un acelerómetro.
      montar({ shakemap: { ...SHAKEMAP, estado: "sin_datos" } });
      expect(datos("shakemap-observado").features).toHaveLength(1);
      const leyenda = screen.getByTestId("map-legend-pga");
      expect(leyenda).not.toHaveTextContent(/NINGÚN INMUEBLE/i);
      expect(screen.getByTestId("shakemap-sin-datos-discrepa")).toHaveTextContent(/1 MEDIDA/);
    });

    it("el `sin_datos` que la nube SÍ produce no se acusa de contradicción ni tapa su nota", () => {
      // ⚠️ LA FALSA ALARMA. Éste es el snapshot literal que publica la nube
      // cuando nadie midió: `estado: sin_datos` y un punto MUDO por cada
      // inmueble instrumentado (`servicio.py::_medidas_de` no filtra por
      // `peak_pga_g`). Con la discrepancia gateada por `puntos.length`, la
      // leyenda del SOC imprimía CUATRO afirmaciones que el propio dato
      // desmiente —«TRAE 2 MEDIDA(S)» con cero medidas, «SE PINTA LO MEDIDO»
      // sin nada medido, «DISCO CON SU VALOR» sobre discos sin valor y «SIN
      // COBERTURA · A MÁS DE 25 km» sin un solo halo— y **tapaba la nota
      // correcta**, que es la única que el operador necesita leer.
      //
      // Ninguna guarda lo vio porque las dos fixtures de `sin_datos` llegaban
      // con `observado.features: []`: ninguna montaba la forma que la nube sí
      // produce.
      const mudo = (id: string) => ({
        ...SHAKEMAP.observado.features[0],
        properties: {
          ...SHAKEMAP.observado.features[0].properties,
          site_id: id,
          pga_g: null,
          pgv_cms: null,
          pga_g_modelada: null,
          residuo_log10: null,
          medido_en: null,
        },
      });
      montar({
        shakemap: {
          ...SHAKEMAP,
          estado: "sin_datos",
          modelado: null,
          observado: { type: "FeatureCollection", features: [mudo("crit"), mudo("s-2")] },
        },
      });
      const leyenda = screen.getByTestId("map-legend-pga");
      expect(screen.queryByTestId("shakemap-sin-datos-discrepa")).toBeNull();
      expect(screen.getByTestId("shakemap-sin-datos")).toHaveTextContent(
        /NINGUNO DE LOS 2 INMUEBLES INSTRUMENTADOS MIDIÓ EN LA VENTANA/,
      );
      expect(leyenda, "cero medidas no son «2 MEDIDA(S)»").not.toHaveTextContent(/MEDIDA\(S\)/);
      // Y la leyenda no explica ninguna capa que no esté en pantalla.
      expect(leyenda).not.toHaveTextContent(/DISCO CON SU VALOR/);
      expect(leyenda).not.toHaveTextContent(/SIN COBERTURA/);
      expect(datos("shakemap-observado").features).toEqual([]);
      expect(datos("shakemap-cobertura").features).toEqual([]);
    });

    it("con puntos y NINGUNA medida la leyenda tampoco promete cobertura", () => {
      // La fila de `SIN COBERTURA` colgaba de `pintaObservado`, que es «hay
      // puntos que pintar». El halo, en cambio, cuelga de `medido`: un inmueble
      // que no publicó no da cobertura ninguna. Con puntos mudos las dos cosas
      // discrepan y la leyenda vuelve a prometer un límite que ninguna capa
      // dibuja — el defecto de la clave de color huérfana, otra vez.
      montar({
        shakemap: {
          ...SHAKEMAP,
          estado: "solo_observado",
          modelado: null,
          observado: {
            type: "FeatureCollection",
            features: [
              {
                ...SHAKEMAP.observado.features[0],
                properties: {
                  ...SHAKEMAP.observado.features[0].properties,
                  pga_g: null,
                  pgv_cms: null,
                  residuo_log10: null,
                },
              },
            ],
          },
        },
      });
      expect(datos("shakemap-observado").features, "el punto mudo sí se pinta, hueco").toHaveLength(
        1,
      );
      expect(datos("shakemap-cobertura").features, "sin medida no hay halo").toEqual([]);
      expect(screen.getByTestId("map-legend-pga")).not.toHaveTextContent(/SIN COBERTURA/);
    });

    it("un rasgo SIN procedencia no se pinta, y la leyenda DICE cuántos se quedaron fuera", () => {
      // El contador se probaba puro; su declaración en pantalla, no
      // (`shakemap-sin-procedencia` no aparecía en ninguna prueba). Anular la
      // fila dejaba la suite entera en verde — y descartar en silencio es
      // cambiar un dato sospechoso por una pantalla tranquila.
      montar({
        shakemap: {
          ...SHAKEMAP,
          observado: {
            type: "FeatureCollection",
            features: [
              SHAKEMAP.observado.features[0],
              {
                ...SHAKEMAP.observado.features[0],
                properties: {
                  ...SHAKEMAP.observado.features[0].properties,
                  site_id: "sin-proc",
                  procedencia: "modeled" as unknown as "measured",
                },
              },
            ],
          },
        },
      });
      expect(datos("shakemap-observado").features).toHaveLength(1);
      expect(screen.getByTestId("shakemap-sin-procedencia")).toHaveTextContent(
        /1 RASGO\(S\) SIN PROCEDENCIA/,
      );
    });

    it("el mapa NO es en vivo y DICE cuándo se calculó", () => {
      // Única declaración de con qué información se hizo este mapa (regla de
      // oro 7). Anular la fila dejaba 146 pruebas en verde.
      montar();
      expect(screen.getByTestId("shakemap-calculado")).toHaveTextContent(
        /CALCULADO 2026-09-14 · 10:41 UTC/,
      );
    });

    it("CONSULTANDO se declara: la espera no se ve igual que un incidente sin mapa", () => {
      render(
        <MapPanel
          sites={[CRITICAL]}
          epicenters={[]}
          onSelectSite={vi.fn()}
          shakemapLoading={true}
        />,
      );
      act(() => {
        mocks.handlers.get("style.load")?.();
      });
      expect(screen.getByTestId("shakemap-cargando")).toHaveTextContent(/CONSULTANDO/i);
      // Y no promete ni codificación ni cobertura de nada.
      expect(screen.getByTestId("map-legend-pga")).not.toHaveTextContent(/SIN COBERTURA/);
    });

    it("sin la prop, la capa NO existe: el wall no estrena una leyenda vacía", () => {
      render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
      act(() => {
        mocks.handlers.get("style.load")?.();
      });
      expect(screen.queryByTestId("map-legend-pga")).toBeNull();
      expect(screen.queryByTestId("layer-shakemap")).toBeNull();
    });
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

  it("[T-6.09] el glifo de sacudida es una capa propia, y la leyenda lo enseña", () => {
    // Sin capa, `felt_glyph` sería un dato que no llega a ninguna pantalla; sin
    // leyenda, una marca que nadie sabe leer.
    render(
      <MapPanel
        sites={[site("a", { felt: "watch" }), site("b", { felt: "normal" })]}
        epicenters={[]}
        onSelectSite={vi.fn()}
      />,
    );
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const layers: Array<{ id: string; source: string; layout?: Record<string, unknown> }> =
      mocks.map.addLayer.mock.calls.map((call) => call[0] as never);
    const felt = layers.find((l) => l.id === "site-felt");
    expect(felt?.source).toBe("sites");
    expect(felt?.layout?.["text-field"]).toEqual(["get", "felt_glyph"]);

    const leyenda = screen.getByText(/SACUDIDA MEDIDA EN EL EDIFICIO/i).parentElement;
    expect(leyenda).toHaveTextContent(`${FELT_GLYPH.watch} Superó cautela`);
    expect(leyenda).toHaveTextContent(`${FELT_GLYPH.unknown} Sin dato`);
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

/**
 * [T-7.05 · C-1] CAPAS VA PRIMERA EN LA COLUMNA DE LEYENDAS.
 *
 * Con alerta en pantalla, `soc.css` le resta a `.soc-map__legends` el alto que
 * reserva la pila de alertas: la banda pasa de 376 / 447 / 447 px a 136 / 236 /
 * 298 (medido en Chromium con las hojas y las fuentes reales, para los tres altos
 * de escenario que sirve la consola). Lo que no cabe sigue ahí, pero scrolleando.
 *
 * Cuál de las tres leyendas se va, entonces, lo decide el ORDEN DEL MARCADO y no
 * la hoja: el contenedor scrollea desde arriba, así que la primera es la que
 * siempre está a la vista. CAPAS tiene que ser esa porque es el único CONTROL del
 * grupo —el criterio C-1 exige que sus cuatro botones respondan a
 * `elementFromPoint`—; las otras dos son lectura. Reordenar estos tres bloques
 * dejaría los botones fuera de la banda con la hoja intacta y con el barrido del
 * e2e en verde: no habría solape que medir, simplemente no estarían.
 */
describe("[T-7.05] el orden de las leyendas decide qué sobrevive a la banda corta", () => {
  it("CAPAS es la primera leyenda de la columna", () => {
    const { container } = render(
      <MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />,
    );
    const columna = container.querySelector(".soc-map__legends");
    expect(columna, "no hay columna de leyendas que ordenar").not.toBeNull();
    const primera = columna!.firstElementChild;
    expect(
      primera?.getAttribute("data-testid"),
      "la primera leyenda de la columna no es CAPAS: con la banda corta de una alerta, sus botones quedan fuera de vista",
    ).toBe("map-layers");
  });
});

// [T-7.18] EL ARRIBO POR ESTACIÓN
describe("MapPanel · la ráfaga de arribo", () => {
  it("la capa del anillo existe y va DEBAJO del edificio", () => {
    render(<MapPanel sites={[CRITICAL]} epicenters={[]} onSelectSite={vi.fn()} />);
    act(() => {
      mocks.handlers.get("style.load")?.();
    });
    const ids: string[] = mocks.map.addLayer.mock.calls.map((c: [{ id: string }]) => c[0].id);
    expect(ids).toContain("arrival-ring");
    // Se añade antes que el halo ⇒ MapLibre lo dibuja debajo: el anillo anuncia
    // que la onda llegó, no tapa lo que el edificio midió.
    expect(ids.indexOf("arrival-ring")).toBeLessThan(ids.indexOf("site-halo"));
  });

  it("el instante de cada estación sale del FRENTE, no de un campo del servidor", () => {
    const fc = arrivalsFeatureCollection(
      [
        {
          event_id: "EVT-1",
          source: "external",
          reproduccion: true,
          lon: -98.4887,
          lat: 18.5499,
          magnitude: 7.1,
          depth_km: 48,
          detected_at: new Date().toISOString(),
        },
      ],
      [
        { site_id: "cerca", lon: -98.2404, lat: 19.3139 },
        { site_id: "lejos", lon: -99.6557, lat: 19.2826 },
      ] as unknown as Parameters<typeof arrivalsFeatureCollection>[1],
    );
    const porSitio = Object.fromEntries(
      fc.features.map((f) => [f.properties?.["site_id"], f.properties?.["arrival_s"]]),
    );
    expect(porSitio["cerca"]).toBeLessThan(porSitio["lejos"] as number);
    expect(porSitio["cerca"]).toBeGreaterThan(0);
  });

  it("sin frente vivo la colección queda VACÍA: el anillo desaparece solo", () => {
    expect(arrivalsFeatureCollection([], []).features).toEqual([]);
  });
});
