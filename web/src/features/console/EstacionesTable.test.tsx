// [T-7.17] La red de estaciones: lo que la tabla dice y lo que se niega a decir.
//
// Casi todo lo que se fija aquí es que NO se rellena un hueco:
//
// · Sin epicentro no hay distancia ni arribo esperado. Rellenarlos con una
//   estimación sería presentar una simulación como si fuera la medición.
// · `tier` vacío no es `normal`: el gabinete no dijo que estuviera en calma,
//   no dijo nada (regla de oro 7).
// · El desfase solo existe si existen sus dos sumandos.
//
// Y una que sí es afirmativa: el ORDEN es el del servidor, que es el orden en
// que ocurrió. Reordenar aquí haría que dos superficies contaran la misma
// secuencia de dos maneras.

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EstacionOut, EstacionesOut } from "@takab/sdk";
import EstacionesTable, { desfase } from "./EstacionesTable";
import type { EstacionesData } from "./useEstaciones";

function estacion(over: Partial<EstacionOut> = {}): EstacionOut {
  return {
    site_id: "s-1",
    site_code: "site-dev",
    site_name: "Edificio Central",
    sensor_code: "AM.R4F74",
    dist_km: 78.7,
    t_arribo_teorico_s: 19.7,
    t_arribo_medido_s: 20.0,
    peak_pga_g: 0.071,
    peak_ts: "2026-09-15T12:00:20Z",
    umbral_pga_g: 0.04,
    umbral_origen: "inmueble",
    tier: "evacuate_or_hold",
    counted: true,
    ...over,
  };
}

function datos(over: Partial<EstacionesOut> = {}): EstacionesOut {
  return {
    incident_id: "i-1",
    event_id: "EVT-REP-1",
    reproduccion: true,
    ancla: "event",
    ancla_ts: "2026-09-15T12:00:00Z",
    epicentro_lat: 18.55,
    epicentro_lon: -98.49,
    magnitude: 7.1,
    items: [estacion()],
    ...over,
  };
}

function hook(over: Partial<EstacionesData> = {}): EstacionesData {
  return {
    data: datos(),
    loading: false,
    error: false,
    updatedAt: 1,
    refetch: vi.fn(),
    ...over,
  };
}

function pintar(over: Partial<EstacionesData> = {}) {
  return render(<EstacionesTable estaciones={hook(over)} />);
}

describe("desfase · solo existe si existen sus dos sumandos", () => {
  it("resta medido − esperado y lleva signo", () => {
    expect(desfase(19.7, 20.0)).toBe("+0.3s");
    expect(desfase(25.3, 24.1)).toBe("-1.2s");
  });

  it("sin cualquiera de los dos es S/D, no cero", () => {
    expect(desfase(null, 20)).toBe("S/D");
    expect(desfase(20, null)).toBe("S/D");
    expect(desfase(undefined, undefined)).toBe("S/D");
  });
});

describe("EstacionesTable · lo medido junto a lo esperado", () => {
  it("pinta la fila con las dos columnas y su desfase", () => {
    pintar();
    const fila = screen.getByTestId("estacion-site-dev");
    expect(within(fila).getByText("Edificio Central")).toBeInTheDocument();
    expect(fila.textContent).toContain("AM.R4F74");
    expect(fila.textContent).toContain("79 km");
    expect(fila.textContent).toContain("+19.7s");
    expect(fila.textContent).toContain("+20.0s");
    expect(fila.textContent).toContain("+0.3s");
    expect(fila.textContent).toContain("0.071 g");
    expect(fila.textContent).toContain("evacuate_or_hold");
  });

  it("respeta el ORDEN del servidor, que es el del arribo", () => {
    pintar({
      data: datos({
        items: [
          estacion({ site_id: "a", site_code: "z-cerca", t_arribo_teorico_s: 19.7 }),
          estacion({ site_id: "b", site_code: "a-lejos", t_arribo_teorico_s: 38.7 }),
        ],
      }),
    });
    const filas = screen.getAllByTestId(/^estacion-/);
    expect(filas.map((f) => f.dataset.testid)).toEqual(["estacion-z-cerca", "estacion-a-lejos"]);
  });

  it("declara desde dónde se cuentan los arribos", () => {
    pintar();
    expect(screen.getByText(/ARRIBOS DESDE EL ORIGEN DEL SISMO/)).toBeInTheDocument();
    expect(screen.getByText(/REPRODUCCIÓN/)).toBeInTheDocument();

    pintar({ data: datos({ ancla: "incident", reproduccion: false }) });
    expect(screen.getByText(/ARRIBOS DESDE LA APERTURA DEL INCIDENTE/)).toBeInTheDocument();
  });
});

describe("EstacionesTable · lo que se niega a inventar", () => {
  it("sin epicentro, distancia y arribo esperado van en S/D — y el pico SIGUE", () => {
    pintar({
      data: datos({
        reproduccion: false,
        epicentro_lat: null,
        epicentro_lon: null,
        items: [estacion({ dist_km: null, t_arribo_teorico_s: null })],
      }),
    });
    const fila = screen.getByTestId("estacion-site-dev");
    expect(fila.textContent).toContain("S/D");
    expect(fila.textContent).toContain("0.071 g");
  });

  it("tier vacío se escribe S/D y no `normal`", () => {
    pintar({ data: datos({ items: [estacion({ tier: null })] }) });
    const fila = screen.getByTestId("estacion-site-dev");
    expect(fila.textContent).not.toContain("normal");
    expect(fila.textContent).toContain("S/D");
  });

  it("un sitio de DEMOSTRACIÓN lleva su cinta", () => {
    pintar({ data: datos({ items: [estacion({ site_code: "site-sim-101" })] }) });
    expect(screen.getByTestId("site-demo")).toBeInTheDocument();
  });

  it("el umbral viaja con su procedencia, aunque sea en el título", () => {
    pintar({ data: datos({ items: [estacion({ umbral_origen: "referencia" })] }) });
    const celda = screen.getByTitle(/umbral 0.040 g · referencia/);
    expect(celda).toBeInTheDocument();
  });
});

describe("EstacionesTable · los cuatro estados (regla de oro 7)", () => {
  it("cargando no pinta una tabla vacía", () => {
    pintar({ data: null, loading: true });
    expect(screen.queryByTestId(/^estacion-/)).toBeNull();
  });

  it("con error lo dice y ofrece reintentar", () => {
    const refetch = vi.fn();
    pintar({ data: null, error: true, refetch });
    expect(screen.getByText(/no se pudo leer la red de estaciones/)).toBeInTheDocument();
  });

  it("vacío declara que el cliente no tiene estaciones, no cero mediciones", () => {
    pintar({ data: datos({ items: [] }) });
    expect(screen.getByText(/NO TIENE ESTACIONES CON GABINETE ACTIVO/)).toBeInTheDocument();
  });
});
