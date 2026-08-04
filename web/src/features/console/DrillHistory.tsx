// Registro de simulacros con acuse POR SITIO (T-2.48).
//
// Es la evidencia de cumplimiento que se le entrega a Protección Civil, así que
// manda la honestidad sobre la síntesis: el resumen `N/M ACUSADOS` cuenta SOLO
// los sitios a los que se les emitió el comando, y las causas de ausencia se
// listan aparte. Meter en el mismo saco a un edificio que ignoró el simulacro y
// a uno que no tiene gabinete comandable convertiría un problema de inventario
// en una acusación de incumplimiento.

import { useState } from "react";

import type { DrillOut } from "@takab/sdk";

import Modal from "../../components/Modal";
import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import { ackLabel, drillAckReport, drillSiteAck, isPendingSchedule } from "./drill";
import { useDrills, type DrillKind } from "./useDrills";

const KIND_TABS: readonly { value: DrillKind; label: string }[] = [
  { value: "all", label: "TODOS" },
  { value: "executed", label: "EJECUTADOS" },
  { value: "scheduled", label: "AGENDA" },
];

function drillStateLabel(drill: DrillOut): string {
  if (drill.scheduled_at === null) return drill.active ? "EN CURSO" : "EJECUTADO";
  if (drill.stopped_at === null) return "PROGRAMADO";
  return drill.stop_reason === "executed" ? "AGENDA EJECUTADA" : "CANCELADO";
}

/** `N/M ACUSADOS` + las causas que NO son "no acusó". */
function ackSummary(drill: DrillOut): string {
  const r = drillAckReport(drill);
  const parts = [`${r.acked}/${r.commanded} ACUSADOS`];
  if (r.pending > 0) parts.push(`${r.pending} SIN ACUSE`);
  if (r.rejected > 0) parts.push(`${r.rejected} RECHAZADO(S)`);
  if (r.noGateway > 0) parts.push(`${r.noGateway} SIN GABINETE COMANDABLE`);
  if (r.notSent > 0) parts.push(`${r.notSent} SIN COMANDO EMITIDO`);
  return parts.join(" · ");
}

export default function DrillHistory({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<DrillKind>("all");
  const [open, setOpen] = useState<string | null>(null);
  const history = useDrills(kind);

  const hasItems = history.items.length > 0;
  return (
    <Modal title="REGISTRO DE SIMULACROS" onClose={onClose}>
      <div className="soc-drillhist" data-testid="drill-history">
        <div className="soc-drillhist__tabs">
          {KIND_TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              className={`soc-btn soc-btn--ghost${kind === t.value ? " is-on" : ""}`}
              aria-pressed={kind === t.value}
              onClick={() => setKind(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <StateFrame
          label="SIMULACROS"
          loading={history.loading}
          // Con páginas ya cargadas un fallo no borra la evidencia: se conserva
          // y se declara RETENIDA (regla de oro 7).
          error={history.error !== null && !hasItems ? history.error : null}
          onRetry={history.refetch}
          empty={!history.loading && history.error === null && !hasItems}
          emptyText="SIN SIMULACROS REGISTRADOS"
          staleSince={history.error !== null && hasItems ? history.updatedAt : null}
        >
          <ul className="soc-drillhist__list">
            {history.items.map((d) => {
              const when = d.scheduled_at ?? d.started_at;
              const pendingSchedule = isPendingSchedule(d);
              return (
                <li
                  key={d.drill_id}
                  className="soc-drillhist__row"
                  data-testid={`drill-row-${d.drill_id}`}
                >
                  <div className="soc-drillhist__hd">
                    <span className="soc-pill">{drillStateLabel(d)}</span>
                    <span className="soc-mono">{utcStamp(Date.parse(when))} UTC</span>
                    <span className="soc-meta">{Math.round(d.duration_s / 60)} MIN</span>
                    {d.note !== null && <span className="soc-meta">{d.note}</span>}
                  </div>
                  <p className="soc-drillhist__ack">
                    {pendingSchedule
                      ? `${d.sites.length} SITIO(S) APUNTADO(S) · AÚN NO EJECUTADO`
                      : ackSummary(d)}
                  </p>
                  <button
                    type="button"
                    className="soc-btn soc-btn--ghost"
                    aria-expanded={open === d.drill_id}
                    onClick={() => setOpen((cur) => (cur === d.drill_id ? null : d.drill_id))}
                  >
                    DETALLE · {d.sites.length} SITIO(S)
                  </button>
                  {open === d.drill_id && (
                    <ul className="soc-drillhist__sites" data-testid={`drill-sites-${d.drill_id}`}>
                      {d.sites.map((s) => {
                        const state = drillSiteAck(s, d);
                        return (
                          <li key={s.site_id} data-ack={state}>
                            <span>{s.site_name ?? `SITIO ${s.site_id.slice(0, 8)}`}</span>
                            <span className={`soc-drillhist__ackpill is-${state}`}>
                              {ackLabel(state)}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
          {history.error !== null && hasItems && (
            <p className="soc-user__error" role="alert">
              {history.error.toUpperCase()}
            </p>
          )}
          {history.hasMore && (
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              disabled={history.loadingMore}
              onClick={history.loadMore}
            >
              CARGAR MÁS
            </button>
          )}
        </StateFrame>
      </div>
    </Modal>
  );
}
