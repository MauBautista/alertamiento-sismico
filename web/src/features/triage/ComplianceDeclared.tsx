// [T-2.82.b] Import SOLO de tipos, y a propósito. Este fichero lo alcanza
// `IncidentTimeline`, y los tests de `useFleet`/`useSiteRelays` sustituyen
// `@takab/sdk` entero con `vi.mock` sin `importOriginal`: un import de VALOR
// aquí los deja en «0 test» sin una sola marca de fallo. Un `import type` se
// borra al compilar, así que no crea arista en tiempo de ejecución.
import type { ComplianceDocOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import type { ForensicsState } from "./useForensics";

/*
 * [T-2.82.b] Aquí vivían `DeclaredClaim` y `DeclaredDoc`, escritos a mano
 * «hasta que el SDK se regenere». El SDK se regeneró: `ComplianceDocOut` y
 * `ComplianceClaimOut` los publican con sus campos requeridos, y el tipo local
 * desapareció en vez de quedarse de segunda verdad sobre el mismo cable.
 *
 * DISCREPANCIA REAL que apareció al sustituirlo, y no se ha tapado: el contrato
 * declara `ForensicsOut.compliance` **requerido** —el propio docstring generado
 * dice que esta rama «NO DISPONIBLE» quedó «inalcanzable y a la vez formalmente
 * justificada»—, mientras que este componente sigue tratando su ausencia. Se
 * conserva el tratamiento, sin `!` y sin cast: un servidor anterior a T-2.82
 * responde sin el bloque, y pintar entonces «SIN MARCO DECLARADO» sería AFIRMAR
 * sobre el cliente algo que nadie comprobó (regla de oro 7) — exactamente el
 * error que este componente existe para no cometer. El tipo dice lo que dice el
 * contrato; el código se defiende del despliegue viejo.
 */

/**
 * [T-2.82] Marco normativo DECLARADO por el cliente, en la pantalla donde se FIRMA.
 *
 * Va entre el botón que genera el PDF y el bloque de firma a propósito: son los dos
 * actos que este apartado tiene que cualificar. Quien firma un dictamen se lleva
 * detrás las afirmaciones normativas del cliente; tiene derecho a leer, en el mismo
 * golpe de vista, que TAKAB no las verificó. El documento que sale por la impresora
 * dice exactamente lo mismo, porque las dos superficies imprimen el `notes` que
 * calcula el servidor (`takab_api.compliance.compliance_block`).
 *
 * Tres ausencias distintas, tres textos distintos, ninguna en blanco:
 * - el cliente no declaró nada        → el literal de ausencia del servidor;
 * - el registro no se puede leer      → la razón, sin transcribir nada;
 * - el servidor no manda el bloque    → "NO DISPONIBLE", que no es lo mismo que
 *   "no hay nada declarado": afirmar lo segundo sin haberlo comprobado es
 *   exactamente el error que esta tarea existe para no repetir.
 */
export default function ComplianceDeclared({
  forensics,
  staleSince = null,
}: {
  forensics: ForensicsState;
  staleSince?: number | null;
}) {
  // `compliance` es requerido en el contrato, así que esto tipa
  // `ComplianceDocOut | undefined` por el `?.` de `data` y no hace falta cast.
  // El `undefined` que de verdad se atiende es el del servidor viejo.
  const doc: ComplianceDocOut | undefined = forensics.data?.compliance;
  const missing = forensics.data !== undefined && doc === undefined;
  const items = doc?.items ?? [];
  const unreadable = doc?.unreadable ?? null;

  return (
    <div className="soc-card" data-testid="declared-card">
      <div className="soc-card__hd">
        <div>
          <div>Marco normativo declarado</div>
          <div className="soc-card__sub" data-testid="declared-provenance">
            DECLARACIÓN DEL CLIENTE · TAKAB NO LA VERIFICA NI LA CERTIFICA
          </div>
        </div>
      </div>

      {missing ? (
        <p className="cmp-unreadable" role="note">
          MARCO DECLARADO NO DISPONIBLE · este servidor no lo publica todavía. No se afirma nada
          sobre lo que el cliente haya declarado o dejado de declarar.
        </p>
      ) : (
        <StateFrame
          label="MARCO DECLARADO"
          loading={forensics.loading}
          error={forensics.error}
          onRetry={forensics.refetch}
          empty={unreadable === null && items.length === 0}
          emptyText={doc?.notes?.[0] ?? "SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE"}
          staleSince={staleSince}
        >
          {unreadable !== null ? (
            <p className="cmp-unreadable" role="alert" data-testid="declared-unreadable">
              {unreadable}
            </p>
          ) : (
            <ul className="cmp-claims">
              {items.map((item) => (
                <li key={item.key} className="cmp-claim" data-testid="declared-claim">
                  <span className="cmp-claim__title">{item.title}</span>
                  <span className="cmp-claim__text">{item.claim}</span>
                  <span className="cmp-claim__ref">Dónde lo dice: {item.reference}</span>
                </li>
              ))}
            </ul>
          )}
        </StateFrame>
      )}

      {doc !== undefined && doc.notes.length > 0 && (
        <p className="cmp-notes" data-testid="declared-notes">
          {doc.notes.join(" ")}
        </p>
      )}
    </div>
  );
}
