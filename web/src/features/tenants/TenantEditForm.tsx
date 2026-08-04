import { useState } from "react";

import type { TenantOut, TenantUpdate } from "@takab/sdk";

export interface TenantEditFormProps {
  tenant: TenantOut;
  pending: boolean;
  error: string | null;
  onSubmit: (body: TenantUpdate) => void;
  onCancel: () => void;
}

const STATUSES = ["trial", "active", "suspended"] as const;
const VISIBILITIES = ["private", "gov_shared"] as const;

const STATUS_LABEL: Record<string, string> = {
  trial: "Prueba",
  active: "Activo",
  suspended: "Suspendido",
};

const VISIBILITY_LABEL: Record<string, string> = {
  private: "Privado · solo este cliente",
  gov_shared: "Compartido con gobierno · Protección Civil lee sus datos",
};

/**
 * [T-2.51] Ficha editable del cliente (`PATCH /tenants/{id}`).
 *
 * `code` e `isolation_mode` se muestran pero NO se editan:
 * - `code` es la llave que TAKAB entrega fuera de banda; vive en runbooks, tickets
 *   y en el `edge.env` de los gabinetes. Cambiarlo desde un formulario rompería
 *   referencias que este proceso no puede seguir.
 * - `isolation_mode` de `logical` a `dedicated` es una migración de datos, no una
 *   casilla. Ofrecerlo aquí prometería un aislamiento que nadie ejecutó.
 *
 * Solo viajan al servidor los campos REALMENTE cambiados: es un PATCH, y reenviar
 * lo intacto reabriría la carrera que `base_row_version` cierra.
 */
export default function TenantEditForm({
  tenant,
  pending,
  error,
  onSubmit,
  onCancel,
}: TenantEditFormProps) {
  const [name, setName] = useState(tenant.name);
  const [vertical, setVertical] = useState(tenant.vertical ?? "");
  const [planCode, setPlanCode] = useState(tenant.plan_code);
  const [status, setStatus] = useState(tenant.status);
  const [visibility, setVisibility] = useState(tenant.visibility);

  const trimmedName = name.trim();
  const nextVertical = vertical.trim() === "" ? null : vertical.trim();
  const changes: TenantUpdate = {};
  if (trimmedName !== tenant.name) changes.name = trimmedName;
  if (nextVertical !== (tenant.vertical ?? null)) changes.vertical = nextVertical;
  if (planCode.trim() !== tenant.plan_code) changes.plan_code = planCode.trim();
  if (status !== tenant.status) changes.status = status as TenantUpdate["status"];
  if (visibility !== tenant.visibility) {
    changes.visibility = visibility as TenantUpdate["visibility"];
  }
  const dirty = Object.keys(changes).length > 0;
  const invalid = trimmedName === "" || planCode.trim() === "";

  return (
    <form
      className="mt-edit"
      data-testid="tenant-edit-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!dirty || invalid) {
          return;
        }
        onSubmit({ ...changes, base_row_version: tenant.row_version });
      }}
    >
      <div className="mt-edit__hd">
        <span className="soc-meta">FICHA DEL CLIENTE · {tenant.code}</span>
      </div>

      <label className="mt-edit__field">
        <span>Nombre</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label className="mt-edit__field">
        <span>Vertical (opcional)</span>
        <input value={vertical} onChange={(e) => setVertical(e.target.value)} />
      </label>
      <label className="mt-edit__field">
        <span>Plan</span>
        <input value={planCode} onChange={(e) => setPlanCode(e.target.value)} required />
      </label>
      <label className="mt-edit__field">
        <span>Estado del servicio</span>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      <label className="mt-edit__field">
        <span>Visibilidad</span>
        <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          {VISIBILITIES.map((v) => (
            <option key={v} value={v}>
              {VISIBILITY_LABEL[v]}
            </option>
          ))}
        </select>
      </label>

      {visibility === "gov_shared" && tenant.visibility !== "gov_shared" && (
        <p className="mt-edit__warn" role="note" data-testid="gov-shared-warning">
          AMPLÍA QUIÉN LEE ESTE CLIENTE · con `gov_shared`, cualquier `gov_operator` verá sus
          estaciones e incidentes. Queda en la bitácora con tu firma.
        </p>
      )}
      {status === "suspended" && tenant.status !== "suspended" && (
        <p className="mt-edit__warn" role="note" data-testid="suspended-warning">
          SUSPENDER ES ADMINISTRATIVO, NO OPERATIVO · los gabinetes siguen detectando y accionando
          sin nube (regla de oro 2). Para dejar un edificio sin protección hay que retirar su
          hardware.
        </p>
      )}

      {error !== null && (
        <p className="mt-edit__error" role="alert">
          {error}
        </p>
      )}

      <div className="mt-edit__actions">
        <button type="submit" className="soc-btn" disabled={pending || !dirty || invalid}>
          {pending ? "GUARDANDO…" : "GUARDAR FICHA"}
        </button>
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={pending}
          onClick={onCancel}
        >
          CANCELAR
        </button>
      </div>
    </form>
  );
}
