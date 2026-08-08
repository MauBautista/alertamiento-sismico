import type { ForensicsOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import type { ForensicsState } from "./useForensics";

/**
 * `ForensicsOut` + el bloque de cumplimiento (T-2.82).
 *
 * El SDK se regenera en la integración, no aquí, así que el campo se declara a mano
 * como intersección: cuando `shared/sdk-ts` se regenere, `compliance` pasará a ser
 * propio de `ForensicsOut` y esta intersección seguirá compilando sin tocar nada.
 * Espejo de `api/src/takab_api/schemas/compliance.py`.
 */
export interface DeclaredClaim {
  key: string;
  title: string;
  claim: string;
  reference: string;
}

export interface DeclaredDoc {
  provenance: string;
  notice: string;
  items: DeclaredClaim[];
  notes: string[];
  unreadable: string | null;
}

export type ForensicsWithCompliance = ForensicsOut & { compliance?: DeclaredDoc };

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
  const doc = (forensics.data as ForensicsWithCompliance | undefined)?.compliance;
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
          MARCO DECLARADO NO DISPONIBLE · este servidor no lo publica todavía. No se
          afirma nada sobre lo que el cliente haya declarado o dejado de declarar.
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
