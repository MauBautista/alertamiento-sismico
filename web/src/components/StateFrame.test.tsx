import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { expectFourStates } from "../test-utils/states";
import StateFrame, { STATE_PRECEDENCE, resolveState, staleEmptyText } from "./StateFrame";
import type { FrameState, StateFrameProps } from "./StateFrame";

function frame(over: Partial<Parameters<typeof StateFrame>[0]> = {}) {
  return (
    <StateFrame label="INCIDENTES" loading={false} {...over}>
      <span>contenido-vivo</span>
    </StateFrame>
  );
}

describe("StateFrame", () => {
  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    expectFourStates((state) =>
      frame({
        loading: state === "loading",
        error: state === "error" ? "falló la carga" : null,
        empty: state === "empty",
        staleSince: state === "stale" ? Date.UTC(2026, 6, 8, 10, 41, 30) : null,
      }),
    );
  });

  it("loading oculta el contenido y anuncia el panel", () => {
    render(frame({ loading: true }));
    expect(screen.queryByText("contenido-vivo")).toBeNull();
    expect(screen.getByText(/CARGANDO · INCIDENTES/)).toBeInTheDocument();
  });

  it("error muestra el mensaje con role=alert y reintento", () => {
    const onRetry = vi.fn();
    render(frame({ error: "GET /incidents falló (503)", onRetry }));
    expect(screen.getByRole("alert")).toHaveTextContent("GET /incidents falló (503)");
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("empty usa el texto propio si se da", () => {
    render(frame({ empty: true, emptyText: "SIN INCIDENTES ABIERTOS" }));
    expect(screen.getByText("SIN INCIDENTES ABIERTOS")).toBeInTheDocument();
  });

  it("stale MUESTRA el contenido pero bajo el banner DATOS RETENIDOS con HH:MM:SS", () => {
    render(frame({ staleSince: Date.UTC(2026, 6, 8, 10, 41, 30) }));
    expect(screen.getByText("contenido-vivo")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("DATOS RETENIDOS · 10:41:30 UTC");
  });

  it("fresco: contenido sin banner, data-state=ready", () => {
    const { container } = render(frame());
    expect(screen.getByText("contenido-vivo")).toBeInTheDocument();
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
    expect(container.querySelector('[data-state="ready"]')).not.toBeNull();
  });

  it("la precedencia es loading > error > stale > empty", () => {
    const { container } = render(
      frame({
        loading: true,
        error: "x",
        empty: true,
        staleSince: 0,
      }),
    );
    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
  });
});

/* =====================================================================
   T-2.79.d · LA DECISIÓN: entre `empty` y `stale` gana `stale`
   ===================================================================== */

const HORA = Date.UTC(2026, 6, 8, 10, 41, 30);

/**
 * ACTIVADOR POR ESTADO — exhaustivo POR TIPO sobre `STATE_PRECEDENCE`.
 *
 * Éste es el mecanismo que obliga a la combinación número 17. El día que la
 * tabla gane un quinto estado, este `Record` deja de compilar hasta que alguien
 * diga CÓMO se enciende — y en cuanto lo diga, el barrido de combinaciones de
 * abajo pasa de 16 a 32 y exige texto en las 16 nuevas. Sin `??` de respaldo y
 * sin `Partial`: un mapa incompleto con un `??` detrás es exactamente la
 * herramienta que convierte «me falta un caso» en «pinto la pantalla en blanco»
 * (misma lección que `TITULO` en `PrivacyConsentBanner`).
 */
const ACTIVAR: Record<(typeof STATE_PRECEDENCE)[number], (p: StateFrameProps) => StateFrameProps> =
  {
    loading: (p) => ({ ...p, loading: true }),
    error: (p) => ({ ...p, error: "GET /incidents falló (503)" }),
    stale: (p) => ({ ...p, staleSince: HORA }),
    empty: (p) => ({ ...p, empty: true }),
  };

const BASE: StateFrameProps = {
  label: "INCIDENTES",
  loading: false,
  error: null,
  empty: false,
  emptyText: "SIN INCIDENTES ABIERTOS",
  staleSince: null,
  // NULO A PROPÓSITO: el marco tiene que hablar POR SÍ MISMO. Si el texto lo
  // pusieran los hijos, la prueba mediría al componente de ejemplo y no al
  // contrato — y justo en `stale`+`empty` los hijos son lo que NO hay.
  children: null,
};

/** Las 2^n combinaciones de banderas, DERIVADAS de la tabla. */
function combinaciones(): (typeof STATE_PRECEDENCE)[number][][] {
  const n = STATE_PRECEDENCE.length;
  const out: (typeof STATE_PRECEDENCE)[number][][] = [];
  for (let mask = 0; mask < 2 ** n; mask += 1) {
    out.push(STATE_PRECEDENCE.filter((_, i) => (mask >> i) % 2 === 1));
  }
  return out;
}

function pintar(combo: readonly (typeof STATE_PRECEDENCE)[number][]) {
  const props = combo.reduce<StateFrameProps>((p, estado) => ACTIVAR[estado](p), BASE);
  const { container, unmount } = render(<StateFrame {...props} />);
  const texto = (container.textContent ?? "").trim();
  // El banner de edad habla del DATO VIEJO, no del dato. Un marco que sólo
  // dice "DATOS RETENIDOS" es la franja muda de la ficha: se ve una banda y
  // debajo no hay nada. Se descuenta para poder exigir lo segundo aparte.
  const banda = container.querySelector(".soc-stateframe__stale")?.textContent ?? "";
  const salvoLaEdad = texto.replace(banda.trim(), "").trim();
  const marca = container.querySelector("[data-state]")?.getAttribute("data-state") ?? null;
  unmount();
  return { texto, salvoLaEdad, marca };
}

const nombre = (c: readonly string[]) => (c.length === 0 ? "(ninguna bandera)" : c.join("+"));

describe("StateFrame · el espacio de combinaciones, derivado del contrato", () => {
  it("el barrido es el de la tabla: 2^n combinaciones, ni una escrita a mano", () => {
    // No-vacuidad: si la tabla se vacía o el barrido se rompe, lo de abajo
    // pasaría en verde sin mirar nada.
    expect(combinaciones().length).toBe(2 ** STATE_PRECEDENCE.length);
    expect(combinaciones().length).toBeGreaterThan(8);
    expect(Object.keys(ACTIVAR).sort()).toEqual([...STATE_PRECEDENCE].sort());
  });

  it("NINGUNA combinación deja el marco sin una palabra (T-2.79.d · criterio 2)", () => {
    // Se recorre el espacio ENTERO —no una lista de componentes— con los hijos
    // vacíos, porque en `stale`+`empty` los hijos son precisamente lo que no
    // hay. Un marco que no diga nada ahí es la banda muda de la ficha.
    const mudas = combinaciones()
      .filter((c) => pintar(c).texto === "")
      .map(nombre);
    expect(
      mudas,
      "COMBINACIONES QUE PINTAN UN MARCO SIN UNA SOLA PALABRA. Si añadiste un " +
        `estado a STATE_PRECEDENCE, dale su rama de render:\n${mudas.join("\n")}`,
    ).toEqual(["(ninguna bandera)"]);
  });

  it("y NINGUNA se queda en la franja de edad a secas — la franja muda de T-2.79.d", () => {
    // ÉSTE es el defecto literal de la ficha: `DATOS RETENIDOS · hh:mm UTC` y
    // debajo nada. La franja habla del DATO VIEJO; no habla del dato. Se
    // descuenta y se exige que quede algo dicho.
    //
    // Las DOS excepciones son la misma: el dueño AFIRMÓ `empty === false`, o
    // sea que hay dato y el texto es de los hijos. No es una escapatoria — que
    // esa afirmación sea explícita lo garantiza el censo `C-3` de
    // `serverDataCensus.test.ts` (todo `<StateFrame>` cablea sus cuatro
    // entradas), y que no se pueda apagar `empty` porque el dato esté viejo lo
    // garantiza `statePrecedenceCensus.test.ts`. Sin esas dos guardas, esta
    // lista sería una puerta abierta en vez de una constatación.
    const soloLaEdad = combinaciones()
      .filter((c) => pintar(c).salvoLaEdad === "")
      .map(nombre);
    expect(
      soloLaEdad,
      "COMBINACIONES QUE SÓLO PINTAN LA FRANJA DE EDAD. Con `empty` encendido, el " +
        `marco tiene que FECHAR la ausencia en vez de callarla:\n${soloLaEdad.join("\n")}`,
    ).toEqual(["(ninguna bandera)", "stale"]);
  });

  it("la única muda es `ready`, y ahí el texto es del dueño a propósito", () => {
    // `ready` = el dueño AFIRMA que hay dato (`empty === false`) y que está
    // fresco. El marco no puede inventarse su contenido; lo que sí garantiza
    // es que ese estado no se alcanza con ninguna bandera encendida.
    expect(resolveState({ loading: false, error: null, empty: false, stale: false })).toBe("ready");
    const { container } = render(<StateFrame {...BASE}>hay-dato</StateFrame>);
    expect((container.textContent ?? "").trim()).toBe("hay-dato");
  });

  it("cada combinación la gana el PRIMER estado de la tabla que esté encendido", () => {
    for (const combo of combinaciones()) {
      const esperado: FrameState = STATE_PRECEDENCE.find((s) => combo.includes(s)) ?? "ready";
      expect(pintar(combo).marca, `combinación ${combo.join("+") || "(ninguna)"}`).toBe(esperado);
    }
  });
});

describe("StateFrame · `empty` + `stale` a la vez: gana `stale` (T-2.79.d)", () => {
  it("marca el estado como `stale`, no como `empty`", () => {
    const { container } = render(frame({ empty: true, staleSince: HORA }));
    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(container.querySelector('[data-state="empty"]')).toBeNull();
  });

  it("NO afirma la ausencia en presente: la fecha con la hora en que se supo", () => {
    // `empty` afirma un hecho sobre EL MUNDO («no hay»); `stale`, un hecho sobre
    // NUESTRO CONOCIMIENTO («no lo sé desde las hh:mm»). Con los dos ciertos,
    // sólo el segundo se puede verificar.
    const { container } = render(
      frame({ empty: true, emptyText: "SIN INCIDENTES ABIERTOS", staleSince: HORA }),
    );
    const texto = container.textContent ?? "";
    expect(texto).toContain("DATOS RETENIDOS · 10:41:30 UTC");
    // El «no hay» no se pierde: se fecha.
    expect(texto).toContain("SIN INCIDENTES ABIERTOS");
    expect(texto).toContain("10:41:30 UTC");
    expect(texto).toContain("desde entonces no se ha podido confirmar");
  });

  it("el texto fechado sale de una función del contrato, no de cada componente", () => {
    // Para que ningún panel pueda escribir su propia versión del deslinde.
    expect(staleEmptyText("INCIDENTES", "SIN INCIDENTES ABIERTOS", HORA)).toContain(
      "SIN INCIDENTES ABIERTOS",
    );
    expect(staleEmptyText("INCIDENTES", undefined, HORA)).toContain("SIN DATOS · INCIDENTES");
  });

  it("sin `empty`, `stale` sigue enseñando el dato bajo el banner", () => {
    // La conducta de siempre no cambia: el dato viejo se ve, pero rotulado.
    const { container } = render(frame({ staleSince: HORA }));
    expect(screen.getByText("contenido-vivo")).toBeInTheDocument();
    expect(container.textContent ?? "").not.toContain("desde entonces no se ha podido confirmar");
  });
});

describe("StateFrame className (T-1.50)", () => {
  it("aplica la clase de layout del dueño en ready y stale", () => {
    const ready = render(frame({ className: "soc-wall" }));
    expect(ready.container.querySelector(".soc-stateframe.soc-wall")).not.toBeNull();
    ready.unmount();

    const stale = render(frame({ className: "soc-wall", staleSince: 1_700_000_000_000 }));
    expect(stale.container.querySelector('.soc-wall[data-state="stale"]')).not.toBeNull();
    stale.unmount();
  });

  it("también en los estados de status (layout estable del grid dueño)", () => {
    const loading = render(frame({ className: "soc-wall", loading: true }));
    expect(loading.container.querySelector('.soc-wall[data-state="loading"]')).not.toBeNull();
    loading.unmount();

    const empty = render(frame({ className: "soc-wall", empty: true }));
    expect(empty.container.querySelector('.soc-wall[data-state="empty"]')).not.toBeNull();
    empty.unmount();
  });
});
