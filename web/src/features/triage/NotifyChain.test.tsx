// [T-5.15] La cadena de aviso en pantalla.
//
// La aserción que gobierna el archivo: **`sent` no es `delivered`, y `simulated`
// no es ninguno de los dos**. La tabla distingue seis estados desde la `0040`;
// una pantalla que los pinte todos igual desharía la única razón por la que esa
// migración existe, y contestaría «sí, le llegó» a la pregunta del día
// siguiente cuando la respuesta es «no lo sabemos» o «no llegó».

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useNotifyChain: vi.fn() }));
vi.mock("./useNotifyChain", async () => ({
  ...(await vi.importActual<typeof import("./useNotifyChain")>("./useNotifyChain")),
  useNotifyChain: mocks.useNotifyChain,
}));

import { expectFourStates, type UiState } from "../../test-utils/states";
import NotifyChain, { desenlace, destinatario } from "./NotifyChain";
import type { NotifyChainData } from "./useNotifyChain";

const NOW = Date.parse("2026-09-02T18:10:00Z");

function job(over: Record<string, unknown> = {}) {
  return {
    job_id: "j-1",
    channel: "email",
    mode: "cascade",
    position: 0,
    status: "sent",
    delivered: false,
    created_at: "2026-09-02T18:00:00Z",
    due_at: "2026-09-02T18:00:00Z",
    deadline_at: null,
    sent_at: "2026-09-02T18:00:03Z",
    delivered_at: null,
    last_status: "sent",
    last_status_at: null,
    attempts: 1,
    error: null,
    dispatch_latency_s: 3,
    delivery_latency_s: null,
    deadline_met: null,
    recipient: { kind: "correo", count: 1, hint: "o***@cliente.com", unrecognised: false },
    action_id: null,
    ...over,
  };
}

function cadena(over: Partial<NotifyChainData> = {}): NotifyChainData {
  return {
    items: [job()] as never,
    deliveredCount: 0,
    loading: false,
    readError: false,
    staleSince: null,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useNotifyChain.mockReturnValue(cadena());
});

describe("desenlace", () => {
  it("ACEPTADO POR EL PROVEEDOR no es ENTREGADO", () => {
    expect(desenlace(job() as never).label).toBe("ACEPTADO POR EL PROVEEDOR");
    expect(desenlace(job({ delivered: true }) as never).label).toBe("ENTREGADO");
  });

  it("simulado dice en voz alta que no lo recibió nadie", () => {
    expect(desenlace(job({ status: "simulated" }) as never).label).toContain("NO LO RECIBIÓ NADIE");
  });

  it("los seis estados de la tabla tienen rótulo propio, sin repetirse", () => {
    const seis = ["pending", "sent", "failed", "skipped", "simulated", "blocked_demo"];
    const labels = seis.map((s) => desenlace(job({ status: s }) as never).label);
    expect(new Set(labels).size).toBe(6);
    // Y ninguno de los seis, por sí solo, dice «entregado».
    expect(labels.some((l) => l === "ENTREGADO")).toBe(false);
  });

  it("un estado NUEVO no cae en «entregado»: se declara sin clasificar", () => {
    expect(desenlace(job({ status: "teletransportado" }) as never).label).toContain(
      "SIN CLASIFICAR",
    );
  });
});

describe("destinatario", () => {
  it("pinta lo que el servidor dejó decir, sin enmascarar aquí", () => {
    expect(destinatario(job() as never)).toBe("o***@cliente.com");
  });

  it("con varios destinatarios dice cuántos", () => {
    const j = job({
      recipient: { kind: "correo", count: 3, hint: "o***@c.com", unrecognised: false },
    });
    expect(destinatario(j as never)).toBe("o***@c.com (3)");
  });

  it("un destinatario no reconocido se DECLARA, no se deja en blanco", () => {
    const j = job({
      recipient: { kind: "desconocido", count: null, hint: "", unrecognised: true },
    });
    expect(destinatario(j as never)).toBe("DESTINATARIO NO RECONOCIDO");
  });
});

describe("NotifyChain", () => {
  it("el que salió pero no confirmó enseña UNA latencia, no dos", () => {
    render(<NotifyChain incidentId="i-1" />);
    const lat = screen.getByTestId("chain-lat-j-1");
    expect(lat).toHaveTextContent("SALIÓ +0:03");
    expect(lat).not.toHaveTextContent("LLEGÓ");
  });

  it("el entregado enseña los DOS tramos, sin sumarlos", () => {
    // El segundo tramo no depende de TAKAB: sumarlos culparía a la plataforma
    // de los tres minutos que tardó el operador móvil.
    mocks.useNotifyChain.mockReturnValue(
      cadena({
        items: [job({ delivered: true, delivery_latency_s: 15 })] as never,
        deliveredCount: 1,
      }),
    );
    render(<NotifyChain incidentId="i-1" />);
    const lat = screen.getByTestId("chain-lat-j-1");
    expect(lat).toHaveTextContent("SALIÓ +0:03");
    expect(lat).toHaveTextContent("LLEGÓ +0:15 DESPUÉS");
    expect(lat).not.toHaveTextContent("+0:18"); // 3 + 15, que es lo que NO se pinta
  });

  it("el que no salió NO enseña un «+0:00» que diría que salió al instante", () => {
    mocks.useNotifyChain.mockReturnValue(
      cadena({
        items: [job({ status: "simulated", sent_at: null, dispatch_latency_s: null })] as never,
      }),
    );
    render(<NotifyChain incidentId="i-1" />);
    const lat = screen.getByTestId("chain-lat-j-1");
    expect(lat).toHaveTextContent("SALIDA S/D");
    expect(lat).not.toHaveTextContent("+0:00");
  });

  it("la cabecera cuenta los ENTREGADOS sobre el total", () => {
    mocks.useNotifyChain.mockReturnValue(
      cadena({
        items: [job({ delivered: true }), job({ job_id: "j-2" })] as never,
        deliveredCount: 1,
      }),
    );
    render(<NotifyChain incidentId="i-1" />);
    expect(screen.getByTestId("notify-chain")).toHaveTextContent("1 DE 2 ENTREGADOS");
  });

  it("con la consulta fallida NO hay recuento: «0 DE 0» diría que no se avisó a nadie", () => {
    // El recuento vive DENTRO del `StateFrame` justamente para esto: no depende
    // de que alguien se acuerde de escribir el caso de error. Es el defecto de
    // `T-2.59`, y aquí lo impide la estructura, no la disciplina.
    mocks.useNotifyChain.mockReturnValue(cadena({ items: [], readError: true }));
    render(<NotifyChain incidentId="i-1" />);
    expect(screen.getByTestId("notify-chain")).not.toHaveTextContent("ENTREGADOS");
  });

  it("declara los cuatro estados obligatorios", () => {
    const byState: Record<UiState, Partial<NotifyChainData>> = {
      loading: { loading: true },
      error: { items: [], readError: true },
      empty: { items: [] },
      // Con envíos ya cargados un fallo NO borra la evidencia: se declara vieja.
      stale: { staleSince: NOW - 600_000 },
    };
    expectFourStates((state) => {
      mocks.useNotifyChain.mockReturnValue(cadena(byState[state]));
      return <NotifyChain incidentId="i-1" />;
    });
  });
});
