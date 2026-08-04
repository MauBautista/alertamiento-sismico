import { describe, expect, it } from "vitest";

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { LINK_DEGRADADO, LINK_OPERATIVO, LINK_SIN_ENLACE, LINK_SIN_GABINETE } from "./link";
import { INCIDENT_ORDERS, consoleKpis, orderIncidents, showingLabel, sitesInBounds } from "./stats";
import type { LiveIncident } from "./useLiveIncidents";

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

function incident(id: string, over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: id,
    tenant_id: "t-1",
    site_id: id,
    event_id: null,
    opened_at: "2026-08-04T11:59:00Z",
    closed_at: null,
    severity: "warning",
    state: "open",
    trigger: "sasmex",
    max_pga_g: null,
    max_pgv_cms: null,
    ...over,
  };
}

const MEXICO = { west: -100, south: 18, east: -97, north: 20 };

describe("sitesInBounds — el contador va atado al VIEWPORT", () => {
  it("deja fuera lo que no se está viendo", () => {
    const dentro = site("in", { lon: -98.3, lat: 19.06 });
    const fuera = site("out", { lon: -103, lat: 25 });
    expect(sitesInBounds([dentro, fuera], MEXICO).map((s) => s.site_id)).toEqual(["in"]);
  });

  it("sin bounds (mapa aún sin montar) devuelve TODO: no se inventa un recorte", () => {
    expect(sitesInBounds([site("a"), site("b")], null)).toHaveLength(2);
  });

  it("el borde cuenta como dentro (un punto justo en la esquina se ve)", () => {
    expect(sitesInBounds([site("e", { lon: -100, lat: 18 })], MEXICO)).toHaveLength(1);
  });

  it("un viewport que cruza el antimeridiano no vacía el mapa", () => {
    // Al arrastrar el mapa, MapLibre devuelve west > east. Un `>=/<=` ingenuo
    // dejaría 0 estaciones y el operador vería el wall vacío sin motivo.
    const cruzado = { west: 170, south: -10, east: -170, north: 10 };
    const este = site("e", { lon: 175, lat: 0 });
    const oeste = site("o", { lon: -175, lat: 0 });
    const medio = site("m", { lon: 0, lat: 0 });
    const ids = sitesInBounds([este, oeste, medio], cruzado).map((s) => s.site_id);
    expect(ids).toEqual(["e", "o"]);
  });
});

describe("showingLabel — la leyenda declara el recorte", () => {
  it("dice MOSTRANDO n DE N cuando el viewport recorta", () => {
    expect(showingLabel(3, 12)).toBe("MOSTRANDO 3 DE 12");
  });

  it("sin recorte no miente con un 'de' innecesario", () => {
    expect(showingLabel(12, 12)).toBe("MOSTRANDO 12 DE 12");
  });
});

describe("consoleKpis — semáforo de flota, sin ceros inventados", () => {
  it("cuenta por estado de enlace, sin colapsar SIN GABINETE con SIN ENLACE", () => {
    const k = consoleKpis(
      [
        site("a", { link_state: LINK_OPERATIVO }),
        site("b", { link_state: LINK_DEGRADADO }),
        site("c", { link_state: LINK_SIN_ENLACE }),
        site("d", { link_state: LINK_SIN_GABINETE }),
        site("e", {}), // sin campo ⇒ SIN GABINETE (default honesto)
      ],
      [],
    );
    expect(k.stations).toBe(5);
    expect(k.operativo).toBe(1);
    expect(k.degradado).toBe(1);
    expect(k.sinEnlace).toBe(1);
    expect(k.sinGabinete).toBe(2);
  });

  it("sin ninguna métrica de latencia devuelve null, JAMÁS 0 ms", () => {
    // "0 ms" se lee como un enlace perfecto; "S/D" se lee como lo que es.
    const k = consoleKpis([site("a"), site("b")], []);
    expect(k.rttP50Ms).toBeNull();
    expect(k.rttMaxMs).toBeNull();
    expect(k.lagMaxS).toBeNull();
  });

  it("la mediana y el máximo del RTT salen solo de quien lo reportó", () => {
    const k = consoleKpis(
      [
        site("a", { link_state: LINK_OPERATIVO, mqtt_rtt_ms: 40 }),
        site("b", { link_state: LINK_OPERATIVO, mqtt_rtt_ms: 60 }),
        site("c", { link_state: LINK_OPERATIVO, mqtt_rtt_ms: 200 }),
        site("d", { link_state: LINK_SIN_GABINETE }), // no reporta: no cuenta
      ],
      [],
    );
    expect(k.rttP50Ms).toBe(60);
    expect(k.rttMaxMs).toBe(200);
  });

  it("cuenta la sacudida medida por banda, con `unknown` aparte de `normal`", () => {
    const k = consoleKpis(
      [
        site("a", { felt: "trip" }),
        site("b", { felt: "watch" }),
        site("c", { felt: "normal" }),
        site("d", { felt: "unknown" }),
      ],
      [],
    );
    expect(k.trip).toBe(1);
    expect(k.watch).toBe(1);
    expect(k.normal).toBe(1);
    expect(k.feltDesconocido).toBe(1);
  });

  it("las CAÍDAS son las estaciones que perdieron el enlace, no las que no lo tienen", () => {
    const k = consoleKpis(
      [site("a", { link_state: LINK_SIN_ENLACE }), site("b", { link_state: LINK_SIN_GABINETE })],
      [],
    );
    expect(k.sinEnlace).toBe(1);
  });

  it("cuenta incidentes abiertos y críticos", () => {
    const k = consoleKpis(
      [site("a")],
      [incident("i1", { severity: "critical" }), incident("i2", { severity: "warning" })],
    );
    expect(k.incidentesAbiertos).toBe(2);
    expect(k.incidentesCriticos).toBe(1);
  });
});

describe("orderIncidents — cinco órdenes, todos deterministas", () => {
  const critico = incident("i-crit", { severity: "critical", opened_at: "2026-08-04T11:00:00Z" });
  const reciente = incident("i-new", { severity: "info", opened_at: "2026-08-04T11:59:50Z" });
  const fuerte = incident("i-pga", { severity: "warning", max_pga_g: 0.9 });
  const todos = [reciente, fuerte, critico];

  it("expone exactamente los cinco criterios del plan", () => {
    expect(INCIDENT_ORDERS.map((o) => o.key)).toEqual([
      "severity",
      "recent",
      "pga",
      "age",
      "distance",
    ]);
  });

  it("severidad: crítico primero", () => {
    expect(orderIncidents(todos, "severity", {})[0].incident_id).toBe("i-crit");
  });

  it("más reciente: el último que abrió", () => {
    expect(orderIncidents(todos, "recent", {})[0].incident_id).toBe("i-new");
  });

  it("edad: el que lleva más tiempo esperando", () => {
    expect(orderIncidents(todos, "age", {})[0].incident_id).toBe("i-crit");
  });

  it("PGA: el pico más alto primero; los SIN MEDICIÓN caen al final, no valen 0", () => {
    const ordenado = orderIncidents(todos, "pga", {});
    expect(ordenado[0].incident_id).toBe("i-pga");
    // Un incidente sin pico medido no puede colarse por encima de uno con pico
    // pequeño simulando un 0: "no sabemos" no es "no se movió".
    const conCero = incident("i-cero", { max_pga_g: 0.0001 });
    const sinDato = incident("i-nd", { max_pga_g: null });
    expect(orderIncidents([sinDato, conCero], "pga", {}).map((i) => i.incident_id)).toEqual([
      "i-cero",
      "i-nd",
    ]);
  });

  it("distancia al epicentro: la estación más cercana primero", () => {
    const epicentro: MapEpicenter = {
      event_id: "E",
      source: "sasmex",
      lon: -98.3,
      lat: 19.06,
      magnitude: null,
      depth_km: null,
      detected_at: "2026-08-04T11:59:30Z",
    };
    const cerca = incident("cerca", { site_id: "s-cerca" });
    const lejos = incident("lejos", { site_id: "s-lejos" });
    const ctx = {
      epicenter: epicentro,
      siteById: new Map([
        ["s-cerca", site("s-cerca", { lon: -98.31, lat: 19.07 })],
        ["s-lejos", site("s-lejos", { lon: -95.0, lat: 16.0 })],
      ]),
    };
    expect(orderIncidents([lejos, cerca], "distance", ctx).map((i) => i.incident_id)).toEqual([
      "cerca",
      "lejos",
    ]);
  });

  it("sin epicentro conocido, ordenar por distancia NO reordena al azar", () => {
    // Se degrada al orden por severidad y la UI lo declara: barajar las filas
    // fingiendo una distancia que nadie midió sería peor que no ordenar.
    const ordenado = orderIncidents(todos, "distance", {});
    expect(ordenado[0].incident_id).toBe("i-crit");
  });

  it("no muta el array de entrada (la cola vive en react-query)", () => {
    const entrada = [...todos];
    orderIncidents(entrada, "severity", {});
    expect(entrada.map((i) => i.incident_id)).toEqual(todos.map((i) => i.incident_id));
  });
});
