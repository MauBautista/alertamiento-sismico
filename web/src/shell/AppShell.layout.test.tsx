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
 * (`.soc-app > .soc-main { grid-template-rows: auto minmax(0,1fr); row-gap: 0 }`
 * y `.soc-app > .soc-main > *:not(.privacy-banner) { grid-row: 2 }`). Eso no
 * sirve de nada si el marcado deja de satisfacer esos selectores: bastaría con
 * envolver el <main> en un div, o con que el banner perdiera la clase
 * `.privacy-banner`, para que las tres reglas dejaran de aplicar EN SILENCIO y
 * el banner volviera a comerse el alto del mapa (T-1.62, T-2.57 y ahora esto).
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

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  // Estado que SÍ pinta banner: es el caso en el que el bug se manifiesta.
  get.mockResolvedValue({
    data: {
      notice: {
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
      },
      state: "missing",
      consent: null,
      blocks_emergency_actions: false,
    },
    response: { status: 200 },
  });
});

describe("[D3] AppShell — el marcado que la hoja de layout da por supuesto", () => {
  it("el <main> del shell es hijo DIRECTO de `.soc-app`", () => {
    const { container } = renderShell();
    // Con un envoltorio de por medio, `.soc-app > .soc-main` deja de casar y las
    // tres reglas del arreglo desaparecen sin que nada se queje.
    expect(shellMain(container)).not.toBeNull();
  });

  it("el banner es hijo DIRECTO del <main> y lleva la clase que la hoja exenta", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const banner = shellMain(container).querySelector(":scope > .privacy-banner");
    expect(
      banner,
      "el banner dejó de ser hijo directo del <main> o perdió `.privacy-banner`: " +
        "la exención `*:not(.privacy-banner)` lo clavaría en la fila 2, encima de la página",
    ).not.toBeNull();
  });

  it("hay UN solo hijo que no es el banner: nadie más comparte la fila elástica", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const main = shellMain(container);
    const otros = [...main.children].filter((el) => !el.classList.contains("privacy-banner"));
    expect(
      otros.map((el) => el.className),
      "dos hijos no-banner se apilarían EN LA MISMA celda (grid-row: 2), uno encima " +
        "del otro. Si hace falta un tercer hijo en el shell, hay que darle su fila.",
    ).toEqual(["soc-shell"]);
  });

  it("el banner va PRIMERO en el DOM: el orden de lectura no depende de la reja", async () => {
    const { container } = renderShell();
    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");

    const main = shellMain(container);
    // Que se PINTE arriba lo decide la reja; que se LEA primero (lector de
    // pantalla, tabulación) lo decide el DOM. Son dos cosas y las dos importan:
    // un aviso legal que el lector de pantalla anuncia al final de la pantalla
    // no se ha dado por leído.
    expect(main.children[0].classList.contains("privacy-banner")).toBe(true);
  });

  it("cuando el consentimiento está al día el <main> se queda con UN hijo", async () => {
    get.mockResolvedValue({
      data: {
        notice: {
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
        },
        state: "current",
        consent: null,
        blocks_emergency_actions: false,
      },
      response: { status: 200 },
    });
    const { container } = renderShell();
    await screen.findByTestId("pagina");

    const main = shellMain(container);
    // ESTE es el caso normal, y es el que obliga a clavar la página en la fila 2
    // en vez de confiar en la auto-colocación: con un solo hijo, "el primero"
    // y "el que crece" dejan de ser el mismo elemento.
    await waitFor(() => expect(main.children.length).toBe(1));
    expect(main.children[0].className).toBe("soc-shell");
  });
});
