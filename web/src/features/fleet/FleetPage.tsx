import { useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import FleetAdmin from "./FleetAdmin";
import FleetToolbar from "./FleetToolbar";
import GatewayForm from "./GatewayForm";
import RetireDialog from "./RetireDialog";
import SiteCard from "./SiteCard";
import { DEFAULT_FILTERS, applyFilters, isFiltering } from "./fleetFilter";
import type { FleetFilters } from "./fleetFilter";
import { FLEET_STALE_MS, useFleet } from "./useFleet";
import type { FleetCabinet } from "./useFleet";
import {
  useFleetHealth,
  useFleetSyncStates,
  useRestoreGateway,
  useRetireCodeConfigured,
  useRetireGateway,
  useUpdateGateway,
} from "./useFleetMutations";

/**
 * Un contador de la tira superior.
 *
 * [T-2.59] `value === null` significa NO HAY DATO, y entonces se pinta `S/D` y
 * se RETIRA el color semántico: un "0 SIN ENLACE" en rojo tranquilo o un
 * "0 OPERATIVOS" en verde son afirmaciones sobre la flota que nadie ha
 * comprobado. Regla de oro 7 — mostrar un dato inventado como si fuera fresco
 * es peor que no mostrar nada, porque el cero es tranquilizador.
 */
function Kpi({ label, value, kind }: { label: string; value: number | null; kind?: string }) {
  const sinDato = value === null;
  return (
    <div
      className={`fleet__kpi${kind && !sinDato ? ` fleet__kpi--${kind}` : ""}`}
      data-testid="fleet-kpi"
    >
      <span className="fleet__kpi-val">{sinDato ? "S/D" : value}</span>
      <span className="fleet__kpi-lbl">{label}</span>
    </div>
  );
}

/**
 * [T-2.60.a] La tarjeta del gabinete que la organización cree dado de baja y
 * sigue reportando.
 *
 * No se pinta como una tarjeta más del grid: es una CONTRADICCIÓN que exige
 * acción humana en una de las dos direcciones —desmontarlo de verdad o
 * restaurarlo—, y hasta entonces hay un edificio cuya supervisión nadie mira.
 */
function GhostCard({ cabinet }: { cabinet: FleetCabinet }) {
  const gw = cabinet.gateway;
  const cuando = gw.retired_at !== null && gw.retired_at !== undefined ? gw.retired_at : null;
  return (
    <li className="fleet-ghost">
      <div className="fleet-ghost__hd">
        <span className="fleet-ghost__site">{gw.site_name}</span>
        <span className="soc-mono fleet-ghost__serial">{gw.serial}</span>
      </div>
      <p className="fleet-ghost__why">
        Dado de baja{" "}
        {cuando !== null ? (
          <time dateTime={cuando}>el {new Date(cuando).toLocaleString("es-MX")}</time>
        ) : (
          "en fecha no registrada"
        )}
        {/* Sin actor la delación sigue valiendo: falta el quién, no el qué. */}
        {gw.retired_by ? <> por {gw.retired_by}</> : <> (sin actor en la bitácora)</>}, y aun así
        sigue enviando latidos.
      </p>
      <p className="fleet-ghost__act">
        Decida: <strong>restaurarlo</strong> si el edificio sigue protegido, o retirar el hardware
        si de verdad está fuera de servicio.
      </p>
    </li>
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
  const [filters, setFilters] = useState<FleetFilters>(DEFAULT_FILTERS);
  const [action, setAction] = useState<GatewayAction>({ kind: "none" });
  const health = useFleetHealth(fleet.cabinets.length > 0);
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
  // Los KPI cuentan el TOTAL a propósito: un contador que se moviera con el filtro
  // convertiría "3 SIN ENLACE" en una cifra distinta según lo tecleado.
  //
  // [T-2.59] …y no cuentan NADA mientras no haya respuesta. La tira se pinta
  // fuera del StateFrame, así que sin esta puerta un fallo de la API se leía
  // como una flota de cero gabinetes en perfecto estado (ver Kpi arriba).
  const sinDato = fleet.loading || fleet.error !== null;
  // [T-2.60.a] Los fantasmas se apartan ANTES de contar y de filtrar. Están dados
  // de baja, así que no son parte de la flota (no engordan "GABINETES" ni
  // "OPERATIVOS"), y meterlos en el grid resucitaría el bug que cerró T-2.35:
  // tarjetas de hardware retirado que la consola no podía quitar de la pantalla.
  const ghosts = fleet.cabinets.filter((c) => c.gateway.is_ghost === true);
  const activos = fleet.cabinets.filter((c) => c.gateway.is_ghost !== true);
  const counts = countStates(activos);
  const visible = applyFilters(activos, filters);

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
          <Kpi label="GABINETES" value={sinDato ? null : counts.total} />
          <Kpi label="OPERATIVOS" value={sinDato ? null : counts.ok} kind="ok" />
          <Kpi label="DEGRADADOS" value={sinDato ? null : counts.warn} kind="warn" />
          <Kpi label="SIN ENLACE" value={sinDato ? null : counts.crit} kind="crit" />
          {/* Solo aparece cuando hay alguno: un contador que está siempre a cero
              deja de leerse a las dos semanas, y este tiene que dar un salto. */}
          {!sinDato && ghosts.length > 0 && (
            <Kpi label="FANTASMAS" value={ghosts.length} kind="crit" />
          )}
        </div>
      </header>

      {/* [T-2.60.a] Antes del inventario y antes de los filtros: es lo que hay que
          resolver, no una fila más que se pueda filtrar hasta esconderla. */}
      {ghosts.length > 0 && (
        <section className="fleet-ghosts" data-testid="fleet-ghosts" role="alert">
          <header className="fleet-ghosts__hd">
            <span className="fleet-ghosts__badge">RETIRADO · PERO SIGUE REPORTANDO</span>
            <span className="soc-meta">
              {ghosts.length}{" "}
              {ghosts.length === 1
                ? "gabinete dado de baja y latiendo"
                : "gabinetes dados de baja y latiendo"}
            </span>
          </header>
          <ul className="fleet-ghosts__list">
            {ghosts.map((c) => (
              <GhostCard key={c.gateway.gateway_id} cabinet={c} />
            ))}
          </ul>
        </section>
      )}

      <FleetToolbar
        filters={filters}
        onChange={setFilters}
        includeRetired={canManage ? includeRetired : undefined}
        onIncludeRetired={canManage ? setIncludeRetired : undefined}
        shown={visible.length}
        total={fleet.cabinets.length}
      />

      <StateFrame
        label="FLOTA EDGE"
        loading={fleet.loading}
        error={fleet.error}
        onRetry={fleet.refetch}
        empty={visible.length === 0}
        emptyText={
          isFiltering(filters) && fleet.cabinets.length > 0
            ? "SIN RESULTADOS PARA EL FILTRO"
            : "SIN GABINETES REGISTRADOS EN EL TENANT"
        }
        staleSince={staleSince}
      >
        <div className="fleet__grid">
          {visible.map((c) => (
            <SiteCard
              key={c.gateway.gateway_id}
              cabinet={c}
              syncState={syncStates.get(c.gateway.gateway_id)}
              health={health.get(c.gateway.gateway_id)}
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
