import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

const mocks = vi.hoisted(() => {
  const handlers = new Map<string, (event?: unknown) => void>();
  const map = {
    on: vi.fn((event: string, layerOrCb: unknown, cb?: (event?: unknown) => void) => {
      if (typeof layerOrCb === "function") handlers.set(event, layerOrCb as () => void);
      else if (cb) handlers.set(`${event}:${layerOrCb as string}`, cb);
    }),
    addSource: vi.fn(),
    addLayer: vi.fn(),
    getSource: vi.fn(() => ({ setData: vi.fn() })),
    setPaintProperty: vi.fn(),
    remove: vi.fn(),
  };
  return { handlers, map, Map: vi.fn(() => map) };
});

vi.mock("maplibre-gl", () => ({ default: { Map: mocks.Map } }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import MapPanel, { criticalFeatures, siteSeverity, sitesToFeatureCollection } from "./MapPanel";

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
  it("crea el mapa, agrega capas al load y despacha el clic en site-core", () => {
    const onSelectSite = vi.fn();
    render(<MapPanel sites={[CRITICAL]} onSelectSite={onSelectSite} />);
    expect(mocks.Map).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();

    mocks.handlers.get("load")?.();
    expect(mocks.map.addSource).toHaveBeenCalledWith("sites", expect.anything());
    expect(mocks.map.addSource).toHaveBeenCalledWith("critical", expect.anything());
    expect(mocks.map.addLayer).toHaveBeenCalled();

    mocks.handlers.get("click:site-core")?.({
      features: [{ properties: { site_id: "crit" } }],
    });
    expect(onSelectSite).toHaveBeenCalledWith("crit");
  });
});
