import { useState } from "react";

import type { SiteOut, TenantOut, UserOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import {
  USERS_STALE_MS,
  useCreateUser,
  useDeleteUser,
  useUpdateUser,
  useUserAction,
  useUsers,
} from "./useUsers";

/** Roles asignables desde la consola — espejo de `schemas/users.ASSIGNABLE_ROLES`.
 * `occupant` NO está: vive en el pool de ocupantes (ancla pool→rol) y se da de
 * alta con un código de enrolamiento, no aquí. */
const ROLES = [
  "takab_superadmin",
  "takab_support",
  "tenant_admin",
  "soc_operator",
  "gov_operator",
  "inspector",
  "building_admin",
  "brigadista",
  "security_guard",
] as const;

/** Los que solo TAKAB otorga (espejo de `schemas/users.PLATFORM_ROLES`). */
const PLATFORM_ROLES = new Set(["takab_superadmin", "takab_support"]);

const SURFACES = ["web", "mobile", "both"] as const;

export interface UsersCardProps {
  /** Cliente cuya ficha se está viendo; acota el alta y los selectores de sitio. */
  tenant: TenantOut;
  /** Catálogo de sitios visible; `undefined` = `/sites` degradó. */
  sites: SiteOut[] | undefined;
}

function scopeLabel(user: UserOut, sites: SiteOut[] | undefined): string {
  if (user.site_scope === "*") {
    return "TODO EL CLIENTE";
  }
  if (user.site_scope === "") {
    // Regla de oro 7: "vacío" no es "ninguna" hasta que el servidor lo imponga.
    return "SIN ALCANCE DECLARADO";
  }
  const ids = user.site_scope.split(",");
  if (sites === undefined) {
    return `${ids.length} ESTACIÓN(ES)`;
  }
  const names = ids.map((id) => sites.find((s) => s.site_id === id)?.code ?? id.slice(0, 8));
  return names.join(" · ");
}

/**
 * [T-2.54] Gestión de usuarios, dentro de la ficha del cliente.
 *
 * Deliberadamente NO es una ruta nueva: `allowed_routes` viene del servidor y
 * `/tenants` ya lo tienen exactamente los roles que pueden llegar aquí. La
 * autorización real la impone el servidor en cada llamada; esta tarjeta se monta
 * solo con la acción `manage_users` para no pintar controles condenados al 403.
 *
 * Lo que la pantalla NO ofrece, por diseño:
 * - **Fijar una contraseña.** La temporal la genera y entrega Cognito por correo;
 *   una clave escrita en este formulario viajaría por el historial del navegador.
 * - **Mover a alguien de cliente.** `tenant_id` no es editable: re-tenantizaría su
 *   rastro de auditoría, que es evidencia inmutable (regla de oro 11).
 * - **Editar usuarios de otro cliente.** El servidor responde 404 y aquí no se
 *   listan siquiera.
 */
export default function UsersCard({ tenant, sites }: UsersCardProps) {
  const myRole = useSessionStore((s) => s.me?.role ?? "");
  const now = useNow(5000);
  const isInternal = myRole === "takab_superadmin" || myRole === "takab_support";
  const data = useUsers(true);
  const create = useCreateUser();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const action = useUserAction();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ email: "", role: "soc_operator", surface: "web" });
  const [editing, setEditing] = useState<string | null>(null);
  const [scopeDraft, setScopeDraft] = useState<string[]>([]);

  const tenantSites = (sites ?? []).filter((s) => s.tenant_id === tenant.tenant_id);
  const assignable = ROLES.filter((r) => isInternal || !PLATFORM_ROLES.has(r));
  const busy = create.isPending || update.isPending || remove.isPending || action.isPending;
  const staleSince =
    !data.loading &&
    data.error === null &&
    data.dataUpdatedAt > 0 &&
    now - data.dataUpdatedAt > USERS_STALE_MS
      ? data.dataUpdatedAt
      : null;
  const mutationError =
    (create.error ?? update.error ?? remove.error ?? action.error)?.message ?? null;

  function startEdit(user: UserOut): void {
    setEditing(user.username);
    setScopeDraft(
      user.site_scope === "*" || user.site_scope === "" ? [] : user.site_scope.split(","),
    );
  }

  return (
    <div className="soc-card users" data-testid="users-card">
      <div className="soc-card__hd">
        <div>
          <div>Usuarios del cliente</div>
          <div className="soc-card__sub">
            QUIÉN ENTRA A {tenant.name.toUpperCase()} · ROL, ALCANCE Y SUPERFICIE
          </div>
        </div>
        {data.backend !== null && (
          <span
            className={`soc-pill soc-pill--${data.backend === "cognito" ? "ok" : "crit"}`}
            data-testid="users-backend"
          >
            {data.backend === "cognito"
              ? "DIRECTORIO COGNITO"
              : "DIRECTORIO SIMULADO · NADA SE ESCRIBE DE VERDAD"}
          </span>
        )}
      </div>

      <p className="users__note">
        La contraseña temporal la genera y envía Cognito: TAKAB no la fija, no la ve y no la
        muestra. Toda alta, cambio de rol o baja queda en la bitácora con tu firma.
      </p>

      <StateFrame
        label="USUARIOS"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={data.users.length === 0}
        emptyText="SIN USUARIOS EN ESTE CLIENTE"
        staleSince={staleSince}
      >
        <ul className="users__list">
          {data.users.map((user) => (
            <li key={user.username} className="users__row" data-testid="user-row">
              <div className="users__id">
                <span className="users__email">{user.email}</span>
                <span className="soc-meta">
                  {user.role} · {user.surface.toUpperCase()} · {scopeLabel(user, sites)} ·{" "}
                  {user.enabled ? user.status : "DESHABILITADO"}
                </span>
              </div>
              <div className="users__rowactions">
                <button
                  type="button"
                  className="soc-btn soc-btn--secondary"
                  disabled={busy}
                  onClick={() => (editing === user.username ? setEditing(null) : startEdit(user))}
                >
                  {editing === user.username ? "CERRAR" : "EDITAR"}
                </button>
                <button
                  type="button"
                  className="soc-btn soc-btn--secondary"
                  disabled={busy}
                  onClick={() =>
                    update.mutate({
                      username: user.username,
                      body: { enabled: !user.enabled },
                    })
                  }
                >
                  {user.enabled ? "DESHABILITAR" : "HABILITAR"}
                </button>
              </div>

              {editing === user.username && (
                <div className="users__editor" data-testid="user-editor">
                  <label className="users__field">
                    <span>Rol</span>
                    <select
                      value={user.role}
                      onChange={(e) =>
                        update.mutate({
                          username: user.username,
                          body: { role: e.target.value },
                        })
                      }
                    >
                      {assignable.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="users__field">
                    <span>Superficie</span>
                    <select
                      value={user.surface}
                      onChange={(e) =>
                        update.mutate({
                          username: user.username,
                          body: { surface: e.target.value as "web" | "mobile" | "both" },
                        })
                      }
                    >
                      {SURFACES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>

                  <fieldset className="users__scope">
                    <legend>Alcance por estación</legend>
                    <p className="soc-meta">
                      Sin ninguna marcada, el usuario ve TODO el cliente. Marcar estaciones escribe
                      `custom:site_scope` y acota lo que el servidor le entrega.
                    </p>
                    {tenantSites.length === 0 && (
                      <p className="soc-meta">SIN ESTACIONES QUE ACOTAR EN ESTE CLIENTE</p>
                    )}
                    {tenantSites.map((site) => (
                      <label key={site.site_id} className="users__check">
                        <input
                          type="checkbox"
                          checked={scopeDraft.includes(site.site_id)}
                          onChange={(e) =>
                            setScopeDraft((prev) =>
                              e.target.checked
                                ? [...prev, site.site_id]
                                : prev.filter((id) => id !== site.site_id),
                            )
                          }
                        />
                        {site.code} · {site.name}
                      </label>
                    ))}
                    <button
                      type="button"
                      className="soc-btn"
                      disabled={busy}
                      onClick={() =>
                        update.mutate({
                          username: user.username,
                          body: {
                            site_scope: scopeDraft.length === 0 ? "*" : scopeDraft.join(","),
                          },
                        })
                      }
                    >
                      GUARDAR ALCANCE
                    </button>
                  </fieldset>

                  <div className="users__rowactions">
                    <button
                      type="button"
                      className="soc-btn soc-btn--secondary"
                      disabled={busy}
                      onClick={() => action.mutate({ username: user.username, action: "reset" })}
                    >
                      RESTABLECER CONTRASEÑA
                    </button>
                    <button
                      type="button"
                      className="soc-btn soc-btn--secondary"
                      disabled={busy}
                      onClick={() => action.mutate({ username: user.username, action: "resend" })}
                    >
                      REENVIAR INVITACIÓN
                    </button>
                    <button
                      type="button"
                      className="soc-btn soc-btn--secondary"
                      disabled={busy}
                      onClick={() => remove.mutate(user.username)}
                    >
                      DAR DE BAJA
                    </button>
                  </div>
                  <p className="soc-meta">
                    DESHABILITAR es reversible y conserva la cuenta; DAR DE BAJA la elimina del
                    pool. Su rastro en la bitácora sobrevive a ambas.
                  </p>
                </div>
              )}
            </li>
          ))}
        </ul>
      </StateFrame>

      {action.data !== undefined && (
        <p className="users__ack" role="status" data-testid="user-action-ack">
          {action.data.detail}
        </p>
      )}
      {mutationError !== null && (
        <p className="users__error" role="alert" data-testid="users-error">
          {mutationError}
        </p>
      )}

      {creating ? (
        <form
          className="users__new"
          data-testid="user-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(
              {
                email: draft.email.trim(),
                role: draft.role,
                surface: draft.surface as "web" | "mobile" | "both",
                site_scope: "*",
                // Los roles internos DEBEN nombrar el tenant destino; los de tenant
                // no pueden mandarlo (el servidor rechaza uno ajeno con 403).
                tenant_id: isInternal ? tenant.tenant_id : null,
              },
              {
                onSuccess: () => {
                  setCreating(false);
                  setDraft({ email: "", role: "soc_operator", surface: "web" });
                },
              },
            );
          }}
        >
          <label className="users__field">
            <span>Correo</span>
            <input
              type="email"
              value={draft.email}
              onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
              required
            />
          </label>
          <label className="users__field">
            <span>Rol</span>
            <select
              value={draft.role}
              onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value }))}
            >
              {assignable.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="users__field">
            <span>Superficie</span>
            <select
              value={draft.surface}
              onChange={(e) => setDraft((d) => ({ ...d, surface: e.target.value }))}
            >
              {SURFACES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="users__rowactions">
            <button
              type="submit"
              className="soc-btn"
              disabled={create.isPending || draft.email.trim() === ""}
            >
              {create.isPending ? "CREANDO…" : "CREAR E INVITAR"}
            </button>
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              onClick={() => {
                create.reset();
                setCreating(false);
              }}
            >
              CANCELAR
            </button>
          </div>
          <p className="soc-meta">
            El alcance nace en TODO EL CLIENTE y se acota después, por estación. Nace así porque un
            usuario recién creado sin alcance no vería nada y parecería un fallo del sistema.
          </p>
        </form>
      ) : (
        <button type="button" className="soc-btn" onClick={() => setCreating(true)}>
          + NUEVO USUARIO
        </button>
      )}
    </div>
  );
}
