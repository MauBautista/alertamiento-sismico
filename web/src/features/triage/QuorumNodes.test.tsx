import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuorumVoteOut } from "@takab/sdk";

import QuorumNodes from "./QuorumNodes";
import type { QuorumNodesProps } from "./QuorumNodes";
import { quorumView } from "./model";

function vote(
  sensor: string,
  deltaS: number | null,
  counted = true,
  named: { site_code?: string | null; station_serial?: string | null } = {},
): QuorumVoteOut {
  return {
    event_id: "evt-1",
    sensor_id: sensor,
    detected_at: "2026-07-08T10:00:00Z",
    pga_g: 0.1,
    delta_s: deltaS,
    counted,
    // [T-2.39] El servidor resuelve el nombre BAJO RLS. Nulo = estación de otra red.
    site_code: named.site_code ?? null,
    station_serial: named.station_serial ?? null,
  };
}

const VOTES = [
  vote("aaaaaaaa-1111-0000-0000-000000000001", 0, true, { site_code: "TORRE-A" }),
  vote("bbbbbbbb-2222-0000-0000-000000000002", 1.42, true, { site_code: "HOSP-01" }),
  vote("cccccccc-3333-0000-0000-000000000003", 3.07, false),
];

function props(over: Partial<QuorumNodesProps> = {}): QuorumNodesProps {
  return {
    view: quorumView(VOTES),
    eventState: "ready",
    eventError: null,
    corroborated: true,
    minNodes: 3,
    eventStaleSince: null,
    incidentStaleSince: null,
    ...over,
  };
}

/** 2026-08-03 10:41:30 UTC — la hora que el marco tiene que imprimir. */
const HORA = Date.UTC(2026, 7, 3, 10, 41, 30);

describe("QuorumNodes · offsets", () => {
  it("pinta los offsets del servidor VERBATIM (no los fabrica)", () => {
    render(<QuorumNodes {...props()} />);
    expect(screen.getByText("+0.00s")).toBeTruthy();
    expect(screen.getByText("+1.42s")).toBeTruthy();
    expect(screen.getByText("+3.07s")).toBeTruthy();
  });

  // [T-2.39] El código lo resuelve el SERVIDOR bajo RLS; el cliente no lo inventa ni
  // lo deduce. Antes se pintaban ocho hex de un uuid, que en una sala de crisis no
  // identifican nada.
  it("marca el ancla y rotula los nodos con el código que da el servidor", () => {
    render(<QuorumNodes {...props()} />);
    expect(screen.getByText(/TORRE-A · ANCLA/)).toBeTruthy();
    expect(screen.getByText("HOSP-01")).toBeTruthy();
    expect(screen.queryByText(/AAAAAAAA/)).toBeNull();
  });

  // Que la RLS oculte el sensor NO es un fallo: es el hecho de que el voto viene de
  // otro cliente de la red. Inventarle una etiqueta sería peor que el uuid.
  it("un voto que la RLS oculta se rotula OTRA RED, no con un uuid", () => {
    render(<QuorumNodes {...props()} />);
    expect(screen.getByText("OTRA RED")).toBeTruthy();
    expect(screen.queryByText(/CCCCCCCC/)).toBeNull();
  });

  it("prefiere el código de sitio al serial del sensor", () => {
    const view = quorumView([
      vote("s-1", 0, true, { site_code: "TORRE-A", station_serial: "RS4D-9" }),
      vote("s-2", 1, true, { station_serial: "RS4D-7" }),
    ]);
    render(<QuorumNodes {...props({ view })} />);
    expect(screen.getByText(/TORRE-A/)).toBeTruthy();
    expect(screen.getByText("RS4D-7")).toBeTruthy();
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

/* =====================================================================
   T-2.82.a · DOS ramas, DOS datos, DOS edades
   ===================================================================== */

describe("QuorumNodes · la corroboración también envejece [T-2.82.a]", () => {
  it("evento cargado y viejo: la franja lleva la edad DEL EVENTO", () => {
    // Es el panel que dice qué estaciones corroboraron, o sea el que sostiene
    // si hubo quórum. Presentarlo congelado como vigente afirma una
    // corroboración que no se ha vuelto a comprobar.
    const { container } = render(<QuorumNodes {...props({ eventStaleSince: HORA })} />);
    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(screen.getByText(/DATOS RETENIDOS · 10:41:30 UTC/)).toBeTruthy();
    // …y los offsets siguen visibles bajo la franja.
    expect(screen.getByText("+1.42s")).toBeTruthy();
  });

  it("la rama SIN evento usa la edad DEL INCIDENTE, no la del evento", () => {
    // Aquí el dato no es el evento —no hay— sino el incidente, que dice que no
    // referencia ninguno. Su frescura la calcula la página y baja por
    // `TriageDetail`. Sin ella, «INCIDENTE SIN EVENTO SÍSMICO ASOCIADO» se
    // afirma en presente sobre un incidente que pudo cambiar hace un rato.
    render(
      <QuorumNodes
        {...props({
          eventState: "absent",
          view: quorumView([]),
          eventStaleSince: null,
          incidentStaleSince: HORA,
        })}
      />,
    );
    expect(screen.getByText(/INCIDENTE SIN EVENTO SÍSMICO ASOCIADO/)).toBeTruthy();
    expect(screen.getByText(/así estaba a las 10:41:30 UTC/)).toBeTruthy();
    expect(screen.getByText(/desde entonces no se ha podido confirmar/)).toBeTruthy();
  });

  it("una edad NO contamina a la otra rama", () => {
    // Un solo `staleSince` para las dos ramas sería fechar el evento con el
    // reloj del incidente (o al revés): dos datos distintos, dos edades.
    render(
      <QuorumNodes
        {...props({ eventState: "absent", view: quorumView([]), eventStaleSince: HORA })}
      />,
    );
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
  });

  it("con todo fresco no hay franja en ninguna de las dos ramas", () => {
    const { unmount } = render(<QuorumNodes {...props()} />);
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
    unmount();
    render(<QuorumNodes {...props({ eventState: "absent", view: quorumView([]) })} />);
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
  });
});
