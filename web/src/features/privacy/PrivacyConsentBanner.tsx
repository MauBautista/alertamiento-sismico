import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useNow } from "../../lib/useNow";
import { CONSENT_STALE_MS, usePrivacyConsent } from "./usePrivacyConsent";
import type { ConsentState, ConsentStatus } from "./usePrivacyConsent";

/**
 * T-2.79 · Aviso de privacidad: banner NO BLOQUEANTE.
 *
 * Tres decisiones que se ven en el marcado:
 *
 * 1. **No bloquea.** No es un modal, no atrapa el foco y no tapa la consola. Un
 *    operador con un aviso pendiente sigue viendo el live wall, acusando
 *    incidentes y firmando dictámenes. Es cumplimiento, no un torniquete: en
 *    una emergencia, un trámite delante de la pantalla de operación es un fallo
 *    de seguridad (reglas de oro 1 y 2).
 * 2. **Cuando el consentimiento está al día, DESAPARECE.** Un banner permanente
 *    es ruido, y el ruido permanente se deja de leer — con él, el día que sí
 *    importe tampoco se leerá.
 * 3. **El texto que se acepta es el que se enseña.** Los párrafos vienen del
 *    cuerpo servido, no de un resumen escrito aparte: un resumen que se enseña
 *    pero no se sella deja consentir un texto distinto del que se leyó.
 *
 * Los cuatro estados obligatorios (regla de oro 7) los materializa `StateFrame`:
 * `loading` mientras se pregunta, `error` si la API no contesta, `empty` si esta
 * organización no tiene aviso publicado (404) y `stale` si el dato lleva
 * demasiado sin refrescarse — con `stale` el banner sigue visible pero bajo
 * "DATOS RETENIDOS", porque afirmar "tu consentimiento está al día" con un dato
 * congelado es exactamente la mentira que la regla de oro 7 prohíbe.
 */

/**
 * Los CUATRO estados del consentimiento, exhaustivos por tipo.
 *
 * Eran `Record<string, string>` sin la clave `current` y se leían con
 * `TITULO[state] ?? TITULO.missing`. El resultado, medido: con el consentimiento
 * AL DÍA y el dato viejo —`sereno` es falso, así que el early-return de abajo no
 * dispara— el banner reaparecía diciéndole "ACEPTE EL AVISO DE PRIVACIDAD ·
 * Todavía no ha dado su consentimiento" a un operador que SÍ lo había dado. Y no
 * hace falta nada raro para llegar ahí: el refetch va cada 5 min contra un
 * umbral de 15, y con la red caída el error se suprime a propósito.
 *
 * `Record<ConsentState, …>` sin `??` de respaldo es el arreglo ESTRUCTURAL: el
 * quinto estado que alguien añada mañana al contrato no cae en el texto del que
 * no consintió — no compila. Un `??` sobre un mapa incompleto es exactamente la
 * herramienta que convierte "me falta un caso" en "acuso al usuario en silencio".
 */
const TITULO: Record<ConsentState, string> = {
  missing: "ACEPTE EL AVISO DE PRIVACIDAD",
  current: "CONSENTIMIENTO REGISTRADO · SIN RECONFIRMAR",
  stale: "EL AVISO DE PRIVACIDAD CAMBIÓ",
  withdrawn: "CONSENTIMIENTO RETIRADO",
};

const EXPLICACION: Record<ConsentState, string> = {
  missing: "Todavía no ha dado su consentimiento sobre el tratamiento de sus datos.",
  // Regla de oro 7: "no lo he podido reconfirmar" y "no lo has dado" son cosas
  // distintas y el operador actúa distinto ante cada una. Este texto solo se ve
  // con el dato viejo (al día y fresco, el banner no existe), así que dice las
  // dos cosas: que el consentimiento está dado y que la consola no lo ha podido
  // volver a preguntar.
  current:
    "Su consentimiento está registrado y sigue vigente. Lo que no se ha podido es " +
    "volver a confirmarlo con el servidor: el dato es de la hora que marca arriba. " +
    "No se le está pidiendo nada.",
  stale:
    "Aceptó una versión anterior. Su consentimiento anterior se conserva tal como lo dio; " +
    "este es un texto nuevo y se pide de nuevo.",
  withdrawn: "Usted retiró su consentimiento. Puede volver a darlo cuando quiera.",
};

export interface PrivacyConsentBannerProps {
  /** Inyección para los tests de estado; en producción sale del hook. */
  override?: {
    status: ConsentStatus | null;
    loading: boolean;
    error: string | null;
    dataUpdatedAt: number;
  };
}

export default function PrivacyConsentBanner({ override }: PrivacyConsentBannerProps = {}) {
  const live = usePrivacyConsent();
  const [abierto, setAbierto] = useState(false);
  const now = useNow(30_000);

  const status = override ? override.status : live.status;
  const loading = override ? override.loading : live.loading;
  const error = override ? override.error : live.error;
  const dataUpdatedAt = override ? override.dataUpdatedAt : live.dataUpdatedAt;

  const staleSince =
    !loading && !error && dataUpdatedAt > 0 && now - dataUpdatedAt > CONSENT_STALE_MS
      ? dataUpdatedAt
      : null;

  const notice = status?.notice ?? null;
  const state = status?.state ?? "missing";
  const sereno = !loading && !error && staleSince === null;

  // Al día y sin nada que decir ⇒ el banner no existe. No se renderiza un
  // StateFrame vacío: dejaría un hueco de layout permanente en la consola.
  if (sereno && status !== null && notice !== null && state === "current") {
    return null;
  }

  return (
    <StateFrame
      label="Aviso de privacidad"
      loading={loading}
      error={error}
      // SIN botón de reintento, y es una decisión: este banner vive en el shell,
      // encima de TODAS las pantallas, así que un REINTENTAR suyo competiría con
      // el de la pantalla que hay debajo — dos botones con el mismo nombre en la
      // misma vista, y el operador sin saber cuál de los dos recarga lo que está
      // mirando. Lo detectó `BuildingPage.test.tsx` ("Found multiple elements
      // with the role button and name REINTENTAR") en cuanto se montó aquí.
      // No se pierde recuperación: `usePrivacyConsent` reintenta solo cada
      // CONSENT_REFETCH_MS, y el estado `error` sigue viéndose.
      empty={sereno && (status === null || notice === null)}
      emptyText="SIN AVISO · esta organización no tiene aviso de privacidad publicado."
      staleSince={staleSince}
      className="privacy-banner"
    >
      {notice && (
        <section aria-live="polite" className="privacy-banner__box" data-consent-state={state}>
          <header className="privacy-banner__hd">
            <span className="privacy-banner__tag">CUMPLIMIENTO</span>
            <h2 className="privacy-banner__title">{TITULO[state]}</h2>
            <span className="privacy-banner__version">
              {notice.title} · v{notice.version} ·{" "}
              {notice.source === "tenant" ? "de su organización" : "de la plataforma"}
            </span>
            {notice.provisional && (
              <span className="privacy-banner__provisional" title={notice.provisional_reason}>
                TEXTO PROVISIONAL · pendiente de revisión jurídica
              </span>
            )}
          </header>

          <p className="privacy-banner__why">{EXPLICACION[state]}</p>
          <p className="privacy-banner__nonblocking">
            Esto NO bloquea la operación: puede seguir acusando incidentes y pasar lista aunque no
            lo acepte ahora.
          </p>

          <button
            className="privacy-banner__toggle"
            onClick={() => setAbierto((v) => !v)}
            type="button"
          >
            {abierto ? "OCULTAR EL AVISO" : "LEER EL AVISO COMPLETO"}
          </button>

          {abierto && (
            <div className="privacy-banner__body" data-testid="privacy-body">
              {notice.paragraphs.map((p) => (
                <p className="privacy-banner__p" key={p.slice(0, 48)}>
                  {p}
                </p>
              ))}
              <p className="privacy-banner__digest">
                Sello del texto: {notice.digest.slice(0, 16)}…
              </p>
            </div>
          )}

          <div className="privacy-banner__actions">
            <button
              className="privacy-banner__accept"
              disabled={live.deciding}
              onClick={() => live.decide("accept")}
              type="button"
            >
              {/* Con `current` el consentimiento YA está dado: un botón que diga
                  "ACEPTO ESTE AVISO" al lado de "CONSENTIMIENTO REGISTRADO" se
                  lee como un trámite pendiente, que es la misma mentira que el
                  título acaba de dejar de contar. Aquí sirve de reintento
                  explícito: al registrar, el hook invalida la consulta y el dato
                  vuelve a estar fresco. */}
              {live.deciding
                ? "REGISTRANDO…"
                : state === "current"
                  ? "VOLVER A CONFIRMAR"
                  : "ACEPTO ESTE AVISO"}
            </button>
            {state === "current" || state === "stale" ? (
              <button
                className="privacy-banner__withdraw"
                disabled={live.deciding}
                onClick={() => live.decide("withdraw")}
                type="button"
              >
                RETIRAR CONSENTIMIENTO
              </button>
            ) : null}
          </div>

          {live.decideError && <p className="privacy-banner__err">{live.decideError}</p>}
        </section>
      )}
    </StateFrame>
  );
}
