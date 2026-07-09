// Administración de estaciones (T-1.36), como sub-superficie de /fleet.
//
// Deliberadamente NO es una ruta nueva: `allowed_routes` viene del servidor (RBAC §2) y
// añadir `/fleet/admin` habría exigido tocar la matriz para algo que ya está cubierto por
// la acción `manage_fleet`. Los controles de escritura solo se pintan si el token la trae
// — pintar un botón que siempre daría 403 es lo que prohíbe la regla de oro 7.

import { useState } from "react";

import { listSitesSitesGet } from "@takab/sdk";
import type { SiteOut } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import ConfirmButton from "../../components/ConfirmButton";
import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import HardwareForm from "./HardwareForm";
import type { GatewayValues, SensorValues } from "./HardwareForm";
import SiteForm from "./SiteForm";
import type { SiteFormValues } from "./SiteForm";
import { formatPoint } from "./geo";
import {
  useCreateGateway,
  useCreateSensor,
  useCreateSite,
  useRetireSite,
  useUpdateSite,
} from "./useFleetMutations";

type Editing =
  | { kind: "none" }
  | { kind: "new" }
  | { kind: "edit"; site: SiteOut }
  | { kind: "hardware"; site: SiteOut };

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
  const [editing, setEditing] = useState<Editing>({ kind: "none" });

  const create = useCreateSite();
  const update = useUpdateSite();
  const retire = useRetireSite();
  const addGateway = useCreateGateway();
  const addSensor = useCreateSensor();

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
      create.mutate(common, { onSuccess: () => setEditing({ kind: "none" }) });
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

  function createGateway(siteId: string, values: GatewayValues) {
    // Sin `iot_thing`: la API no habla con AWS. El thing lo crea Terraform.
    addGateway.mutate({ site_id: siteId, serial: values.serial, has_wr1: values.has_wr1 });
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
        <h2>ESTACIONES DEL TENANT</h2>
        {editing.kind === "none" && (
          <button type="button" className="soc-btn" onClick={() => setEditing({ kind: "new" })}>
            NUEVA ESTACIÓN
          </button>
        )}
      </header>

      {editing.kind === "hardware" ? (
        <HardwareForm
          site={editing.site}
          submitting={hardwareBusy}
          error={hardwareError}
          onCreateGateway={(values) => createGateway(editing.site.site_id, values)}
          onCreateSensor={(values) => createSensor(editing.site.site_id, values)}
          onDone={() => setEditing({ kind: "none" })}
        />
      ) : editing.kind !== "none" ? (
        <SiteForm
          site={editing.kind === "edit" ? editing.site : undefined}
          submitting={active}
          error={error}
          onSubmit={submit}
          onCancel={() => setEditing({ kind: "none" })}
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
          <table className="fleet__admintable">
            <thead>
              <tr>
                <th>CÓDIGO</th>
                <th>NOMBRE</th>
                <th>UBICACIÓN</th>
                <th>CRITICIDAD</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(sites.data ?? []).map((site) => (
                <tr key={site.site_id} data-testid={`site-row-${site.code}`}>
                  <td className="soc-mono">{site.code}</td>
                  <td>{site.name}</td>
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
                    {/* Retiro lógico: la fila sobrevive porque su evidencia la referencia. */}
                    <ConfirmButton
                      label="RETIRAR"
                      variant="secondary"
                      disabled={retire.isPending}
                      onConfirm={() => retire.mutate(site.site_id)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {error !== null && (
            <p className="soc-stateframe__error" role="alert" data-testid="fleet-admin-error">
              {error}
            </p>
          )}
        </StateFrame>
      )}
    </section>
  );
}
