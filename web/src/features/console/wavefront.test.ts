import { describe, expect, it } from "vitest";

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { V_P_KM_S } from "./attenuation";
import {
  DASH_FRAMES,
  DASH_STEP_MS,
  STATIC_RING_MARKS_S,
  V_S_KM_S,
  WAVE_MAX_AGE_S,
  animatableEpicenters,
  dashFrameIndex,
  epicenterLinks,
  isAnimatable,
  isLocalized,
  kmToPixels,
  metersPerPixel,
  staticRings,
  waveRadiiKm,
} from "./wavefront";

const NOW = Date.parse("2026-08-04T12:00:00Z");

function epicenter(over: Partial<MapEpicenter> = {}): MapEpicenter {
  return {
    event_id: "EVT-1",
    source: "local_quorum",
    lon: -99.1,
    lat: 16.8,
    magnitude: null,
    depth_km: null,
    detected_at: "2026-08-04T11:59:30Z", // hace 30 s
    node_count: 3,
    ...over,
  };
}

function site(over: Partial<MapSiteState> = {}): MapSiteState {
  return {
    site_id: "s-1",
    tenant_id: "t-1",
    name: "Planta Cholula",
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

describe("V_S se DERIVA de V_P, no se inventa", () => {
  it("V_S = V_P / √3 (razón de Poisson)", () => {
    // Una constante suelta sería una SEGUNDA fuente de verdad: si mañana el
    // quórum cambia `quorum_v_p_km_s`, la onda S del mapa se quedaría mintiendo.
    expect(V_S_KM_S).toBeCloseTo(V_P_KM_S / Math.sqrt(3), 12);
    expect(V_S_KM_S).toBeCloseTo(3.753, 3);
  });

  it("la S SIEMPRE va por detrás de la P", () => {
    expect(V_S_KM_S).toBeLessThan(V_P_KM_S);
  });
});

describe("waveRadiiKm — radios FÍSICOS en km, no píxeles", () => {
  it("cada frente avanza a su velocidad", () => {
    const r = waveRadiiKm(10);
    expect(r.pKm).toBeCloseTo(V_P_KM_S * 10, 9);
    expect(r.sKm).toBeCloseTo(V_S_KM_S * 10, 9);
    expect(r.sKm).toBeLessThan(r.pKm);
  });

  it("un origen en el FUTURO (reloj a la deriva) no produce radios negativos", () => {
    const r = waveRadiiKm(-3);
    expect(r.pKm).toBe(0);
    expect(r.sKm).toBe(0);
  });
});

describe("metersPerPixel — el pecado de MapPanel.tsx:239-250 no se repite", () => {
  // Ahí vivían dos anillos con `circle-radius` en PÍXELES DE PANTALLA rotulados
  // como intensidad: el mismo anillo afirmaba ~22 km en zoom 8.5 y ~1 km en zoom
  // 13. La rueda del ratón cambiaba el significado físico del dibujo.
  it("al duplicar el zoom, el píxel cubre la mitad de terreno", () => {
    const a = metersPerPixel(19, 8);
    const b = metersPerPixel(19, 9);
    expect(b).toBeCloseTo(a / 2, 9);
  });

  it("usa el tile de 512 px de MapLibre (no el de 256 de Web Mercator clásico)", () => {
    // 40075016.686 / (512 · 2^0) en el ecuador.
    expect(metersPerPixel(0, 0)).toBeCloseTo(78271.5169, 3);
  });

  it("hacia los polos el píxel cubre menos terreno (Mercator)", () => {
    expect(metersPerPixel(60, 10)).toBeLessThan(metersPerPixel(0, 10));
  });

  it("kmToPixels convierte una distancia física a radio de pantalla", () => {
    const px = kmToPixels(100, 19, 8);
    expect(px).toBeCloseTo((100 * 1000) / metersPerPixel(19, 8), 6);
    // Y el MISMO radio físico da MÁS píxeles al acercar: eso es lo correcto.
    expect(kmToPixels(100, 19, 9)).toBeCloseTo(px * 2, 6);
  });
});

describe("isLocalized — la animación exige un epicentro DE VERDAD", () => {
  it("SASMEX localiza", () => {
    expect(isLocalized(epicenter({ source: "sasmex", node_count: null }))).toBe(true);
  });

  it("el quórum localiza con 3 estaciones o más", () => {
    expect(isLocalized(epicenter({ source: "local_quorum", node_count: 3 }))).toBe(true);
    expect(isLocalized(epicenter({ source: "local_quorum", node_count: 2 }))).toBe(false);
  });

  it("un evento de catálogo sin corroboración NO arranca ondas", () => {
    // Un punto del SSN no describe un frente que esté cruzando la red AHORA.
    expect(isLocalized(epicenter({ source: "ssn", node_count: null }))).toBe(false);
    expect(isLocalized(epicenter({ source: "manual", node_count: undefined }))).toBe(false);
  });
});

describe("isAnimatable — se apaga por TRES condiciones", () => {
  it("con epicentro localizado y evento fresco, corre", () => {
    expect(isAnimatable({ epicenters: [epicenter()], nowMs: NOW, reducedMotion: false })).toBe(
      true,
    );
  });

  it("1) sin epicentro localizado no arranca", () => {
    expect(
      isAnimatable({
        epicenters: [epicenter({ source: "ssn", node_count: null })],
        nowMs: NOW,
        reducedMotion: false,
      }),
    ).toBe(false);
    expect(isAnimatable({ epicenters: [], nowMs: NOW, reducedMotion: false })).toBe(false);
  });

  it("2) recargar la página con un incidente VIEJO no arranca anillos fantasma", () => {
    // El caso que hay que probar de verdad: el incidente sigue abierto (por eso
    // el epicentro viene en el snapshot) pero el sismo pasó hace media hora. Un
    // frente animado sobre un evento de hace 30 min afirma algo falso.
    const viejo = epicenter({ detected_at: "2026-08-04T11:30:00Z" });
    expect(isAnimatable({ epicenters: [viejo], nowMs: NOW, reducedMotion: false })).toBe(false);
  });

  it("2b) el corte es exactamente WAVE_MAX_AGE_S", () => {
    const justo = epicenter({
      detected_at: new Date(NOW - (WAVE_MAX_AGE_S - 1) * 1000).toISOString(),
    });
    const pasado = epicenter({
      detected_at: new Date(NOW - (WAVE_MAX_AGE_S + 1) * 1000).toISOString(),
    });
    expect(isAnimatable({ epicenters: [justo], nowMs: NOW, reducedMotion: false })).toBe(true);
    expect(isAnimatable({ epicenters: [pasado], nowMs: NOW, reducedMotion: false })).toBe(false);
  });

  it("3) prefers-reduced-motion apaga TODO movimiento", () => {
    expect(isAnimatable({ epicenters: [epicenter()], nowMs: NOW, reducedMotion: true })).toBe(
      false,
    );
  });

  it("una fecha ilegible no arranca nada (y no revienta)", () => {
    expect(
      isAnimatable({
        epicenters: [epicenter({ detected_at: "no-es-fecha" })],
        nowMs: NOW,
        reducedMotion: false,
      }),
    ).toBe(false);
  });
});

describe("animatableEpicenters", () => {
  it("filtra al conjunto que SÍ describe un frente vivo", () => {
    const vivo = epicenter({ event_id: "vivo" });
    const viejo = epicenter({ event_id: "viejo", detected_at: "2026-08-04T11:00:00Z" });
    const sinLocalizar = epicenter({ event_id: "cat", source: "ssn", node_count: null });
    const ids = animatableEpicenters([vivo, viejo, sinLocalizar], NOW).map((e) => e.event_id);
    expect(ids).toEqual(["vivo"]);
  });

  it("con reduced-motion NO se filtra: los anillos estáticos siguen siendo útiles", () => {
    // El interruptor apaga el MOVIMIENTO, no la información.
    expect(animatableEpicenters([epicenter()], NOW)).toHaveLength(1);
  });
});

describe("epicenterLinks — geometría que se calcula UNA vez", () => {
  it("una línea por par (epicentro, estación), con km y rumbo medidos", () => {
    const fc = epicenterLinks([epicenter()], [site(), site({ site_id: "s-2", name: "Otra" })]);
    expect(fc.features).toHaveLength(2);
    const f = fc.features[0];
    expect(f.geometry.type).toBe("LineString");
    expect(f.geometry.coordinates[0]).toEqual([-99.1, 16.8]);
    expect(f.geometry.coordinates[1]).toEqual([-98.3, 19.06]);
    expect(f.properties.event_id).toBe("EVT-1");
    expect(f.properties.site_id).toBe("s-1");
    expect(f.properties.km).toBeGreaterThan(200);
    expect(f.properties.km).toBeLessThan(300);
    expect(typeof f.properties.bearing).toBe("string");
  });

  it("sin epicentros o sin estaciones no hay líneas (colección vacía, no null)", () => {
    expect(epicenterLinks([], [site()]).features).toHaveLength(0);
    expect(epicenterLinks([epicenter()], []).features).toHaveLength(0);
  });

  it("N epicentros × M estaciones = N·M líneas, y ninguna se recalcula por frame", () => {
    const fc = epicenterLinks(
      [epicenter({ event_id: "a" }), epicenter({ event_id: "b" })],
      [site({ site_id: "1" }), site({ site_id: "2" }), site({ site_id: "3" })],
    );
    expect(fc.features).toHaveLength(6);
  });
});

describe("dash conmutado — coste O(1) por frame", () => {
  it("el array de dasharrays está PREcomputado", () => {
    expect(DASH_FRAMES.length).toBeGreaterThan(1);
    for (const frame of DASH_FRAMES) {
      expect(Array.isArray(frame)).toBe(true);
      expect(frame.every((n) => Number.isFinite(n) && n >= 0)).toBe(true);
    }
  });

  it("el índice avanza un paso cada DASH_STEP_MS y cicla", () => {
    expect(dashFrameIndex(0)).toBe(0);
    expect(dashFrameIndex(DASH_STEP_MS - 1)).toBe(0);
    expect(dashFrameIndex(DASH_STEP_MS)).toBe(1);
    expect(dashFrameIndex(DASH_STEP_MS * DASH_FRAMES.length)).toBe(0);
  });

  it("un delta negativo del rAF (vsync previo) no da un índice fuera del array", () => {
    expect(dashFrameIndex(-5)).toBe(0);
  });
});

describe("staticRings — lo que se ve con prefers-reduced-motion", () => {
  it("anillos QUIETOS rotulados +5s/+10s/+20s, para P y para S", () => {
    expect(STATIC_RING_MARKS_S).toEqual([5, 10, 20]);
    const rings = staticRings();
    expect(rings).toHaveLength(STATIC_RING_MARKS_S.length * 2);
    expect(rings.map((r) => r.label)).toContain("P +5s");
    expect(rings.map((r) => r.label)).toContain("S +20s");
  });

  it("los radios son los MISMOS que los de la animación en ese instante", () => {
    // Si difirieran, la versión accesible estaría contando otra historia.
    const rings = staticRings();
    const p10 = rings.find((r) => r.label === "P +10s");
    expect(p10?.km).toBeCloseTo(waveRadiiKm(10).pKm, 9);
    const s10 = rings.find((r) => r.label === "S +10s");
    expect(s10?.km).toBeCloseTo(waveRadiiKm(10).sKm, 9);
  });
});
