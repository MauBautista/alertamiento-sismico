import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, applyFilters, isFiltering, matchesQuery } from "./fleetFilter";
import type { FleetCabinet } from "./useFleet";

function cabinet(over: {
  id: string;
  name?: string;
  code?: string;
  serial?: string;
  thing?: string | null;
  state?: string;
  hb?: string | null;
}): FleetCabinet {
  return {
    gateway: {
      gateway_id: over.id,
      site_id: `s-${over.id}`,
      site_name: over.name ?? `Sitio ${over.id}`,
      site_code: over.code ?? `C-${over.id}`,
      site_status: "active",
      serial: over.serial ?? `TKB-${over.id}`,
      fw_version: null,
      iot_thing: over.thing === undefined ? `gw-${over.id}` : over.thing,
      status: "online",
      has_wr1: true,
      installed_at: null,
      row_version: "1",
      derived_state: over.state ?? "OPERATIVO",
      degrade_reasons: [],
      last_heartbeat_ts: over.hb === undefined ? "2026-08-03T10:00:00Z" : over.hb,
      power_status: null,
      battery_pct: null,
      cert_days_remaining: null,
      mqtt_rtt_ms: null,
      seedlink_lag_s: null,
      ntp_offset_ms: null,
    },
    siteName: over.name ?? `Sitio ${over.id}`,
    siteCode: over.code ?? `C-${over.id}`,
    siteStatus: "active",
    relays: null,
  };
}

const OK = cabinet({ id: "1", name: "Torre Norte", code: "TN", state: "OPERATIVO" });
const WARN = cabinet({ id: "2", name: "Hospital Sur", code: "HS", state: "DEGRADADO" });
const DEAD = cabinet({
  id: "3",
  name: "Almacén",
  code: "AL",
  state: "SIN ENLACE",
  hb: null,
});
const ALL = [OK, WARN, DEAD];

describe("matchesQuery · los cuatro identificadores que un técnico tiene a mano", () => {
  it("casa por nombre de estación", () => {
    expect(matchesQuery(OK, "torre")).toBe(true);
  });
  it("casa por código", () => {
    expect(matchesQuery(WARN, "hs")).toBe(true);
  });
  it("casa por serial", () => {
    expect(matchesQuery(OK, "TKB-1")).toBe(true);
  });
  it("casa por iot thing", () => {
    expect(matchesQuery(OK, "gw-1")).toBe(true);
  });
  it("una consulta vacía no filtra nada", () => {
    expect(ALL.every((c) => matchesQuery(c, "   "))).toBe(true);
  });
  it("un gabinete sin iot thing no revienta la búsqueda", () => {
    expect(matchesQuery(cabinet({ id: "9", thing: null }), "sitio")).toBe(true);
  });
});

describe("applyFilters", () => {
  it("por defecto ordena PEOR PRIMERO: se abre la pantalla para ver qué está roto", () => {
    expect(applyFilters(ALL, DEFAULT_FILTERS).map((c) => c.gateway.gateway_id)).toEqual([
      "3",
      "2",
      "1",
    ]);
  });

  it("un derived_state desconocido va al frente, no entre los sanos", () => {
    const raro = cabinet({ id: "4", state: "LO-QUE-SEA" });
    const [first] = applyFilters([OK, raro], DEFAULT_FILTERS);
    expect(first.gateway.gateway_id).toBe("4");
  });

  it("ordenar por último latido pone PRIMERO al que no tiene", () => {
    const rows = applyFilters(ALL, { ...DEFAULT_FILTERS, sort: "latido" });
    expect(rows[0].gateway.gateway_id).toBe("3");
  });

  it("ordena por nombre de estación", () => {
    const rows = applyFilters(ALL, { ...DEFAULT_FILTERS, sort: "nombre" });
    expect(rows.map((c) => c.siteName)).toEqual(["Almacén", "Hospital Sur", "Torre Norte"]);
  });

  it("OCULTAR SIN ENLACE quita solo los caídos", () => {
    const rows = applyFilters(ALL, { ...DEFAULT_FILTERS, hideOffline: true });
    expect(rows.map((c) => c.gateway.gateway_id)).toEqual(["2", "1"]);
  });

  it("no muta el arreglo de entrada", () => {
    const original = [...ALL];
    applyFilters(ALL, { ...DEFAULT_FILTERS, sort: "nombre" });
    expect(ALL).toEqual(original);
  });

  it("una consulta sin resultados devuelve vacío, no todo", () => {
    expect(applyFilters(ALL, { ...DEFAULT_FILTERS, query: "zzz" })).toEqual([]);
  });
});

describe("isFiltering · distingue 'no hay nada' de 'no hay nada CON ESTE FILTRO'", () => {
  it("los valores por defecto no son un filtro", () => {
    expect(isFiltering(DEFAULT_FILTERS)).toBe(false);
  });
  it("una búsqueda sí", () => {
    expect(isFiltering({ ...DEFAULT_FILTERS, query: "a" })).toBe(true);
  });
  it("ocultar sin enlace sí", () => {
    expect(isFiltering({ ...DEFAULT_FILTERS, hideOffline: true })).toBe(true);
  });
  it("cambiar el orden NO es filtrar: se ve lo mismo", () => {
    expect(isFiltering({ ...DEFAULT_FILTERS, sort: "nombre" })).toBe(false);
  });
});
