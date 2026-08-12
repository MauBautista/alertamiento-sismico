import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectFourStates } from "../../test-utils/states";
import PrivacyConsentBanner from "./PrivacyConsentBanner";
import type { ConsentState, ConsentStatus, PrivacyNotice } from "./usePrivacyConsent";
import { CONSENT_STALE_MS } from "./usePrivacyConsent";

const post = vi.fn();
const get = vi.fn();

vi.mock("@takab/sdk", () => ({
  client: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));

const AVISO: PrivacyNotice = {
  purpose: "privacy_notice",
  locale: "es-MX",
  version: "0.1.0-provisional",
  title: "Aviso de privacidad — TAKAB Ailert",
  body: "Parrafo uno.\n\nParrafo dos.",
  paragraphs: ["Parrafo uno.", "Parrafo dos."],
  digest: "a".repeat(64),
  source: "repo",
  notice_id: null,
  effective_at: null,
  provisional: true,
  provisional_reason: "revisión legal en estado PROVISIONAL",
};

function estado(state: ConsentState, notice: PrivacyNotice | null = AVISO): ConsentStatus {
  return {
    notice,
    state,
    consent:
      state === "missing"
        ? null
        : {
            consent_id: "c1",
            decision: state === "withdrawn" ? "withdraw" : "accept",
            notice_source: "repo",
            notice_id: null,
            notice_digest: state === "stale" ? "b".repeat(64) : AVISO.digest,
            notice_version: "0.0.9",
            notice_locale: "es-MX",
            via: "web",
            actor_sub: "u1",
            decided_at: "2026-08-01T10:00:00Z",
          },
    blocks_emergency_actions: false,
  };
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue({ data: estado("missing"), response: { status: 200 } });
});

describe("PrivacyConsentBanner", () => {
  it("materializa los cuatro estados obligatorios (regla de oro 7)", () => {
    expectFourStates((s) =>
      wrap(
        <PrivacyConsentBanner
          override={{
            status: s === "empty" ? { ...estado("missing"), notice: null } : estado("missing"),
            loading: s === "loading",
            error: s === "error" ? "GET /privacy/consent falló (500)" : null,
            // `stale` = el DATO lleva demasiado sin refrescarse. Se distingue
            // del `stale` del consentimiento a propósito: uno habla de la
            // frescura del dato y el otro del texto que se aceptó.
            dataUpdatedAt: s === "stale" ? Date.now() - CONSENT_STALE_MS - 1000 : Date.now(),
          }}
        />,
      ),
    );
  });

  it("DESAPARECE cuando el consentimiento está al día", () => {
    const { container } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("current"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    // Un banner permanente es ruido, y el ruido permanente se deja de leer.
    expect(container.querySelector(".privacy-banner__box")).toBeNull();
    expect(container.textContent).toBe("");
  });

  it.each([
    ["missing", "ACEPTE EL AVISO DE PRIVACIDAD"],
    ["stale", "EL AVISO DE PRIVACIDAD CAMBIÓ"],
    ["withdrawn", "CONSENTIMIENTO RETIRADO"],
  ] as const)("con estado %s aparece y dice %s", (state, titulo) => {
    render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado(state),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    expect(screen.getByText(titulo)).toBeTruthy();
  });

  it("distingue 'cambió el aviso' de 'nunca aceptó': no es el mismo mensaje", () => {
    const { container: a, unmount } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("missing"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    const textoMissing = a.textContent ?? "";
    unmount();
    const { container: b } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("stale"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    const textoStale = b.textContent ?? "";
    expect(textoStale).not.toBe(textoMissing);
    expect(textoStale).toContain("Su consentimiento anterior se conserva");
  });

  /**
   * [D1] El banner ACUSABA de no haber consentido a quien SÍ consintió.
   *
   * `TITULO`/`EXPLICACION` no tenían clave `current`, y el early-return que
   * esconde el banner exige `sereno` — que a su vez exige `staleSince === null`.
   * Con `state === "current"` y el dato viejo el banner reaparecía y caía a
   * `?? TITULO.missing`: "ACEPTE EL AVISO DE PRIVACIDAD" y "Todavía no ha dado
   * su consentimiento" sobre un operador que lo había dado.
   *
   * No es teórico: el refetch va cada 5 min contra un umbral de 15 (`usePrivacy
   * Consent.ts`), y con la red caída el error se suprime a propósito para no
   * tapar un consentimiento que sigue siendo cierto. Basta con que la API no
   * conteste tres veces seguidas.
   *
   * Regla de oro 7 al revés de como se suele leer: el dato congelado no se
   * puede pintar como live, pero tampoco se puede pintar como AUSENTE. "No lo
   * he podido reconfirmar" y "no lo has dado" son cosas distintas y el operador
   * actúa distinto ante cada una.
   */
  it("[D1] consintió y el dato está viejo: NO se le acusa de no haber consentido", () => {
    const { container } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("current"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now() - CONSENT_STALE_MS - 1000,
          }}
        />,
      ),
    );

    const texto = container.textContent ?? "";
    // El banner SÍ aparece: esconderlo sería afirmar frescura que no hay.
    expect(container.querySelector(".privacy-banner__box")).not.toBeNull();
    expect(texto).toContain("DATOS RETENIDOS");
    // Pero lo que dice no puede ser el texto del que nunca consintió.
    expect(texto, "acusa de no haber consentido a quien consintió").not.toContain(
      "ACEPTE EL AVISO DE PRIVACIDAD",
    );
    expect(texto, "acusa de no haber consentido a quien consintió").not.toContain(
      "Todavía no ha dado su consentimiento",
    );
  });

  it("[D1] `current` sin reconfirmar dice algo DISTINTO de `missing`, no lo mismo", () => {
    // La red no es "que no diga la palabra prohibida": es que los dos estados
    // se distingan. Si mañana alguien cambia la redacción de `missing`, la
    // negación de arriba se volvería verde vacía; esto no.
    const { container: viejo, unmount } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("current"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now() - CONSENT_STALE_MS - 1000,
          }}
        />,
      ),
    );
    const textoCurrent = (viejo.querySelector(".privacy-banner__box")?.textContent ?? "").trim();
    unmount();

    const { container: nunca } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("missing"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    const textoMissing = (nunca.querySelector(".privacy-banner__box")?.textContent ?? "").trim();

    expect(textoCurrent, "el banner de `current` no se renderizó").not.toBe("");
    expect(textoCurrent).not.toBe(textoMissing);
  });

  /**
   * [T-2.79.d] LA FRANJA MUDA — el hueco que dejó abierto T-2.79.
   *
   * Sin aviso publicado (`notice === null`) Y con el dato viejo, el banner
   * pintaba `DATOS RETENIDOS · hh:mm UTC` y debajo NADA: una banda muda en la
   * consola de un SOC. No mentía; simplemente no decía nada. La causa era una
   * precedencia LOCAL: `empty` exigía `sereno`, o sea que el componente apagaba
   * su propio `empty` porque el dato estaba viejo, y con ello se comía el único
   * texto que ese estado tenía.
   *
   * Ahora `empty` se declara tal cual es y la tabla decide: gana `stale`, y el
   * marco FECHA la ausencia en vez de callarla.
   */
  it("[T-2.79.d] sin aviso Y con el dato viejo: la franja deja de estar muda", () => {
    const { container } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: { ...estado("missing"), notice: null },
            loading: false,
            error: null,
            dataUpdatedAt: Date.now() - CONSENT_STALE_MS - 1000,
          }}
        />,
      ),
    );

    const marco = container.querySelector("[data-state]");
    expect(marco?.getAttribute("data-state")).toBe("stale");

    const banda = container.querySelector(".soc-stateframe__stale")?.textContent ?? "";
    expect(banda).toContain("DATOS RETENIDOS");

    // LO QUE ESTA FICHA CIERRA: debajo de la banda hay texto.
    const salvoLaBanda = (container.textContent ?? "").replace(banda, "").trim();
    expect(salvoLaBanda, "la franja sigue muda: banda de edad y debajo nada").not.toBe("");
    expect(salvoLaBanda).toContain("no tiene aviso de privacidad publicado");
    // Y la ausencia va FECHADA, no afirmada en presente: lo que se puede
    // verificar es lo que se vio a esa hora, no lo que hay ahora.
    expect(salvoLaBanda).toContain("desde entonces no se ha podido confirmar");
  });

  it("[T-2.79.d] el `empty` del banner ya no depende de que el dato esté fresco", () => {
    // La misma ausencia, con el dato FRESCO, sigue siendo el `empty` de toda la
    // vida. Sin esta mitad, el arreglo de arriba podría haber sido «encender
    // empty siempre» y romper el estado vacío normal.
    const { container } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: { ...estado("missing"), notice: null },
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    expect(container.querySelector("[data-state]")?.getAttribute("data-state")).toBe("empty");
    expect(container.textContent ?? "").toContain("no tiene aviso de privacidad publicado");
  });

  it("[D1] un 404 del endpoint NO se cuenta como “esta organización no tiene aviso”", async () => {
    // `GET /privacy/consent` responde 200 con `notice: null` cuando no hay aviso
    // (api/src/takab_api/routers/privacy.py). Un 404 solo puede venir de la
    // infraestructura —prefijo mal montado, gateway, proxy— y traducirlo a una
    // frase de negocio le cuenta al operador una historia falsa sobre su propia
    // organización. El estado `empty` sale del `notice: null`, no de un 404.
    get.mockResolvedValue({ data: undefined, response: { status: 404 } });
    render(wrap(<PrivacyConsentBanner />));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent ?? "").not.toContain("no tiene aviso de privacidad publicado");
    expect(aviso.textContent ?? "").toContain("404");
  });

  it("dice que el texto es PROVISIONAL cuando lo es, y no cuando no lo es", () => {
    const { unmount } = render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("missing"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    expect(screen.getByText(/TEXTO PROVISIONAL/)).toBeTruthy();
    unmount();

    const firme = estado("missing");
    firme.notice = { ...AVISO, provisional: false, provisional_reason: "" };
    render(
      wrap(
        <PrivacyConsentBanner
          override={{ status: firme, loading: false, error: null, dataUpdatedAt: Date.now() }}
        />,
      ),
    );
    expect(screen.queryByText(/TEXTO PROVISIONAL/)).toBeNull();
  });

  it("declara que NO bloquea la operación", () => {
    render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("missing"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    expect(screen.getByText(/NO bloquea la operación/)).toBeTruthy();
  });

  it("el cuerpo que se lee sale del aviso servido, y va con su sello", async () => {
    render(
      wrap(
        <PrivacyConsentBanner
          override={{
            status: estado("missing"),
            loading: false,
            error: null,
            dataUpdatedAt: Date.now(),
          }}
        />,
      ),
    );
    expect(screen.queryByTestId("privacy-body")).toBeNull();
    fireEvent.click(screen.getByText("LEER EL AVISO COMPLETO"));
    const cuerpo = screen.getByTestId("privacy-body");
    // Los párrafos son los SERVIDOS, no un resumen escrito en el front.
    expect(cuerpo.textContent).toContain("Parrafo uno.");
    expect(cuerpo.textContent).toContain("Parrafo dos.");
    expect(cuerpo.textContent).toContain(AVISO.digest.slice(0, 16));
  });

  it("aceptar manda el DIGEST del aviso en pantalla, no solo la decisión", async () => {
    post.mockResolvedValue({ data: { consent_id: "c9" }, response: { status: 201 } });
    render(wrap(<PrivacyConsentBanner />));

    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");
    fireEvent.click(screen.getByText("ACEPTO ESTE AVISO"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const enviado = post.mock.calls[0][0] as { url: string; body: Record<string, unknown> };
    expect(enviado.url).toBe("/privacy/consent");
    // Sin el digest, el servidor tendría que adivinar qué texto se aceptó.
    expect(enviado.body.digest).toBe(AVISO.digest);
    expect(enviado.body.decision).toBe("accept");
    expect(enviado.body.via).toBe("web");
  });

  it("un 409 se explica: el aviso cambió mientras estaba en pantalla", async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 409 } });
    render(wrap(<PrivacyConsentBanner />));

    await screen.findByText("ACEPTE EL AVISO DE PRIVACIDAD");
    fireEvent.click(screen.getByText("ACEPTO ESTE AVISO"));

    expect(await screen.findByText(/el aviso cambió mientras estaba en pantalla/)).toBeTruthy();
  });
});
