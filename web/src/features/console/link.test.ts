import { describe, expect, it } from "vitest";

import type { MapSiteState } from "@takab/sdk";

import {
  LINK_DEGRADADO,
  LINK_GLYPH,
  LINK_OPERATIVO,
  LINK_SIN_ENLACE,
  LINK_SIN_GABINETE,
  type LinkState,
  coreOpacity,
  haloOpacity,
  heartbeatAge,
  isLinkDown,
  isLinkLive,
  linkPillKind,
  siteLink,
} from "./link";

/** Los cuatro estados del contrato, tipados: un string suelto no compila. */
const ALL: LinkState[] = [LINK_OPERATIVO, LINK_DEGRADADO, LINK_SIN_ENLACE, LINK_SIN_GABINETE];

function site(over: Partial<MapSiteState> = {}): MapSiteState {
  return {
    site_id: "s-1",
    tenant_id: "t-1",
    name: "Sitio",
    code: "site-uno",
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

describe("siteLink — el default JAMÁS afirma un enlace vivo", () => {
  it("un snapshot viejo (sin el campo) es SIN GABINETE, no OPERATIVO", () => {
    // Un servidor que todavía no manda `link_state` no puede hacer que la consola
    // declare un enlace que nadie ha comprobado (regla de oro 7).
    expect(siteLink(site())).toBe(LINK_SIN_GABINETE);
  });

  it("un valor desconocido del servidor no se pinta como si fuera bueno", () => {
    expect(siteLink(site({ link_state: "ALGO NUEVO" }))).toBe(LINK_SIN_GABINETE);
  });

  it("los cuatro estados del contrato se respetan tal cual", () => {
    for (const state of ALL) {
      expect(siteLink(site({ link_state: state }))).toBe(state);
    }
  });
});

describe("SIN GABINETE ≠ SIN ENLACE", () => {
  it("son valores distintos y ambos cuentan como enlace caído para el dibujo", () => {
    expect(LINK_SIN_GABINETE).not.toBe(LINK_SIN_ENLACE);
    expect(isLinkDown(LINK_SIN_GABINETE)).toBe(true);
    expect(isLinkDown(LINK_SIN_ENLACE)).toBe(true);
    expect(isLinkDown(LINK_OPERATIVO)).toBe(false);
    // DEGRADADO SIGUE REPORTANDO: el color es una lectura viva, no un recuerdo.
    expect(isLinkDown(LINK_DEGRADADO)).toBe(false);
    expect(isLinkLive(LINK_DEGRADADO)).toBe(true);
  });

  it("cada estado tiene su propio glifo y el sano no lleva ninguno", () => {
    expect(LINK_GLYPH[LINK_OPERATIVO]).toBe("");
    expect(LINK_GLYPH[LINK_DEGRADADO]).toBe("▲");
    expect(LINK_GLYPH[LINK_SIN_ENLACE]).toBe("⊘");
    expect(LINK_GLYPH[LINK_SIN_GABINETE]).toBe("○");
    // Los tres visibles son distinguibles entre sí (nada de dos ⊘).
    const visible: LinkState[] = [LINK_DEGRADADO, LINK_SIN_ENLACE, LINK_SIN_GABINETE];
    expect(new Set(visible.map((s) => LINK_GLYPH[s])).size).toBe(3);
  });
});

describe("opacidad — el enlace NO usa el canal de color (lo ocupa `felt`)", () => {
  it("el enlace caído baja la opacidad; el vivo la deja entera", () => {
    expect(coreOpacity(LINK_OPERATIVO)).toBe(1);
    expect(coreOpacity(LINK_DEGRADADO)).toBeLessThan(1);
    expect(coreOpacity(LINK_SIN_ENLACE)).toBeLessThan(coreOpacity(LINK_DEGRADADO));
    expect(coreOpacity(LINK_SIN_GABINETE)).toBeLessThan(coreOpacity(LINK_DEGRADADO));
  });

  it("el halo siempre es más tenue que el núcleo (sigue siendo halo)", () => {
    for (const state of ALL) {
      expect(haloOpacity(state)).toBeLessThan(coreOpacity(state));
      expect(haloOpacity(state)).toBeGreaterThan(0);
    }
  });

  it("MapLibre rechaza opacidades fuera de 0..1: ninguna se sale", () => {
    for (const state of ALL) {
      expect(coreOpacity(state)).toBeGreaterThan(0);
      expect(coreOpacity(state)).toBeLessThanOrEqual(1);
      expect(haloOpacity(state)).toBeLessThanOrEqual(1);
    }
  });
});

describe("heartbeatAge — la EDAD, no el timestamp", () => {
  const NOW = Date.parse("2026-08-04T12:00:00Z");

  it("sin latido lo dice; no inventa una edad", () => {
    expect(heartbeatAge(null, NOW)).toEqual({ text: "SIN LATIDO REGISTRADO", seconds: null });
    expect(heartbeatAge(undefined, NOW)).toEqual({ text: "SIN LATIDO REGISTRADO", seconds: null });
  });

  it("segundos, minutos y horas en el idioma del wall", () => {
    expect(heartbeatAge("2026-08-04T11:59:48Z", NOW).text).toBe("HACE 12 s");
    expect(heartbeatAge("2026-08-04T11:56:00Z", NOW).text).toBe("HACE 4 min");
    expect(heartbeatAge("2026-08-04T06:00:00Z", NOW).text).toBe("HACE 6 h");
  });

  it("un latido con timestamp futuro (reloj a la deriva) no da edad negativa", () => {
    const age = heartbeatAge("2026-08-04T12:00:30Z", NOW);
    expect(age.seconds).toBe(0);
    expect(age.text).toBe("HACE 0 s");
  });

  it("una fecha ilegible no se convierte en NaN por la pantalla", () => {
    expect(heartbeatAge("no-es-fecha", NOW)).toEqual({
      text: "SIN LATIDO REGISTRADO",
      seconds: null,
    });
  });
});

describe("linkPillKind — reusa LinkPill, que solo tiene ok|crit", () => {
  it("solo OPERATIVO es 'ok': degradado y caído son avisos", () => {
    expect(linkPillKind(LINK_OPERATIVO)).toBe("ok");
    expect(linkPillKind(LINK_DEGRADADO)).toBe("crit");
    expect(linkPillKind(LINK_SIN_ENLACE)).toBe("crit");
    expect(linkPillKind(LINK_SIN_GABINETE)).toBe("crit");
  });
});
