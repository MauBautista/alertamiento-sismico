import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const mapHandlers = new Map<string, (event?: unknown) => void>();
  const markerHandlers = new Map<string, () => void>();
  const marker = {
    setLngLat: vi.fn().mockReturnThis(),
    addTo: vi.fn().mockReturnThis(),
    on: vi.fn((event: string, cb: () => void) => {
      markerHandlers.set(event, cb);
      return marker;
    }),
    getLngLat: vi.fn(() => ({ lng: -98.3, lat: 19.06 })),
  };
  const map = {
    on: vi.fn((event: string, cb: (event?: unknown) => void) => {
      mapHandlers.set(event, cb);
    }),
    remove: vi.fn(),
  };
  return {
    mapHandlers,
    markerHandlers,
    marker,
    map,
    Map: vi.fn(() => map),
    Marker: vi.fn(() => marker),
  };
});

vi.mock("maplibre-gl", () => ({
  default: { Map: mocks.Map, Marker: mocks.Marker },
  Map: mocks.Map,
  Marker: mocks.Marker,
}));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import MapPointPicker from "./MapPointPicker";

const START = { lon: -98.2, lat: 19.04 };

describe("MapPointPicker", () => {
  it("es un componente propio, no una sobrecarga de MapPanel", () => {
    render(<MapPointPicker value={START} onChange={vi.fn()} />);
    expect(screen.getByTestId("map-point-picker")).toBeInTheDocument();
    // El wall de la consola nunca se monta aquí.
    expect(screen.queryByTestId("map-panel")).toBeNull();
  });

  it("muestra las coordenadas de la prop, no un estado interno", () => {
    render(<MapPointPicker value={{ lat: 19.0633, lon: -98.3014 }} onChange={vi.fn()} />);
    expect(screen.getByTestId("picker-coords")).toHaveTextContent("19.0633°N · 98.3014°W");
  });

  it("arrastrar el marcador NOTIFICA la coordenada redondeada", () => {
    const onChange = vi.fn();
    render(<MapPointPicker value={START} onChange={onChange} />);

    mocks.markerHandlers.get("dragend")?.();
    expect(onChange).toHaveBeenCalledWith({ lon: -98.3, lat: 19.06 });
  });

  it("un clic en el mapa también coloca la estación", () => {
    const onChange = vi.fn();
    render(<MapPointPicker value={START} onChange={onChange} />);

    mocks.mapHandlers.get("click")?.({ lngLat: { lng: -99.1332, lat: 19.4326 } });
    expect(onChange).toHaveBeenCalledWith({ lon: -99.1332, lat: 19.4326 });
  });

  it("en modo lectura el marcador no se arrastra ni el mapa acepta clics", () => {
    mocks.mapHandlers.clear();
    render(<MapPointPicker value={START} onChange={vi.fn()} disabled />);
    expect(mocks.Marker).toHaveBeenLastCalledWith(expect.objectContaining({ draggable: false }));
    expect(mocks.mapHandlers.has("click")).toBe(false);
  });
});
