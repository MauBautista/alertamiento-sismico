import { useState } from "react";

import type { TenantOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import {
  COMPLIANCE_CATALOG,
  useComplianceLabels,
  useSaveComplianceLabels,
} from "./useComplianceLabels";

export interface ComplianceLabelsCardProps {
  tenant: TenantOut;
  /** `manage_tenants`: cargar el marco declarado es administrar la ficha del cliente. */
  canEdit: boolean;
}

/**
 * [T-2.82] Marco normativo DECLARADO por el cliente.
 *
 * Es la única tarjeta de la consola que muestra AFIRMACIONES en vez de mediciones, y
 * por eso está construida al revés que las demás: lo primero que se lee no es el dato,
 * es de quién es. Este repositorio ya citó una vez una norma de transporte
 * (`NOM-003-SCT`) como si fuera el marco sísmico del producto; un formulario que deje
 * teclear cualquier string y luego lo pinte con aire oficial repite ese fallo a escala.
 *
 * Tres cerraduras visibles aquí (las otras están en el servidor):
 *
 * 1. La clase de la afirmación se ELIGE de un catálogo cerrado — no se teclea. No hay
 *    forma de inventar una categoría, y el catálogo no nombra ninguna norma porque
 *    TAKAB todavía no tiene marco citable confirmado (GATE-LEGAL).
 * 2. "Dónde lo dice" es obligatorio. No hace verdadera la afirmación: la hace
 *    seguible por quien tenga que comprobarla, que es justo lo que faltó aquel día.
 * 3. Ni el rótulo de procedencia ni el deslinde se componen aquí: llegan del servidor
 *    (`notice`/`notes`), de la misma función que los imprime en el dictamen PDF.
 *
 * El VACÍO es un estado con texto propio: un cuadro en blanco en una tarjeta que se
 * llama "cumplimiento" se lee como "todo en orden", y eso nadie lo ha afirmado.
 */
export default function ComplianceLabelsCard({ tenant, canEdit }: ComplianceLabelsCardProps) {
  const data = useComplianceLabels(tenant.tenant_id);
  const mut = useSaveComplianceLabels(tenant.tenant_id);
  const [key, setKey] = useState("");
  const [claim, setClaim] = useState("");
  const [reference, setReference] = useState("");

  const doc = data.doc;
  const items = doc?.items ?? [];
  const unreadable = doc?.unreadable ?? null;
  const baseUpdatedAt = doc?.updated_at ?? null;
  const used = new Set(items.map((i) => i.key));
  const available = Object.entries(COMPLIANCE_CATALOG).filter(([k]) => !used.has(k));

  function replaceWith(next: { key: string; claim: string; reference: string }[]): void {
    mut.save({ items: next, base_updated_at: baseUpdatedAt });
  }

  function add(e: React.FormEvent): void {
    e.preventDefault();
    if (invalidReason !== null) return;
    replaceWith([
      ...items.map((i) => ({ key: i.key, claim: i.claim, reference: i.reference })),
      { key, claim: claim.trim(), reference: reference.trim() },
    ]);
    setKey("");
    setClaim("");
    setReference("");
  }

  // El botón deshabilitado dice QUÉ falta. Tres causas distintas tapadas por el mismo
  // gris dejan al operador adivinando (mismo criterio que VisibilityCard en T-2.59).
  const invalidReason =
    key === ""
      ? "Elige primero la clase de afirmación"
      : claim.trim() === ""
        ? "Escribe qué declara el cliente"
        : reference.trim() === ""
          ? "Falta dónde lo dice: sin referencia citable no se guarda"
          : null;

  return (
    <div className="soc-card" data-testid="compliance-card">
      <div className="soc-card__hd">
        <div>
          <div>Marco normativo declarado</div>
          <div className="soc-card__sub" data-testid="compliance-provenance">
            DECLARACIÓN DEL CLIENTE · TAKAB NO LA VERIFICA NI LA CERTIFICA
          </div>
        </div>
      </div>

      <StateFrame
        label="MARCO DECLARADO"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={unreadable === null && items.length === 0}
        emptyText={doc?.notes?.[0] ?? "SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE"}
        staleSince={data.staleSince}
      >
        {unreadable !== null ? (
          <p className="cmp-unreadable" role="alert" data-testid="compliance-unreadable">
            {unreadable}
          </p>
        ) : (
          <ul className="cmp-claims">
            {items.map((item) => (
              <li key={item.key} className="cmp-claim" data-testid="compliance-claim">
                <span className="cmp-claim__title">{item.title}</span>
                <span className="cmp-claim__text">{item.claim}</span>
                <span className="cmp-claim__ref">Dónde lo dice: {item.reference}</span>
                {canEdit && (
                  <button
                    type="button"
                    className="cmp-claim__drop"
                    onClick={() =>
                      replaceWith(
                        items
                          .filter((i) => i.key !== item.key)
                          .map((i) => ({ key: i.key, claim: i.claim, reference: i.reference })),
                      )
                    }
                    disabled={mut.pending}
                  >
                    Retirar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </StateFrame>

      {doc !== null && doc.notes.length > 0 && (
        <p className="cmp-notes" data-testid="compliance-notes">
          {doc.notes.join(" ")}
        </p>
      )}

      {/* Un registro ilegible NO se edita: guardar encima lo borraría sin que nadie
          haya podido leer qué decía, y lo que se pierde es una afirmación que quizá
          ya viajó dentro de un dictamen firmado. Se arregla en la base, a la vista. */}
      {canEdit && doc !== null && unreadable === null && (
        <form className="cmp-form" data-testid="compliance-form" onSubmit={add}>
          <label className="cmp-form__field">
            <span>Clase de afirmación</span>
            <select value={key} onChange={(e) => setKey(e.target.value)}>
              <option value="">— elige una clase —</option>
              {available.map(([k, title]) => (
                <option key={k} value={k}>
                  {title}
                </option>
              ))}
            </select>
          </label>
          <label className="cmp-form__field">
            <span>Qué declara el cliente</span>
            <input value={claim} maxLength={280} onChange={(e) => setClaim(e.target.value)} />
          </label>
          <label className="cmp-form__field">
            <span>Dónde lo dice (referencia citable)</span>
            <input
              value={reference}
              maxLength={280}
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
          {mut.error !== null && (
            <p className="cmp-form__error" role="alert">
              {mut.error}
            </p>
          )}
          <button
            type="submit"
            className="cmp-form__submit"
            disabled={mut.pending || invalidReason !== null || available.length === 0}
            title={
              mut.pending
                ? "Guardando…"
                : available.length === 0
                  ? "Ya hay una afirmación de cada clase"
                  : (invalidReason ?? undefined)
            }
          >
            Añadir
          </button>
        </form>
      )}
      {canEdit && unreadable === null && mut.error !== null && doc === null && (
        <p className="cmp-form__error" role="alert">
          {mut.error}
        </p>
      )}
    </div>
  );
}
