import { useState } from "react";

import type { SiteOut, TenantOut, UserOut } from "@takab/sdk";

import Button from "../../components/Button";
import Card from "../../components/Card";
import ConfirmButton from "../../components/ConfirmButton";
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
import { siteLabelText } from "../fleet/datosDeDemostracion";

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
  const now = useNow(5000);
  // [T-6.03] Lo declara `/me` (`is_internal`), no el nombre del rol: la lista de
  // roles internos vive en `auth/matrix.INTERNAL_ROLES` y viaja con el token.
  const isInternal = useSessionStore((s) => s.me?.is_internal === true);
  // [A-108] La cuenta en sesión. Su fila no ofrece desarmarse a sí misma.
  const meSub = useSessionStore((s) => s.me?.sub ?? null);
  const data = useUsers(true);
  // [A-018 · T-8.09] `GET /users` sólo acota a los roles DE CLIENTE; a un rol
  // interno le da el pool entero. La tarjeta es la de UN cliente —su subtítulo
  // dice «QUIÉN ENTRA A {cliente}»— y pintaba debajo a los de todos. El filtro
  // va aquí, contra el cliente de la ficha; para un rol de cliente coincide con
  // el del servidor, así que no hay dos verdades que puedan divergir.
  const users = data.users.filter((u) => u.tenant_id === tenant.tenant_id);
  const create = useCreateUser();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const action = useUserAction();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ email: "", role: "soc_operator", surface: "web" });
  const [editing, setEditing] = useState<string | null>(null);
  const [scopeDraft, setScopeDraft] = useState<string[]>([]);
  // [A-107] El rol ELEGIDO todavía no es el rol aplicado: cambiarlo reparte o
  // quita acceso a datos (la RLS se ancla en `custom:role`) y se confirma aparte.
  const [roleDraft, setRoleDraft] = useState<{ username: string; role: string } | null>(null);

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
    <Card
      title="Usuarios del cliente"
      sub={<>QUIÉN ENTRA A {tenant.name.toUpperCase()} · ROL, ALCANCE Y SUPERFICIE</>}
      aside={
        <>
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
        </>
      }
      className="users"
      testId="users-card"
    >
      <p className="users__note">
        La contraseña temporal la genera y envía Cognito: TAKAB no la fija, no la ve y no la
        muestra. Toda alta, cambio de rol o baja queda en la bitácora con tu firma.
      </p>

      <StateFrame
        label="USUARIOS"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={users.length === 0}
        emptyText="SIN USUARIOS EN ESTE CLIENTE"
        staleSince={staleSince}
      >
        <ul className="users__list">
          {users.map((user) => {
            // [A-108] Mi propia fila: ni deshabilitarme, ni quitarme el rol, ni
            // darme de baja. El servidor sólo vetaba la baja (409), y un admin
            // podía dejarse fuera de la consola con un clic.
            const mine = meSub !== null && user.username === meSub;
            const motivoMio = "Es tu propia cuenta: pídeselo a otro administrador";
            const rolElegido =
              roleDraft !== null && roleDraft.username === user.username ? roleDraft.role : null;
            return (
              <li key={user.username} className="users__row" data-testid="user-row">
                <div className="users__id">
                  <span className="users__email">{user.email}</span>
                  <span className="soc-meta">
                    {user.role} · {user.surface.toUpperCase()} · {scopeLabel(user, sites)} ·{" "}
                    {user.enabled ? user.status : "DESHABILITADO"}
                    {mine ? " · TU CUENTA" : ""}
                  </span>
                </div>
                <div className="users__rowactions">
                  <Button
                    variant="secondary"
                    disabled={busy}
                    title={busy ? "Operación en curso…" : undefined}
                    onClick={() => (editing === user.username ? setEditing(null) : startEdit(user))}
                  >
                    {editing === user.username ? "CERRAR" : "EDITAR"}
                  </Button>
                  {user.enabled ? (
                    // [A-107] Deshabilitar corta el acceso de una persona: dos pasos.
                    <ConfirmButton
                      label="DESHABILITAR"
                      variant="secondary"
                      disabled={busy || mine}
                      title={
                        mine
                          ? motivoMio
                          : busy
                            ? "Operación en curso…"
                            : "Reversible: conserva la cuenta"
                      }
                      onConfirm={() =>
                        update.mutate({ username: user.username, body: { enabled: false } })
                      }
                    />
                  ) : (
                    <Button
                      variant="secondary"
                      disabled={busy}
                      title={busy ? "Operación en curso…" : undefined}
                      onClick={() =>
                        update.mutate({ username: user.username, body: { enabled: true } })
                      }
                    >
                      HABILITAR
                    </Button>
                  )}
                </div>

                {editing === user.username && (
                  <div className="users__editor" data-testid="user-editor">
                    <label className="users__field">
                      <span>Rol</span>
                      <select
                        value={rolElegido ?? user.role}
                        disabled={mine}
                        title={mine ? motivoMio : undefined}
                        onChange={(e) =>
                          setRoleDraft({ username: user.username, role: e.target.value })
                        }
                      >
                        {assignable.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </label>
                    {rolElegido !== null && rolElegido !== user.role && (
                      <div className="users__rowactions">
                        <ConfirmButton
                          label={`CAMBIAR ROL A ${rolElegido}`}
                          disabled={busy}
                          title="Cambia qué datos ve y qué puede hacer esta persona"
                          onConfirm={() => {
                            update.mutate({ username: user.username, body: { role: rolElegido } });
                            setRoleDraft(null);
                          }}
                        />
                        <Button variant="secondary" onClick={() => setRoleDraft(null)}>
                          DEJAR {user.role}
                        </Button>
                      </div>
                    )}

                    <label className="users__field">
                      <span>Superficie</span>
                      <select
                        value={user.surface}
                        // [A-108] Quitarse la superficie web es cerrarse la consola.
                        disabled={mine}
                        title={mine ? motivoMio : undefined}
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
                        Sin ninguna marcada, el usuario ve TODO el cliente. Marcar estaciones
                        escribe `custom:site_scope` y acota lo que el servidor le entrega.
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
                          {site.code} · {siteLabelText(site.name, site.code)}
                        </label>
                      ))}
                      <Button
                        disabled={busy}
                        title={busy ? "Operación en curso…" : undefined}
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
                      </Button>
                    </fieldset>

                    <div className="users__rowactions">
                      <Button
                        variant="secondary"
                        disabled={busy}
                        title={busy ? "Operación en curso…" : undefined}
                        onClick={() => action.mutate({ username: user.username, action: "reset" })}
                      >
                        RESTABLECER CONTRASEÑA
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={busy}
                        title={busy ? "Operación en curso…" : undefined}
                        onClick={() => action.mutate({ username: user.username, action: "resend" })}
                      >
                        REENVIAR INVITACIÓN
                      </Button>
                      {/* [A-107] Irreversible: dos pasos. */}
                      <ConfirmButton
                        label="DAR DE BAJA"
                        variant="secondary"
                        disabled={busy || mine}
                        title={
                          mine
                            ? motivoMio
                            : busy
                              ? "Operación en curso…"
                              : "Irreversible: elimina la cuenta del pool"
                        }
                        onConfirm={() => remove.mutate(user.username)}
                      />
                    </div>
                    <p className="soc-meta">
                      DESHABILITAR es reversible y conserva la cuenta; DAR DE BAJA la elimina del
                      pool. Su rastro en la bitácora sobrevive a ambas.
                    </p>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </StateFrame>

      {data.truncated && (
        <p className="users__note" role="status" data-testid="users-truncated">
          LISTA INCOMPLETA · el directorio tiene más identidades de las que esta pantalla recorre de
          una vez. Faltan usuarios abajo: no la leas como la lista entera.
        </p>
      )}

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
            <Button
              type="submit"
              disabled={create.isPending || draft.email.trim() === ""}
              title={
                create.isPending
                  ? "Creando…"
                  : draft.email.trim() === ""
                    ? "Escribe el correo del usuario"
                    : undefined
              }
            >
              {create.isPending ? "CREANDO…" : "CREAR E INVITAR"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                create.reset();
                setCreating(false);
              }}
            >
              CANCELAR
            </Button>
          </div>
          <p className="soc-meta">
            El alcance nace en TODO EL CLIENTE y se acota después, por estación. Nace así porque un
            usuario recién creado sin alcance no vería nada y parecería un fallo del sistema.
          </p>
        </form>
      ) : (
        <Button onClick={() => setCreating(true)}>+ NUEVO USUARIO</Button>
      )}
    </Card>
  );
}
