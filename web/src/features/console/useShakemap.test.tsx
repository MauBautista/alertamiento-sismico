// [T-7.24] El camino del mapa de la sacudida: que la consulta SE HAGA, contra la
// ruta que el router publica, y que sus cuatro estados sean distinguibles.
//
// Sin esta pieza `MapPanel` estrenaba props que nadie alimentaba. Lo que se
// prueba aquí, entonces, no es react-query: es que exista un cliente para
// `GET /incidents/{id}/shakemap` y que no confunda «falló» con «no hay».

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ client: { get: vi.fn() } }));
vi.mock("@takab/sdk", () => sdk);

import { ESTADO_PENDIENTE, type ShakemapOut } from "./shakemap";
import { SHAKEMAP_PENDING_POLL_MS, SHAKEMAP_URL, useShakemap } from "./useShakemap";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SNAPSHOT: ShakemapOut = {
  incident_id: "i-1",
  estado: "completo",
  calculado_en: "2026-09-14T10:41:30Z",
  ley: "ATTEN-LAW v1",
  cobertura_km: 25,
  epicentro: null,
  fuera_de_alcance: [],
  observado: { type: "FeatureCollection", features: [] },
  modelado: null,
};

describe("useShakemap · la consola PREGUNTA por el mapa de la sacudida", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("pide el snapshot del incidente, por la ruta que publica el router", () => {
    sdk.client.get.mockResolvedValue({ data: SNAPSHOT, response: { status: 200 } });
    renderHook(() => useShakemap("i-1"), { wrapper });
    // La ruta, literal: es el contrato con `api/src/takab_api/routers/shakemap.py`
    // y lo único que un `grep` puede cruzar mientras el SDK no la publique.
    expect(SHAKEMAP_URL).toBe("/incidents/{incident_id}/shakemap");
    expect(sdk.client.get).toHaveBeenCalledWith({
      url: SHAKEMAP_URL,
      path: { incident_id: "i-1" },
    });
  });

  it("sin incidente enfocado NO consulta nada, y eso no es ni error ni espera", async () => {
    sdk.client.get.mockResolvedValue({ data: SNAPSHOT, response: { status: 200 } });
    const { result } = renderHook(() => useShakemap(null), { wrapper });
    expect(sdk.client.get).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(false);
  });

  /** El fallo tal como quedó registrado, para poder leer QUÉ se declaró. */
  async function fallo(respuesta: unknown): Promise<{ error: boolean; causa: string }> {
    const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const envoltura = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={q}>{children}</QueryClientProvider>
    );
    sdk.client.get.mockResolvedValue(respuesta);
    const { result } = renderHook(() => useShakemap("i-1"), { wrapper: envoltura });
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.data).toBeNull();
    const consulta = q.getQueryCache().find({ queryKey: ["shakemap", "i-1"] });
    return { error: result.current.error, causa: String(consulta?.state.error ?? "") };
  }

  it("el fallo se declara ERROR CON SU CAUSA, y jamás vuelve como un mapa vacío", async () => {
    // Un 503 devuelto como `data: undefined` se leería aguas abajo como «este
    // incidente no tiene mapa», que es la confusión que la regla de oro 7
    // prohíbe en cada superficie de este repositorio.
    //
    // ⚠️ Y la causa se comprueba, no sólo la bandera: quitando el `throw` de
    // `queryFn` esta prueba seguía VERDE, porque react-query rechaza igual un
    // `undefined` con un error suyo («Query data cannot be undefined»). La
    // bandera acertaba por accidente y la guarda no medía nada.
    const r = await fallo({ error: { detail: "boom" }, response: { status: 503 } });
    expect(r.causa, "el fallo tiene que citar el endpoint y su status").toContain("503");
    expect(r.causa).toContain("/incidents/{incident_id}/shakemap");
  });

  it("un cuerpo ausente con 200 tampoco pasa por mapa: es un fallo, y lo dice", async () => {
    const r = await fallo({ data: undefined, response: { status: 200 } });
    expect(r.causa).toContain("/incidents/{incident_id}/shakemap");
    expect(r.causa).toContain("200");
  });

  it("`pendiente` es lo ÚNICO que se vuelve a preguntar solo", async () => {
    // Es la única respuesta que se sabe transitoria (200, no 404: el worker aún
    // no pasó). El mapa de un sismo que ya ocurrió no cambia mientras se mira, y
    // repreguntarlo sería pedirle a la nube que rehaga la misma ventana.
    const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const envoltura = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={q}>{children}</QueryClientProvider>
    );
    sdk.client.get.mockResolvedValue({
      data: { ...SNAPSHOT, estado: ESTADO_PENDIENTE },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useShakemap("i-1"), { wrapper: envoltura });
    await waitFor(() => expect(result.current.data?.estado).toBe(ESTADO_PENDIENTE));
    type Sondeo = (consulta: unknown) => number | false;
    const buscar = () => q.getQueryCache().find({ queryKey: ["shakemap", "i-1"] });
    const intervalo = (buscar()?.options as { refetchInterval?: unknown } | undefined)
      ?.refetchInterval as Sondeo | undefined;
    expect(typeof intervalo, "el sondeo se DERIVA del estado, no es una constante").toBe(
      "function",
    );
    expect(intervalo!(buscar())).toBe(SHAKEMAP_PENDING_POLL_MS);

    sdk.client.get.mockResolvedValue({ data: SNAPSHOT, response: { status: 200 } });
    await result.current.refetch();
    await waitFor(() => expect(result.current.data?.estado).toBe("completo"));
    expect(intervalo!(buscar()), "un mapa ya calculado no se vuelve a pedir solo").toBe(false);
  });
});
