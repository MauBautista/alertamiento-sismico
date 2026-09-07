// Administración de estaciones (T-1.36), como sub-superficie de /fleet.
//
// Deliberadamente NO es una ruta nueva: `allowed_routes` viene del servidor (RBAC §2) y
// añadir `/fleet/admin` habría exigido tocar la matriz para algo que ya está cubierto por
// la acción `manage_fleet`. Los controles de escritura solo se pintan si el token la trae
// — pintar un botón que siempre daría 403 es lo que prohíbe la regla de oro 7.

import { useState } from "react";
import { useSearchParams } from "react-router";

import { listSitesSitesGet } from "@takab/sdk";
import type { GatewayOut, GatewayRowOut, SiteOut } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import EnrollmentCodes from "./EnrollmentCodes";
import HardwareForm from "./HardwareForm";
import type { GatewayValues, SensorValues } from "./HardwareForm";
import GatewayAcuse from "./GatewayAcuse";
import RetireDialog from "./RetireDialog";
import SiteForm from "./SiteForm";
import type { SiteFormValues, WriteTarget } from "./SiteForm";
import { formatPoint } from "./geo";
import { useFleet } from "./useFleet";
import { useTenantOptions } from "./useTenantOptions";
import { FLEET_NEW_SITE_PARAMS } from "./newSiteHref";
import {
  useCreateGateway,
  useCreateSensor,
  useCreateSite,
  useRetireCodeConfigured,
  useRetireSite,
  useUpdateSite,
} from "./useFleetMutations";
import SiteLabel from "../../components/SiteLabel";
import { siteLabelText } from "./datosDeDemostracion";

type Editing =
  | { kind: "none" }
  | { kind: "new" }
  | { kind: "edit"; site: SiteOut }
  | { kind: "hardware"; site: SiteOut }
  // [T-2.37] Acuse tras el alta: cierra el formulario y entrega los UUID del edge.env.
  | { kind: "acuse"; site: SiteOut; gateway: GatewayRowOut }
  // [T-2.36] El retiro deja de ser un ConfirmButton: exige un segundo factor y por
  // tanto un diálogo con dos campos, no un doble clic armado.
  | { kind: "retire"; site: SiteOut }
  // [T-2.53] Códigos de alta de ocupantes de la estación (desbloquea GATE-HW).
  | { kind: "enrollment"; site: SiteOut };

function useSites() {
  return useQuery({
    queryKey: ["sites"],
    queryFn: async () => {
      const { data, response } = await listSitesSitesGet();
      if (data === undefined) throw new Error(`GET /sites falló (${response.status})`);
      return data;
    },
  });
}

/**
 * Compuerta de la acción `manage_fleet`. Va SEPARADA del panel a propósito: así, para
 * quien no administra la flota, no se monta ni un `useQuery` — no se pide `/sites`, no
 * se abre una mutación, no existe el botón. El gate no es cosmético.
 */
export default function FleetAdmin() {
  const canManage = useSessionStore((s) => s.me?.allowed_actions.manage_fleet === true);
  if (!canManage) return null;
  return <FleetAdminPanel />;
}

function FleetAdminPanel() {
  const sites = useSites();
  // [T-6.03] `?tenant=<id>&nueva=1`: la ficha del cliente manda aquí con el alta
  // abierta y el cliente preseleccionado. Se consume UNA vez (estado inicial) y se
  // limpia al cerrar el formulario, para que recargar no reabra un alta a medias.
  const [params, setParams] = useSearchParams();
  const preselectedTenant = params.get(FLEET_NEW_SITE_PARAMS.tenant);
  const [editing, setEditing] = useState<Editing>(() =>
    params.get(FLEET_NEW_SITE_PARAMS.nueva) === "1" ? { kind: "new" } : { kind: "none" },
  );
  function closeForm() {
    setEditing({ kind: "none" });
    if (params.has(FLEET_NEW_SITE_PARAMS.tenant) || params.has(FLEET_NEW_SITE_PARAMS.nueva)) {
      const next = new URLSearchParams(params);
      next.delete(FLEET_NEW_SITE_PARAMS.tenant);
      next.delete(FLEET_NEW_SITE_PARAMS.nueva);
      setParams(next, { replace: true });
    }
  }

  const create = useCreateSite();
  const update = useUpdateSite();
  const retire = useRetireSite();
  const addGateway = useCreateGateway();
  const addSensor = useCreateSensor();

  const fleet = useFleet();
  const gatewaysOf = (siteId: string): GatewayOut[] =>
    fleet.cabinets.filter((c) => c.gateway.site_id === siteId).map((c) => c.gateway);

  const tenantId = useSessionStore((s) => s.me?.tenant_id ?? null);
  const codeConfigured = useRetireCodeConfigured(tenantId);
  // [T-6.03] Lo dice el SERVIDOR (`/me.is_internal`), no el nombre del rol: un rol
  // interno debe NOMBRAR el cliente al crear un sitio (la API responde 400 si no);
  // un rol de cliente escribe siempre en el suyo y sólo se le rotula.
  const isInternal = useSessionStore((s) => s.me?.is_internal === true);
  const tenantOptions = useTenantOptions();
  const tenantName = (id: string | null): string | null =>
    id === null ? null : (tenantOptions.tenants.find((t) => t.tenant_id === id)?.name ?? null);
  const writeTarget: WriteTarget =
    editing.kind === "edit"
      ? // Un sitio no se muda de cliente: al editar sólo se rotula de quién es.
        {
          kind: "own",
          tenantId: editing.site.tenant_id,
          tenantName: tenantName(editing.site.tenant_id),
        }
      : isInternal
        ? {
            kind: "choose",
            tenants: tenantOptions.tenants,
            loading: tenantOptions.loading,
            error: tenantOptions.error,
            initialTenantId: preselectedTenant,
          }
        : { kind: "own", tenantId: tenantId ?? "", tenantName: tenantName(tenantId) };
  // [T-2.53] El botón de códigos se gatea por su PROPIA acción: `manage_fleet` y
  // `enrollment_manage` coinciden hoy en la web, pero derivarlo de la otra dejaría
  // el control colgando de una coincidencia (regla de oro 7).
  const canEnroll = useSessionStore((s) => s.me?.allowed_actions.enrollment_manage === true);

  const active = create.isPending || update.isPending;
  const hardwareBusy = addGateway.isPending || addSensor.isPending;
  const error = (create.error ?? update.error ?? retire.error)?.message ?? null;
  const hardwareError = (addGateway.error ?? addSensor.error)?.message ?? null;

  function submit(values: SiteFormValues) {
    const common = {
      code: values.code.trim(),
      name: values.name.trim(),
      lat: values.point.lat,
      lon: values.point.lon,
      criticality: values.criticality,
      address: values.address.trim() === "" ? null : values.address.trim(),
      building_type: values.building_type.trim() === "" ? null : values.building_type.trim(),
    };

    if (editing.kind === "new") {
      // [T-6.03] El cliente viaja SÓLO cuando el rol puede elegirlo. Para un rol de
      // cliente lo resuelve el servidor desde los claims: mandarlo sería una
      // invitación a probar con otro (`resolve_write_tenant` lo negaría igual).
      const body = isInternal ? { ...common, tenant_id: values.tenant_id } : common;
      create.mutate(body, { onSuccess: closeForm });
    } else if (editing.kind === "edit") {
      update.mutate(
        {
          siteId: editing.site.site_id,
          body: {
            ...common,
            status: "active",
            // Testigo de concurrencia: si otro operador guardó, el servidor da 409.
            base_row_version: editing.site.row_version,
          },
        },
        { onSuccess: () => setEditing({ kind: "none" }) },
      );
    }
  }

  function createGateway(site: SiteOut, values: GatewayValues) {
    addGateway.mutate(
      {
        site_id: site.site_id,
        serial: values.serial,
        // [T-2.37] La API sigue sin hablar con AWS —el thing lo crea Terraform—, pero
        // si el operador ya lo provisionó lo registra aquí. Sin esto, todo gabinete
        // dado de alta desde la consola quedaba no-sincronizable para siempre.
        iot_thing: values.iot_thing === "" ? null : values.iot_thing,
        has_wr1: values.has_wr1,
        // [T-2.31] Qué actuadores existen en el sitio; viaja firmado al edge.
        equipment: values.equipment,
      },
      {
        // Acusar recibo y CERRAR el formulario. Sin esto la pantalla no cambiaba al
        // pulsar y el operador volvía a pulsar: uno de los dos caminos por los que
        // aparecían gabinetes duplicados en el mismo sitio.
        onSuccess: (gateway) => setEditing({ kind: "acuse", site, gateway }),
      },
    );
  }

  function createSensor(siteId: string, values: SensorValues) {
    addSensor.mutate({
      site_id: siteId,
      kind: values.kind,
      model: values.model,
      serial: values.serial === "" ? null : values.serial,
      mount: values.mount === "" ? null : values.mount,
      // Vacío ⇒ null ⇒ el sitio queda SIN CALIBRAR, que es la verdad (T-1.33).
      calibration_source: values.calibration_source === "" ? null : values.calibration_source,
    });
  }

  return (
    <section className="fleet__admin" data-testid="fleet-admin">
      <header className="fleet__adminhd">
        <h2>{isInternal ? "ESTACIONES · TODOS LOS CLIENTES" : "ESTACIONES DEL TENANT"}</h2>
        {editing.kind === "none" && (
          <button type="button" className="soc-btn" onClick={() => setEditing({ kind: "new" })}>
            NUEVA ESTACIÓN
          </button>
        )}
      </header>

      {editing.kind === "enrollment" ? (
        <EnrollmentCodes site={editing.site} onClose={() => setEditing({ kind: "none" })} />
      ) : editing.kind === "acuse" ? (
        <GatewayAcuse
          gateway={editing.gateway}
          siteName={siteLabelText(editing.site.name, editing.site.code)}
          onDone={() => setEditing({ kind: "hardware", site: editing.site })}
        />
      ) : editing.kind === "hardware" ? (
        <HardwareForm
          site={editing.site}
          existing={gatewaysOf(editing.site.site_id)}
          submitting={hardwareBusy}
          error={hardwareError}
          onCreateGateway={(values) => createGateway(editing.site, values)}
          onCreateSensor={(values) => createSensor(editing.site.site_id, values)}
          onDone={() => setEditing({ kind: "none" })}
        />
      ) : editing.kind !== "none" ? (
        <SiteForm
          site={editing.kind === "edit" ? editing.site : undefined}
          writeTarget={writeTarget}
          submitting={active}
          error={error}
          onSubmit={submit}
          onCancel={closeForm}
        />
      ) : (
        <StateFrame
          label="ESTACIONES"
          loading={sites.isPending}
          error={sites.error?.message ?? null}
          onRetry={() => void sites.refetch()}
          empty={(sites.data ?? []).length === 0}
          emptyText="SIN ESTACIONES · CREA LA PRIMERA"
        >
          <div className="fleet__adminscroll">
            <table className="fleet__admintable">
              <thead>
                <tr>
                  <th>CÓDIGO</th>
                  <th>NOMBRE</th>
                  {/* [T-6.03] Un interno ve los sitios de TODOS los clientes (RLS):
                      sin esta columna la tabla no dice de quién es cada fila. */}
                  {isInternal && <th>CLIENTE</th>}
                  <th>UBICACIÓN</th>
                  <th>CRITICIDAD</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(sites.data ?? []).map((site) => (
                  <tr key={site.site_id} data-testid={`site-row-${site.code}`}>
                    <td className="soc-mono">{site.code}</td>
                    <td>
                      <SiteLabel name={site.name} code={site.code} />
                    </td>
                    {isInternal && (
                      <td data-testid={`site-tenant-${site.code}`}>
                        {tenantName(site.tenant_id) ?? (
                          // Sin catálogo no se inventa un nombre: el identificador es
                          // feo pero cierto.
                          <span className="soc-mono">{site.tenant_id}</span>
                        )}
                      </td>
                    )}
                    <td className="soc-mono">{formatPoint({ lat: site.lat, lon: site.lon })}</td>
                    <td className="soc-mono">{site.criticality.toUpperCase()}</td>
                    <td className="fleet__rowactions">
                      <button
                        type="button"
                        className="soc-btn soc-btn--secondary"
                        onClick={() => setEditing({ kind: "edit", site })}
                      >
                        EDITAR
                      </button>
                      <button
                        type="button"
                        className="soc-btn soc-btn--secondary"
                        onClick={() => setEditing({ kind: "hardware", site })}
                      >
                        HARDWARE
                      </button>
                      {canEnroll && (
                        <button
                          type="button"
                          className="soc-btn soc-btn--secondary"
                          onClick={() => setEditing({ kind: "enrollment", site })}
                        >
                          CÓDIGOS
                        </button>
                      )}
                      {/* Retiro lógico: la fila sobrevive porque su evidencia la
                        referencia. [T-2.36] Doble fricción en el diálogo. */}
                      <button
                        type="button"
                        className="soc-btn soc-btn--secondary"
                        disabled={retire.isPending}
                        onClick={() => setEditing({ kind: "retire", site })}
                      >
                        RETIRAR
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {error !== null && (
            <p className="soc-stateframe__error" role="alert" data-testid="fleet-admin-error">
              {error}
            </p>
          )}
        </StateFrame>
      )}

      {editing.kind === "retire" && (
        <RetireDialog
          kind="site"
          label={siteLabelText(editing.site.name, editing.site.code)}
          confirmValue={editing.site.code}
          codeConfigured={codeConfigured}
          pending={retire.isPending}
          error={retire.error?.message ?? null}
          onCancel={() => {
            retire.reset();
            setEditing({ kind: "none" });
          }}
          onConfirm={({ confirmValue, retireCode }) =>
            retire.mutate(
              {
                siteId: editing.site.site_id,
                body: { confirm_code: confirmValue, retire_code: retireCode },
              },
              { onSuccess: () => setEditing({ kind: "none" }) },
            )
          }
        />
      )}
    </section>
  );
}
