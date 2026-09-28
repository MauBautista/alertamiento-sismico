// [T-9.66 · D-46] La tarjeta del HISTORIAL SÍSMICO DEL INMUEBLE en la pestaña
// SISMOS: los últimos cinco eventos, mezclados por fecha, y sus cuatro estados.
import type { HistorialIncidente, HistorialSismicoOut, HistorialSismo } from "@takab/sdk";
import { act, fireEvent, render, within } from "@testing-library/react-native";

import { HISTORIAL_MAX_FILAS, HistorialCard } from "./HistorialCard";
import type { LecturaSismica } from "./useSismos";

const AHORA = Date.now();

function incidente(over: Partial<HistorialIncidente> = {}): HistorialIncidente {
  return {
    tipo: "incidente",
    incident_id: "i-1",
    opened_at: "2026-09-21T10:00:00Z",
    severity: "warning",
    estado: "closed",
    clasificacion: "real",
    pga_medida_g: 0.0123,
    trigger: "sasmex",
    ...over,
  };
}

function sismoH(over: Partial<HistorialSismo> = {}): HistorialSismo {
  return {
    tipo: "sismo",
    origin_time: "2026-09-10T08:00:00Z",
    magnitude: 5.8,
    place: "Costa de Guerrero",
    dist_km: 240.6,
    mmi_estimada: 4.4,
    mmi_romano: "IV",
    usgs_url: null,
    ...over,
  };
}

function lectura(
  over: Partial<LecturaSismica<HistorialSismicoOut>> = {},
): LecturaSismica<HistorialSismicoOut> {
  return {
    data: { atribucion: "Datos: USGS", eventos: [incidente(), sismoH()] },
    loading: false,
    error: null,
    staleSinceMs: null,
    refetch: jest.fn(),
    ...over,
  };
}

async function montar(l: LecturaSismica<HistorialSismicoOut>) {
  const v = await render(<HistorialCard lectura={l} nowMs={AHORA} />);
  await act(async () => {});
  return v;
}

describe("[T-9.66] el historial del inmueble en la app", () => {
  it("un incidente dice lo que MIDIÓ el gabinete; un sismo, lo ESTIMADO", async () => {
    const v = await montar(lectura());
    const [fInc, fSis] = v.getAllByTestId("historial-fila");
    expect(within(fInc).getByText(/INCIDENTE · ADVERTENCIA/)).toBeTruthy();
    expect(within(fInc).getByText(/Cerrado · Sismo real/)).toBeTruthy();
    expect(within(fInc).getByText("PGA medida: 0.012 g")).toBeTruthy();
    expect(within(fSis).getByText(/5\.8 · Costa de Guerrero/)).toBeTruthy();
    expect(within(fSis).getByText("MMI estimada: IV · 241 km")).toBeTruthy();
    expect(v.getByText("Datos: USGS")).toBeTruthy();
  });

  it("enseña como mucho los últimos cinco, en el orden de la nube", async () => {
    const eventos = Array.from({ length: 8 }, (_, i) =>
      sismoH({ place: `Lugar ${i}`, origin_time: `2026-09-${String(20 - i).padStart(2, "0")}T00:00:00Z` }),
    );
    const v = await montar(lectura({ data: { eventos } }));
    const filas = v.getAllByTestId("historial-fila");
    expect(HISTORIAL_MAX_FILAS).toBe(5);
    expect(filas).toHaveLength(5);
    expect(within(filas[0]).getByText(/Lugar 0/)).toBeTruthy();
    expect(within(filas[4]).getByText(/Lugar 4/)).toBeTruthy();
  });

  it("un incidente sin PGA ni clasificación no inventa ninguna de las dos", async () => {
    const v = await montar(
      lectura({ data: { eventos: [incidente({ pga_medida_g: null, clasificacion: null })] } }),
    );
    expect(v.getByText("PGA medida: sin dato")).toBeTruthy();
    expect(v.getByText(/sin clasificar/)).toBeTruthy();
  });

  it("cargando", async () => {
    const v = await montar(lectura({ data: null, loading: true }));
    expect(v.getByTestId("historial-loading")).toBeTruthy();
    expect(v.queryByTestId("historial-fila")).toBeNull();
  });

  it("vacío: lo dice, y no es lo mismo que un fallo", async () => {
    const v = await montar(lectura({ data: { eventos: [] } }));
    expect(v.getByTestId("historial-empty")).toHaveTextContent(/no registra incidentes ni sismos/);
    expect(v.queryByTestId("historial-error")).toBeNull();
  });

  it("error: lo dice y ofrece REINTENTAR, que vuelve a consultar", async () => {
    const l = lectura({ data: null, error: "No se pudo consultar el historial del inmueble." });
    const v = await montar(l);
    expect(v.getByTestId("historial-error")).toHaveTextContent(/No se pudo consultar/);
    await act(async () => {
      fireEvent.press(v.getByTestId("historial-retry"));
    });
    expect(l.refetch).toHaveBeenCalledTimes(1);
  });

  it("dato viejo: se pinta CON su edad", async () => {
    const v = await montar(lectura({ staleSinceMs: AHORA - 20 * 60_000 }));
    expect(v.getByTestId("historial-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getAllByTestId("historial-fila").length).toBeGreaterThan(0);
  });
});
