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
      // [T-2.79.d] `empty` se DECLARA tal cual es; ya no lleva `sereno &&`.
      //
      // Ese `sereno` era una precedencia LOCAL: apagaba el `empty` porque el
      // dato estuviera viejo, y el resultado medido era la franja muda —
      // `DATOS RETENIDOS · hh:mm UTC` y debajo NADA, porque sin aviso los hijos
      // tampoco pintan. Quien decide entre `empty` y `stale` es la tabla
      // `STATE_PRECEDENCE`, no cada componente; y decidió que gana `stale`, con
      // la ausencia FECHADA debajo. Lo vigila `statePrecedenceCensus.test.ts`.
      empty={!loading && !error && (status === null || notice === null)}
      emptyText="SIN AVISO · esta organización no tiene aviso de privacidad publicado."
      staleSince={staleSince}
      className="privacy-banner"
    >
      {notice && (
        <section aria-live="polite" className="privacy-banner__box" data-consent-state={state}>
          {/* [T-6.11] UNA LÍNEA. Este bloque medía 164 px en las seis pantallas
              hasta que alguien aceptara —dos párrafos, una cabecera de tres
              piezas y dos filas de botones— y esos 164 px salían ENTEROS del
              alto del mapa: medido a 1280×800, el escenario pasaba de 445 px a
              269, por debajo de su piso. Es lo primero que ve un cliente en una
              demo, y lo que veía era un trámite tapando la operación.

              Lo que se queda en la línea es lo que hay que poder leer sin
              pulsar nada: en qué estado está el consentimiento (el título ya lo
              distingue), qué aviso y de quién, y que esto NO bloquea. La
              explicación larga y el texto del aviso se leen al desplegar, que
              es donde ya vivía el cuerpo. */}
          <span className="privacy-banner__tag">CUMPLIMIENTO</span>
          <h2 className="privacy-banner__title">{TITULO[state]}</h2>
          {/* El que cede cuando la ventana estrecha: se recorta con puntos
              suspensivos, y el `title` conserva lo que se recortó — la versión
              es lo que identifica QUÉ aviso se está aceptando. */}
          <span
            className="privacy-banner__version"
            title={`${notice.title} · v${notice.version} · ${
              notice.source === "tenant" ? "de su organización" : "de la plataforma"
            }`}
          >
            {notice.title} · v{notice.version} ·{" "}
            {notice.source === "tenant" ? "de su organización" : "de la plataforma"}
          </span>
          {notice.provisional && (
            <span className="privacy-banner__provisional" title={notice.provisional_reason}>
              TEXTO PROVISIONAL
            </span>
          )}
          {/* La promesa se queda a la vista, corta: que el aviso no sea un
              torniquete es justo lo que un operador necesita saber sin abrir
              nada (reglas de oro 1 y 2). */}
          <span className="privacy-banner__nonblocking">NO bloquea la operación</span>

          <div className="privacy-banner__actions">
            <button
              className="privacy-banner__toggle"
              onClick={() => setAbierto((v) => !v)}
              type="button"
            >
              {abierto ? "OCULTAR EL AVISO" : "LEER EL AVISO COMPLETO"}
            </button>
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

          {abierto && (
            <div className="privacy-banner__body" data-testid="privacy-body">
              {/* La explicación del estado ENCABEZA el cuerpo: quien despliega
                  lo primero que pregunta es por qué le están enseñando esto. */}
              <p className="privacy-banner__why">{EXPLICACION[state]}</p>
              <p className="privacy-banner__p">
                Esto NO bloquea la operación: puede seguir acusando incidentes y pasar lista aunque
                no lo acepte ahora.
              </p>
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
        </section>
      )}
    </StateFrame>
  );
}
