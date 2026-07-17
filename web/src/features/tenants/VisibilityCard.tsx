import { useState } from "react";

import type { TenantOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import { useVisibilityGrants, useVisibilityMutations } from "./useVisibility";

export interface VisibilityCardProps {
  /** El cliente cuya visibilidad se configura (grantee). */
  grantee: TenantOut;
  /** Catálogo de clientes para elegir el target. */
  allTenants: TenantOut[];
}

/**
 * [T-1.73] Visibilidad configurable entre clientes. SOLO superadmin (la tarjeta se
 * monta con `manage_visibility`). Concede al cliente seleccionado ver METADATOS (que
 * existen las estaciones) y/o DATOS en vivo de otro cliente o de TODOS. Un grant AÑADE
 * lectura, jamás escritura (el servidor y la RLS lo garantizan).
 */
export default function VisibilityCard({ grantee, allTenants }: VisibilityCardProps) {
  const data = useVisibilityGrants(grantee.tenant_id, true);
  const mut = useVisibilityMutations(grantee.tenant_id);
  const [target, setTarget] = useState(""); // "" = sin elegir, "ALL" = todos, uuid = específico
  const [meta, setMeta] = useState(true);
  const [live, setLive] = useState(false);

  const others = allTenants.filter((t) => t.tenant_id !== grantee.tenant_id);
  const targetName = (id: string | null, all: boolean): string =>
    all ? "TODOS los clientes" : (others.find((t) => t.tenant_id === id)?.name ?? id ?? "—");

  const invalid = target === "" || (!meta && !live);

  function submit(e: React.FormEvent): void {
    e.preventDefault();
    if (invalid) return;
    mut.grant({
      grantee_tenant_id: grantee.tenant_id,
      target_all: target === "ALL",
      target_tenant_id: target === "ALL" ? null : target,
      can_view_metadata: meta,
      can_view_data: live,
    });
    setTarget("");
  }

  return (
    <div className="soc-card" data-testid="visibility-card">
      <div className="soc-card__hd">
        <div>
          <div>Visibilidad entre clientes</div>
          <div className="soc-card__sub">
            QUÉ PUEDE VER {grantee.name.toUpperCase()} DE OTROS CLIENTES
          </div>
        </div>
      </div>

      <StateFrame
        label="VISIBILIDAD"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={data.grants.length === 0}
        emptyText="SIN VISIBILIDAD CRUZADA · ESTE CLIENTE SOLO VE LO SUYO"
        staleSince={null}
      >
        <ul className="vis-grants">
          {data.grants.map((g) => (
            <li key={g.grant_id} className="vis-grant" data-testid="visibility-grant">
              <span className="vis-grant__target">
                → {targetName(g.target_tenant_id, g.target_all)}
              </span>
              <span className="soc-meta">
                {g.can_view_metadata && "METADATOS"}
                {g.can_view_metadata && g.can_view_data && " + "}
                {g.can_view_data && "DATOS EN VIVO"}
              </span>
              <button
                type="button"
                className="vis-grant__revoke"
                onClick={() => mut.revoke(g.grant_id)}
                disabled={mut.pending}
              >
                Revocar
              </button>
            </li>
          ))}
        </ul>
      </StateFrame>

      <form className="vis-form" data-testid="visibility-form" onSubmit={submit}>
        <label className="vis-form__field">
          <span>Conceder que vea a</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">— elige un cliente —</option>
            <option value="ALL">TODOS los clientes</option>
            {others.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label className="vis-form__check">
          <input type="checkbox" checked={meta} onChange={(e) => setMeta(e.target.checked)} /> Ver
          que existen (metadatos)
        </label>
        <label className="vis-form__check">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Ver
          datos en vivo
        </label>
        {mut.error !== null && (
          <p className="vis-form__error" role="alert">
            {mut.error}
          </p>
        )}
        <button type="submit" className="vis-form__submit" disabled={mut.pending || invalid}>
          Conceder
        </button>
      </form>
    </div>
  );
}
