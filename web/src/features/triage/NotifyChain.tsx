// Quién recibió la alerta, y cuánto tardó en llegarle (T-5.15).
//
// LA DISTINCIÓN QUE GOBIERNA ESTE ARCHIVO, y por la que existe la `0040`:
// `sent` significa «el proveedor lo aceptó» y `simulated` «no había proveedor
// configurado, no lo recibió nadie». **Ninguno de los dos afirma que un humano
// lo tenga en la mano**; eso solo lo afirma `delivered_at`. Pintarlos con el
// mismo verde sería la misma familia de defecto que el checklist BMS que
// mostraba la última ORDEN en lugar del estado del relé.
//
// Y el destinatario llega YA enmascarado del servidor (`notify/destino.py`):
// aquí no se enmascara nada, porque un enmascarado en el cliente significa que
// el dato en claro viajó.

import type { NotificationJobOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import { latenciaLegible, utcStamp } from "../../lib/time";
import { useNotifyChain } from "./useNotifyChain";

/** Qué le pasó a este envío, en una palabra que no miente. */
export function desenlace(job: NotificationJobOut): { label: string; tone: string } {
  if (job.delivered) return { label: "ENTREGADO", tone: "ok" };
  switch (job.status) {
    case "sent":
      // El proveedor lo aceptó y NO ha confirmado la entrega. No es un fallo, y
      // tampoco es un éxito: es lo único que se sabe.
      return { label: "ACEPTADO POR EL PROVEEDOR", tone: "wait" };
    case "pending":
      return { label: "SIN ENVIAR TODAVÍA", tone: "wait" };
    case "failed":
      return { label: "FALLÓ", tone: "bad" };
    case "simulated":
      return { label: "SIMULADO · NO LO RECIBIÓ NADIE", tone: "bad" };
    case "blocked_demo":
      return { label: "INHIBIDO POR MODO DEMOSTRACIÓN", tone: "bad" };
    case "skipped":
      return { label: "OMITIDO · LA CASCADA YA ESTABA SATISFECHA", tone: "muted" };
    default:
      // El estado que alguien añada mañana NO cae en «entregado»: se declara.
      return { label: `${job.status.toUpperCase()} · SIN CLASIFICAR`, tone: "muted" };
  }
}

/** El destinatario tal como el servidor lo dejó decir. */
export function destinatario(job: NotificationJobOut): string {
  const r = job.recipient;
  if (r.unrecognised) {
    // Un hueco se leería como «no había destinatario», que es otra cosa.
    return "DESTINATARIO NO RECONOCIDO";
  }
  return r.count !== null && r.count > 1 ? `${r.hint} (${r.count})` : r.hint;
}

export default function NotifyChain({ incidentId }: { incidentId: string }) {
  const chain = useNotifyChain(incidentId);
  const hay = chain.items.length > 0;

  return (
    <div className="soc-card" data-testid="notify-chain">
      <div className="soc-card__hd">
        <div>
          <div>Cadena de aviso</div>
          <div className="soc-card__sub">QUIÉN LO RECIBIÓ · CUÁNTO TARDÓ</div>
        </div>
      </div>
      <StateFrame
        label="CADENA DE AVISO"
        loading={chain.loading}
        error={chain.readError && !hay ? "no se pudo leer la cadena de aviso" : null}
        onRetry={chain.refetch}
        empty={!chain.loading && !chain.readError && !hay}
        emptyText="NO SE ENCOLÓ NINGÚN AVISO PARA ESTE INCIDENTE"
        staleSince={chain.staleSince}
      >
        {/* EL RECUENTO VA DENTRO DEL MARCO, y no en la cabecera de la tarjeta
            como la bitácora de al lado. Lo cazó `serverDataCensus` y tiene toda
            la razón: es el defecto de `T-2.59` —la tira de KPI de `/fleet`
            pintando «0 SIN ENLACE» en verde con la API caída— y la única
            garantía que no depende de que yo me acuerde de escribir el `S/D` es
            que el marcado esté donde `StateFrame` decide si se pinta. Con la
            consulta fallida esto no existe; lo que se ve es el error. */}
        <p className="notifychain__count soc-bacnet">
          ⬢ {chain.deliveredCount} DE {chain.items.length} ENTREGADOS
        </p>
        <ul className="notifychain__list">
          {chain.items.map((j) => {
            const d = desenlace(j);
            return (
              <li key={j.job_id} className="notifychain__item" data-tone={d.tone}>
                <span className="notifychain__ch soc-mono">
                  {j.channel.toUpperCase()} · {j.mode === "cascade" ? "CASCADA" : "PARALELO"}
                </span>
                <span className="notifychain__to soc-mono" data-testid={`chain-to-${j.job_id}`}>
                  {destinatario(j)}
                </span>
                <span className={`notifychain__st is-${d.tone}`}>{d.label}</span>
                {/* Los dos tramos NO se suman: el segundo no depende de TAKAB,
                    y presentarlos juntos lo parecería. */}
                <span className="notifychain__lat soc-mono" data-testid={`chain-lat-${j.job_id}`}>
                  {j.dispatch_latency_s === null
                    ? "SALIDA S/D"
                    : `SALIÓ ${latenciaLegible(j.dispatch_latency_s)}`}
                  {j.delivery_latency_s !== null &&
                    ` · LLEGÓ ${latenciaLegible(j.delivery_latency_s)} DESPUÉS`}
                </span>
                {j.sent_at !== null && (
                  <span className="notifychain__ts soc-mono">
                    {utcStamp(Date.parse(j.sent_at))} UTC
                  </span>
                )}
                {j.deadline_met === false && (
                  <span className="notifychain__sla">FUERA DE PLAZO</span>
                )}
                {j.error !== null && <span className="notifychain__err">{j.error}</span>}
              </li>
            );
          })}
        </ul>
      </StateFrame>
    </div>
  );
}
