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
          override={{ status: estado("current"), loading: false, error: null, dataUpdatedAt: Date.now() }}
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
          override={{ status: estado(state), loading: false, error: null, dataUpdatedAt: Date.now() }}
        />,
      ),
    );
    expect(screen.getByText(titulo)).toBeTruthy();
  });

  it("distingue 'cambió el aviso' de 'nunca aceptó': no es el mismo mensaje", () => {
    const { container: a, unmount } = render(
      wrap(
        <PrivacyConsentBanner
          override={{ status: estado("missing"), loading: false, error: null, dataUpdatedAt: Date.now() }}
        />,
      ),
    );
    const textoMissing = a.textContent ?? "";
    unmount();
    const { container: b } = render(
      wrap(
        <PrivacyConsentBanner
          override={{ status: estado("stale"), loading: false, error: null, dataUpdatedAt: Date.now() }}
        />,
      ),
    );
    const textoStale = b.textContent ?? "";
    expect(textoStale).not.toBe(textoMissing);
    expect(textoStale).toContain("Su consentimiento anterior se conserva");
  });

  it("dice que el texto es PROVISIONAL cuando lo es, y no cuando no lo es", () => {
    const { unmount } = render(
      wrap(
        <PrivacyConsentBanner
          override={{ status: estado("missing"), loading: false, error: null, dataUpdatedAt: Date.now() }}
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
          override={{ status: estado("missing"), loading: false, error: null, dataUpdatedAt: Date.now() }}
        />,
      ),
    );
    expect(screen.getByText(/NO bloquea la operación/)).toBeTruthy();
  });

  it("el cuerpo que se lee sale del aviso servido, y va con su sello", async () => {
    render(
      wrap(
        <PrivacyConsentBanner
          override={{ status: estado("missing"), loading: false, error: null, dataUpdatedAt: Date.now() }}
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
