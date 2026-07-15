import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuorumVoteOut } from "@takab/sdk";

import QuorumNodes from "./QuorumNodes";
import type { QuorumNodesProps } from "./QuorumNodes";
import { quorumView } from "./model";

function vote(sensor: string, deltaS: number | null, counted = true): QuorumVoteOut {
  return {
    event_id: "evt-1",
    sensor_id: sensor,
    detected_at: "2026-07-08T10:00:00Z",
    pga_g: 0.1,
    delta_s: deltaS,
    counted,
  };
}

const VOTES = [
  vote("aaaaaaaa-1111-0000-0000-000000000001", 0),
  vote("bbbbbbbb-2222-0000-0000-000000000002", 1.42),
  vote("cccccccc-3333-0000-0000-000000000003", 3.07, false),
];

function props(over: Partial<QuorumNodesProps> = {}): QuorumNodesProps {
  return {
    view: quorumView(VOTES),
    eventState: "ready",
    eventError: null,
    corroborated: true,
    minNodes: 3,
    ...over,
  };
}

describe("QuorumNodes · offsets", () => {
  it("pinta los offsets del servidor VERBATIM (no los fabrica)", () => {
    render(<QuorumNodes {...props()} />);
    expect(screen.getByText("+0.00s")).toBeTruthy();
    expect(screen.getByText("+1.42s")).toBeTruthy();
    expect(screen.getByText("+3.07s")).toBeTruthy();
  });

  it("marca el ancla y rotula los nodos por sensor_id, no por códigos inventados", () => {
    render(<QuorumNodes {...props()} />);
    expect(screen.getByText(/AAAAAAAA · ANCLA/)).toBeTruthy();
    expect(screen.queryByText(/CHL-A|PUE-01/)).toBeNull();
  });

  it("un delta_s negativo lleva el signo (la ventana es simétrica)", () => {
    render(<QuorumNodes {...props({ view: quorumView([vote("x", -0.5), vote("y", 0)]) })} />);
    expect(screen.getByText("-0.50s")).toBeTruthy();
  });

  it("delta_s nulo se muestra S/D, no como 0", () => {
    render(<QuorumNodes {...props({ view: quorumView([vote("x", null)]) })} />);
    expect(screen.getByText("S/D")).toBeTruthy();
  });

  it("un voto no contado se pinta idle, no activo", () => {
    const { container } = render(<QuorumNodes {...props()} />);
    expect(container.querySelectorAll(".triage-node--active")).toHaveLength(2);
    expect(container.querySelectorAll(".triage-node--idle")).toHaveLength(1);
  });
});

describe("QuorumNodes · el veredicto es un hecho del servidor, no del cliente", () => {
  it("corroborated ⇒ CONFIRMADO con la cuenta real de estaciones", () => {
    render(<QuorumNodes {...props({ corroborated: true })} />);
    expect(screen.getByText(/CONFIRMADO · 2 estaciones/)).toBeTruthy();
  });

  it("evento de otra fuente (sasmex/manual) NO se anuncia como quórum", () => {
    render(<QuorumNodes {...props({ corroborated: false })} />);
    expect(screen.queryByText(/CONFIRMADO/)).toBeNull();
    expect(screen.getByText(/SIN CORROBORAR POR QUÓRUM/)).toBeTruthy();
  });

  it("NO compara countedNodes contra min_nodes: 2 nodos con mínimo 3 sigue siendo CUMPLIDO si el motor formó el evento", () => {
    // El motor prefiere el rule_set de SITIO y usa la versión vigente en su momento;
    // recalcular aquí produciría un "2/3 NODOS" que contradice al propio motor.
    render(<QuorumNodes {...props({ corroborated: true, minNodes: 3 })} />);
    expect(screen.getByText(/CONFIRMADO/)).toBeTruthy();
    expect(screen.queryByText(/2\/3/)).toBeNull();
  });

  it("min_nodes se muestra como CONTEXTO de configuración actual, no como veredicto", () => {
    render(<QuorumNodes {...props({ minNodes: 3 })} />);
    expect(screen.getByText(/MÍNIMO CONFIGURADO HOY: 3/)).toBeTruthy();
  });

  it("sin min_nodes configurado no se menciona ningún mínimo", () => {
    render(<QuorumNodes {...props({ minNodes: null })} />);
    expect(screen.queryByText(/MÍNIMO CONFIGURADO/)).toBeNull();
  });
});

describe("QuorumNodes · regla de oro 7 (los 4 estados del evento)", () => {
  it("incidente sin evento asociado: lo dice, y NO pinta veredicto alguno", () => {
    render(<QuorumNodes {...props({ eventState: "absent", view: quorumView([]) })} />);
    expect(screen.getByText(/SIN EVENTO SÍSMICO ASOCIADO/)).toBeTruthy();
    expect(screen.queryByText(/CONFIRMADO/)).toBeNull();
    expect(screen.queryByText(/EVENTO NO FORMADO POR QUÓRUM/)).toBeNull();
  });

  it("evento EN VUELO no se confunde con 'sin evento' ni fabrica veredicto", () => {
    const { container } = render(
      <QuorumNodes {...props({ eventState: "loading", view: quorumView([]) })} />,
    );
    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
    expect(screen.queryByText(/SIN EVENTO SÍSMICO ASOCIADO/)).toBeNull();
    expect(screen.queryByText(/CONFIRMADO/)).toBeNull();
  });

  it("evento FALLIDO se reporta como error, jamás como 'sin evento'", () => {
    const { container } = render(
      <QuorumNodes
        {...props({
          eventState: "error",
          eventError: "GET /events/{id} falló (500)",
          view: quorumView([]),
        })}
      />,
    );
    expect(container.querySelector('[data-state="error"]')).not.toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/500/);
    expect(screen.queryByText(/SIN EVENTO SÍSMICO ASOCIADO/)).toBeNull();
    expect(screen.queryByText(/CONFIRMADO/)).toBeNull();
  });

  it("evento cargado pero sin votos lo dice (empty), no lo confunde con error", () => {
    const { container } = render(
      <QuorumNodes
        {...props({ eventState: "ready", view: quorumView([]), corroborated: false })}
      />,
    );
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(screen.getByText(/SIN VOTOS DE QUÓRUM/)).toBeTruthy();
  });
});
