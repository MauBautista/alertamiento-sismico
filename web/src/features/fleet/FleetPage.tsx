import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import FleetAdmin from "./FleetAdmin";
import GatewayForm from "./GatewayForm";
import RetireDialog from "./RetireDialog";
import SiteCard from "./SiteCard";
import { FLEET_STALE_MS, useFleet } from "./useFleet";
import type { FleetCabinet } from "./useFleet";
import {
  useFleetSyncStates,
  useRestoreGateway,
  useRetireCodeConfigured,
  useRetireGateway,
  useUpdateGateway,
} from "./useFleetMutations";

function Kpi({ label, value, kind }: { label: string; value: number; kind?: string }) {
  return (
    <div className={`fleet__kpi${kind ? ` fleet__kpi--${kind}` : ""}`} data-testid="fleet-kpi">
      <span className="fleet__kpi-val">{value}</span>
      <span className="fleet__kpi-lbl">{label}</span>
    </div>
  );
}

/** Conteo por derived_state EXACTO del servidor (verdad única, G7). */
function countStates(cabinets: FleetCabinet[]) {
  return {
    total: cabinets.length,
    ok: cabinets.filter((c) => c.gateway.derived_state === "OPERATIVO").length,
    warn: cabinets.filter((c) => c.gateway.derived_state === "DEGRADADO").length,
    crit: cabinets.filter((c) => c.gateway.derived_state === "SIN ENLACE").length,
  };
}

/** T-1.28 · Flota Edge — inventario de gabinetes (mockup 2, FleetEdge.jsx). */
type GatewayAction =
  | { kind: "none" }
  | { kind: "edit"; cabinet: FleetCabinet }
  | { kind: "retire"; cabinet: FleetCabinet };

export default function FleetPage() {
  // [T-2.37] Los retirados solo aparecen si se piden: es la única forma de
  // restaurarlos, y verlos siempre reproduciría el defecto que T-2.35 cerró.
  const [includeRetired, setIncludeRetired] = useState(false);
  const fleet = useFleet({ includeRetired });
  const now = useNow(5000);

  const canManage = useSessionStore((s) => s.me?.allowed_actions.manage_fleet === true);
  const tenantId = useSessionStore((s) => s.me?.tenant_id ?? null);
  const codeConfigured = useRetireCodeConfigured(canManage ? tenantId : null);
  const syncStates = useFleetSyncStates(fleet.cabinets.length > 0);
  const [action, setAction] = useState<GatewayAction>({ kind: "none" });
  const updateGateway = useUpdateGateway();
  const retireGateway = useRetireGateway();
  const restoreGateway = useRestoreGateway();
  const staleSince =
    !fleet.loading &&
    !fleet.error &&
    fleet.dataUpdatedAt > 0 &&
    now - fleet.dataUpdatedAt > FLEET_STALE_MS
      ? fleet.dataUpdatedAt
      : null;
  const counts = countStates(fleet.cabinets);

  return (
    <section className="fleet" data-screen-label="02 Flota Edge">
      <header className="fleet__hd">
        <div>
          <span className="soc-meta">MANTENIMIENTO · CAMPO</span>
          <h1 className="fleet__title">Flota Edge y Estado de Gabinetes</h1>
          <p className="fleet__sub">
            Inventario de gateways TAKAB · enlace MQTT/SeedLink, UPS, actuadores BACnet/IP.
          </p>
        </div>
        <div className="fleet__kpis">
          <Kpi label="GABINETES" value={counts.total} />
          <Kpi label="OPERATIVOS" value={counts.ok} kind="ok" />
          <Kpi label="DEGRADADOS" value={counts.warn} kind="warn" />
          <Kpi label="SIN ENLACE" value={counts.crit} kind="crit" />
        </div>
      </header>

      {canManage && (
        <label className="fleet__toggle" data-testid="fleet-include-retired">
          <input
            type="checkbox"
            checked={includeRetired}
            onChange={(e) => setIncludeRetired(e.target.checked)}
          />
          <span>VER RETIRADOS</span>
        </label>
      )}

      <StateFrame
        label="FLOTA EDGE"
        loading={fleet.loading}
        error={fleet.error}
        onRetry={fleet.refetch}
        empty={fleet.cabinets.length === 0}
        emptyText="SIN GABINETES REGISTRADOS EN EL TENANT"
        staleSince={staleSince}
      >
        <div className="fleet__grid">
          {fleet.cabinets.map((c) => (
            <SiteCard
              key={c.gateway.gateway_id}
              cabinet={c}
              syncState={syncStates.get(c.gateway.gateway_id)}
              onEdit={canManage ? () => setAction({ kind: "edit", cabinet: c }) : undefined}
              onRetire={canManage ? () => setAction({ kind: "retire", cabinet: c }) : undefined}
              onRestore={canManage ? () => restoreGateway.mutate(c.gateway.gateway_id) : undefined}
              restoring={restoreGateway.isPending}
            />
          ))}
        </div>
      </StateFrame>

      {/* FUERA del StateFrame a propósito: un tenant sin gabinetes cae en el estado
          `empty`, y ahí es precisamente cuando hace falta poder crear la primera
          estación. Enterrar el alta dentro del marco la haría inalcanzable. */}
      <FleetAdmin />

      {action.kind === "edit" && (
        <GatewayForm
          gateway={action.cabinet.gateway}
          siteName={action.cabinet.siteName}
          submitting={updateGateway.isPending}
          error={updateGateway.error?.message ?? null}
          onCancel={() => {
            updateGateway.reset();
            setAction({ kind: "none" });
          }}
          onSubmit={(values) =>
            updateGateway.mutate(
              {
                gatewayId: action.cabinet.gateway.gateway_id,
                body: {
                  site_id: action.cabinet.gateway.site_id,
                  serial: values.serial,
                  iot_thing: values.iot_thing === "" ? null : values.iot_thing,
                  fw_version: values.fw_version === "" ? null : values.fw_version,
                  has_wr1: values.has_wr1,
                  equipment: values.equipment,
                  installed_at: action.cabinet.gateway.installed_at,
                  // Testigo de concurrencia: si otro admin guardó, el servidor da 409
                  // en vez de pisar en silencio qué actuadores tiene el edificio.
                  base_row_version: action.cabinet.gateway.row_version,
                },
              },
              { onSuccess: () => setAction({ kind: "none" }) },
            )
          }
        />
      )}

      {action.kind === "retire" && (
        <RetireDialog
          kind="gateway"
          label={action.cabinet.siteName}
          confirmValue={action.cabinet.gateway.serial}
          codeConfigured={codeConfigured}
          pending={retireGateway.isPending}
          error={retireGateway.error?.message ?? null}
          onCancel={() => {
            retireGateway.reset();
            setAction({ kind: "none" });
          }}
          onConfirm={({ confirmValue, retireCode }) =>
            retireGateway.mutate(
              {
                gatewayId: action.cabinet.gateway.gateway_id,
                body: { confirm_serial: confirmValue, retire_code: retireCode },
              },
              { onSuccess: () => setAction({ kind: "none" }) },
            )
          }
        />
      )}
    </section>
  );
}
