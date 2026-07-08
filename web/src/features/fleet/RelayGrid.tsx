import type { FleetRelay } from "./useFleet";

/**
 * Actuadores del gabinete desde la config activa. armed=true ⇒ ARMADO (enlace
 * vivo, supervisor fail-fast); armed=null ⇒ S/D. No existe "FALLA": no hay
 * fuente de dato para afirmarla y fingirla sería peor que no mostrarla.
 */
export default function RelayGrid({ relays }: { relays: FleetRelay[] }) {
  return (
    <div className="fleet-relays">
      {relays.map((relay, i) => (
        <div
          key={relay.key}
          className={`fleet-relay fleet-relay--${relay.armed ? "ok" : "warn"}`}
          title={`cableado ${relay.wiring}`}
        >
          <span className="fleet-relay__id">R{i + 1}</span>
          <span className="fleet-relay__label">{relay.label}</span>
          <span className="fleet-relay__state">{relay.armed ? "ARMADO" : "S/D"}</span>
        </div>
      ))}
    </div>
  );
}
