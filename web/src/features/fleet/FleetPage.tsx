import StateFrame from "../../components/StateFrame";
import { useNow } from "../../lib/useNow";
import FleetAdmin from "./FleetAdmin";
import SiteCard from "./SiteCard";
import { FLEET_STALE_MS, useFleet } from "./useFleet";
import type { FleetCabinet } from "./useFleet";

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
export default function FleetPage() {
  const fleet = useFleet();
  const now = useNow(5000);
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
            <SiteCard key={c.gateway.gateway_id} cabinet={c} />
          ))}
        </div>
      </StateFrame>

      {/* FUERA del StateFrame a propósito: un tenant sin gabinetes cae en el estado
          `empty`, y ahí es precisamente cuando hace falta poder crear la primera
          estación. Enterrar el alta dentro del marco la haría inalcanzable. */}
      <FleetAdmin />
    </section>
  );
}
