import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppShell from "./AppShell";

/**
 * [D3] La MITAD DOM de la invariante de layout del shell.
 *
 * `src/styles/layoutInvariants.test.ts` afirma lo que dice la HOJA
 * (`.soc-app > .soc-main { grid-template-rows: auto auto minmax(0,1fr); row-gap: 0 }`,
 * `.soc-app > .soc-main > .soc-scene { grid-row: 1 }` y
 * `.soc-app > .soc-main > *:not(.privacy-banner):not(.soc-scene) { grid-row: 3 }`).
 * Eso no sirve de nada si el marcado deja de satisfacer esos selectores:
 * bastaría con envolver el <main> en un div, o con que el banner perdiera la
 * clase `.privacy-banner`, o la franja la clase `.soc-scene`, para que las
 * reglas dejaran de aplicar EN SILENCIO y un hermano volviera a comerse el alto
 * del mapa (T-1.62, T-2.57 y ahora esto).
 *
 * [T-6.01] Llegó el tercer hijo que este archivo anunciaba: la FRANJA DE
 * ESCENA. Va PRIMERA (una alerta se lee antes que un aviso legal) y en escena
 * NORMAL no tiene hijos visibles.
 *
 * jsdom no hace layout: aquí no se mide un solo píxel. Lo que se afirma es la
 * FORMA del árbol, que es exactamente lo que la hoja da por supuesto. La medida
 * de verdad la toma `e2e/layout.spec.ts` en un navegador.
 */

const get = vi.fn();
const post = vi.fn();

vi.mock("@takab/sdk", () => ({
  client: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

// El socket live y la topbar no pintan nada de este contrato y arrastran medio
// árbol de sesión: se sustituyen por lo mínimo que conserva la FORMA (la topbar
// sigue siendo hermana del <main>, que es lo que hace de `.soc-main` el segundo
// hijo del grid de `.soc-app`).
vi.mock("../live/LiveSocketProvider", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("./Topbar", () => ({
  default: () => <header className="soc-topbar" />,
}));
// [T-6.01] Las cuatro fuentes de la franja, inertes: aquí se mide la FORMA del
// shell en escena NORMAL, no la escena (eso es `SceneStrip.test.tsx`). La franja
// real se monta, con su clase real: es la clase que la hoja da por supuesta.
vi.mock("../features/console/useLiveIncidents", () => ({
  useLiveIncidents: () => ({
    incidents: [],
    loading: false,
    error: null,
    // Fresco: con una edad vieja la línea de alerta pintaría la ausencia FECHADA
    // (T-2.79.d), que sí es un hijo visible — y este test mide la escena NORMAL.
    dataUpdatedAt: Date.now(),
    liveStatus: "ready",
    lastFrameAt: null,
    degraded: [],
    refetch: () => undefined,
  }),
}));
vi.mock("../features/console/useMapState", () => ({
  useMapState: () => ({
    sites: [],
    epicenters: [],
    loading: false,
    error: null,
    dataUpdatedAt: 1,
    refetch: () => undefined,
  }),
}));
vi.mock("../features/console/useActiveDrill", () => ({
  useActiveDrill: () => ({
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: 1,
    refetch: () => undefined,
    start: () => undefined,
    stop: () => undefined,
    cancel: () => undefined,
    pending: false,
    error: null,
  }),
}));
vi.mock("../features/console/useMaintenanceWindows", () => ({
  useMaintenanceWindows: () => ({
    items: [],
    loading: false,
    readError: null,
    forbidden: false,
    updatedAt: 1,
    refetch: () => undefined,
    close: () => undefined,
    open: () => undefined,
    pending: false,
    openPending: false,
    error: null,
    openError: null,
  }),
}));
vi.mock("../features/console/useDemoMode", () => ({
  useDemoMode: () => ({
    demo: { active: false },
    loading: false,
    readError: false,
    updatedAt: 1,
    refetch: () => undefined,
    encender: () => undefined,
    apagar: () => undefined,
    pending: false,
  }),
}));

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/console"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route
              path="/console"
              element={<section className="soc-shell" data-testid="pagina" />}
            />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** El <main> del SHELL, el que la hoja alcanza con `.soc-app > .soc-main`. */
function shellMain(container: HTMLElement): HTMLElement {
  const main = container.querySelector<HTMLElement>(".soc-app > main.soc-main");
  if (main === null) {
    throw new Error(
      "no hay `.soc-app > main.soc-main`: la regla de layout de privacy.css no alcanza a nada",
    );
  }
  return main;
}

const NOTICE = {
  purpose: "privacy_notice",
  locale: "es-MX",
  version: "0.1.0",
  title: "Aviso",
  body: "Uno.",
  paragraphs: ["Uno."],
  digest: "a".repeat(64),
  source: "repo",
  notice_id: null,
  effective_at: null,
  provisional: false,
  provisional_reason: "",
};

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  // Estado que SÍ pinta banner: es el caso en el que el bug se manifiesta.
  get.mockResolvedValue({
    data: { notice: NOTICE, state: "missing", consent: null, blocks_emergency_actions: false },
    response: { status: 200 },
  });
});

describe("[D3] AppShell — el marcado que la hoja de layout da por supuesto", () => {
  it("el <main> del shell es hijo DIRECTO de `.soc-app`", () => {
    const { container } = renderShell();
    // Con un envoltorio de por medio, `.soc-app > .soc-main` deja de casar y las
    // reglas del arreglo desaparecen sin que nada se queje.
    expect(shellMain(container)).not.toBeNull();
  });

  it("la franja de escena es hija DIRECTA del <main> y lleva la clase que la hoja clava a la fila 1", () => {
    const { container } = renderShell();
    const scene = shellMain(container).querySelector(":scope > .soc-scene");
    expect(
      scene,
      "la franja dejó de ser hija directa del <main> o perdió `.soc-scene`: caería a la " +
        "fila 3, encima de la página, o la página a la fila `auto`",
    ).not.toBeNull();
  });

  it("el banner es hijo DIRECTO del <main> y lleva la clase que la hoja exenta", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const banner = shellMain(container).querySelector(":scope > .privacy-banner");
    expect(
      banner,
      "el banner dejó de ser hijo directo del <main> o perdió `.privacy-banner`: " +
        "la exención `*:not(.privacy-banner)` lo clavaría en la fila 3, encima de la página",
    ).not.toBeNull();
  });

  it("hay UN solo hijo que no es ni la franja ni el banner: nadie más comparte la fila elástica", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const main = shellMain(container);
    const otros = [...main.children].filter(
      (el) => !el.classList.contains("privacy-banner") && !el.classList.contains("soc-scene"),
    );
    expect(
      otros.map((el) => el.className),
      "dos hijos sin fila propia se apilarían EN LA MISMA celda (grid-row: 3), uno encima " +
        "del otro. Si hace falta un cuarto hijo en el shell, hay que darle su fila.",
    ).toEqual(["soc-shell"]);
  });

  it("la escena va PRIMERA en el DOM y el banner después: una alerta se lee antes que un aviso legal", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const main = shellMain(container);
    // Que se PINTE arriba lo decide la reja; que se LEA primero (lector de
    // pantalla, tabulación) lo decide el DOM. Son dos cosas y las dos importan.
    expect(main.children[0].classList.contains("soc-scene")).toBe(true);
    expect(main.children[1].classList.contains("privacy-banner")).toBe(true);
  });

  it("en escena NORMAL la franja no tiene un solo hijo visible: no puede robar alto", () => {
    const { container } = renderShell();
    const scene = shellMain(container).querySelector(":scope > .soc-scene");
    const visibles = [...(scene?.children ?? [])].filter((el) => !el.hasAttribute("hidden"));
    expect(visibles).toEqual([]);
  });

  it("cuando el consentimiento está al día el <main> se queda con la franja y la página", async () => {
    get.mockResolvedValue({
      data: { notice: NOTICE, state: "current", consent: null, blocks_emergency_actions: false },
      response: { status: 200 },
    });
    const { container } = renderShell();
    await screen.findByTestId("pagina");

    const main = shellMain(container);
    // ESTE es el caso normal, y es el que obliga a clavar la página en la fila 3
    // en vez de confiar en la auto-colocación: sin banner, "el segundo hijo" y
    // "el que crece" dejan de ser el mismo elemento.
    await waitFor(() => expect(main.children.length).toBe(2));
    expect([...main.children].map((el) => el.className)).toEqual(["soc-scene", "soc-shell"]);
  });
});
