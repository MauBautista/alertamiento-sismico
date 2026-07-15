import { Check } from "lucide-react";

import StateFrame from "../../components/StateFrame";
import type { QuorumView } from "./model";

function offset(deltaS: number | null): string {
  if (deltaS === null) {
    return "S/D";
  }
  return `${deltaS >= 0 ? "+" : ""}${deltaS.toFixed(2)}s`;
}

export interface QuorumNodesProps {
  view: QuorumView;
  /** Estado del evento asociado. `absent` = el incidente no referencia evento. */
  eventState: "absent" | "loading" | "error" | "ready";
  eventError?: string | null;
  /** Hecho del servidor: el motor formó el evento por quórum. NUNCA se deriva aquí. */
  corroborated: boolean;
  /** `config.quorum.min_nodes` ACTUAL. Contexto, no veredicto del evento pasado. */
  minNodes: number | null;
  onRetry?: () => void;
}

/**
 * Regla de quórum con offsets por nodo. `delta_s` lo calcula el motor de la nube
 * (`incident/quorum.py`) contra el ancla (la detección más temprana) y aquí se
 * pinta VERBATIM — el mockup fabricaba `+0.18s`, `+0.39s`… y códigos de estación
 * (`CHL-A`, `PUE-01`) que ninguna API resuelve: `quorum_votes` sólo trae el
 * `sensor_id`, así que el nodo se rotula con su uuid corto.
 *
 * El veredicto "CUÓRUM CUMPLIDO" es un HECHO del servidor (`source='local_quorum'`,
 * que el motor sólo escribe al alcanzarlo). No se recalcula contra el `min_nodes`
 * del rule_set activo: el motor prefiere el scope de SITIO y usa la versión vigente
 * en su momento, así que esa comparación podría contradecir al propio motor. El
 * `min_nodes` actual se muestra sólo como contexto de configuración.
 *
 * La ventana de asociación es consciente de la distancia (|Δt| ≤ dist/v_P + margen,
 * blueprint §4.5): un offset grande NO implica que el nodo se descarte — eso lo dice
 * `counted`, que también viene del servidor.
 */
export default function QuorumNodes({
  view,
  eventState,
  eventError,
  corroborated,
  minNodes,
  onRetry,
}: QuorumNodesProps) {
  return (
    <div className="soc-card">
      <div className="soc-card__hd">
        <div>
          <div>Regla de quórum · Offsets por nodo</div>
          <div className="soc-card__sub">
            CORROBORACIÓN MULTI-SENSOR · VENTANA CONSCIENTE DE LA DISTANCIA
            {minNodes !== null && ` · MÍNIMO CONFIGURADO HOY: ${minNodes}`}
          </div>
        </div>
        {eventState === "ready" && corroborated && (
          <span className="soc-pill soc-pill--ok" style={{ fontSize: 9 }}>
            <Check size={11} aria-hidden /> CONFIRMADO · {view.countedNodes} estaciones
          </span>
        )}
        {eventState === "ready" && !corroborated && (
          <span className="soc-pill soc-pill--warn" style={{ fontSize: 9 }}>
            SIN CORROBORAR POR QUÓRUM
          </span>
        )}
      </div>

      {eventState === "absent" ? (
        <div className="soc-stateframe soc-stateframe--status" data-state="empty">
          <span>INCIDENTE SIN EVENTO SÍSMICO ASOCIADO</span>
        </div>
      ) : (
        <StateFrame
          label="QUÓRUM"
          loading={eventState === "loading"}
          error={eventState === "error" ? (eventError ?? "no se pudo cargar el evento") : null}
          onRetry={onRetry}
          empty={eventState === "ready" && view.nodes.length === 0}
          emptyText="SIN VOTOS DE QUÓRUM PARA ESTE EVENTO"
          staleSince={null}
        >
          <div className="triage-nodes">
            {view.nodes.map((n) => (
              <div
                key={n.sensorId}
                className={`triage-node ${n.counted ? "triage-node--active" : "triage-node--idle"}`}
                data-testid="quorum-node"
              >
                <span className="soc-dot" />
                <span className="triage-node__id">
                  {n.label}
                  {n.isAnchor && " · ANCLA"}
                </span>
                <span className="triage-node__t soc-mono">{offset(n.deltaS)}</span>
              </div>
            ))}
          </div>
        </StateFrame>
      )}
    </div>
  );
}
