// Banner del SIMULACRO (T-1.60 · reescrito en T-2.48): rotulado NO-real, jamás
// confundible con la alerta.
//
// PRECEDENCIA: con un incidente vivo el frame real domina — este banner se
// degrada a un badge discreto (lo real siempre gana, también visualmente).
//
// [T-2.48] Dos correcciones de fondo:
//
// 1. Los 4 estados obligatorios sobre `/drills/active` (regla de oro 7). Antes
//    ignoraba `loading` y, si la lectura fallaba con un simulacro VIVO, el
//    banner desaparecía EN SILENCIO. Un simulacro en curso que deja de
//    anunciarse es indistinguible de una alerta real para quien está dentro del
//    edificio: ahora, con último dato conocido se conserva y se rotula RETENIDO;
//    sin dato alguno se muestra el fallo con REINTENTAR. Nunca se calla.
// 2. Simulacro ARMADO: a T−15 min aparece el aviso persistente y a T−0 queda
//    precargado `EJECUTAR AHORA`. El disparo lo hace SIEMPRE una persona con la
//    sesión viva; aquí no hay temporizador que active nada (regla de oro 8).

import { AlertTriangle, CalendarClock } from "lucide-react";
import { useMemo, useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { utcClock } from "../../lib/time";
import { useNow } from "../../lib/useNow";
import { armedPhase, drillAckReport, nextArmedDrill } from "./drill";
import DrillHistory from "./DrillHistory";
import DrillModal from "./DrillModal";
import { useActiveDrill } from "./useActiveDrill";

export default function DrillBanner({ hasLiveIncident }: { hasLiveIncident: boolean }) {
  const canStart = useSessionStore((s) => s.me?.allowed_actions.drill_start === true);
  const now = useNow(1000);
  const {
    drill,
    scheduled,
    loading,
    readError,
    updatedAt,
    refetch,
    start,
    stop,
    cancel,
    pending,
    error,
  } = useActiveDrill();
  const [modalOpen, setModalOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const armed = useMemo(() => nextArmedDrill(scheduled ?? [], now), [scheduled, now]);
  // "Conocido" = hay algo que el servidor ya nos dijo alguna vez. Con eso el
  // fallo degrada a RETENIDO; sin eso, el fallo ES el estado.
  const known = drill !== null || armed !== null;
  const frameError = readError !== null && !known ? readError : null;
  const staleSince = readError !== null && known ? updatedAt : null;

  return (
    <div className="soc-drill-bar">
      <StateFrame
        label="SIMULACRO"
        className="soc-drill__frame"
        loading={loading}
        error={frameError}
        onRetry={refetch}
        empty={!known}
        emptyText="SIN SIMULACRO EN CURSO"
        staleSince={staleSince}
      >
        {drill !== null ? (
          hasLiveIncident ? (
            <span className="soc-pill soc-pill--warn" data-testid="drill-badge">
              SIMULACRO EN CURSO (LA ALERTA REAL DOMINA)
            </span>
          ) : (
            <RunningBanner
              endsAt={Date.parse(drill.started_at) + drill.duration_s * 1000}
              siteCount={drill.sites.length}
              ackLine={ackLine(drill)}
              canStop={canStart}
              pending={pending}
              onStop={() => stop(drill.drill_id)}
            />
          )
        ) : armed !== null ? (
          <ArmedBanner
            scheduledAt={Date.parse(armed.scheduled_at as string)}
            siteCount={armed.sites.length}
            note={armed.note}
            due={armedPhase(armed, now) === "due"}
            canAct={canStart}
            pending={pending}
            onRun={() => start({ fromScheduled: armed.drill_id })}
            onCancel={() => cancel(armed.drill_id)}
          />
        ) : null}
      </StateFrame>

      {/* `drill-idle` lo mide el e2e de T-1.62 (la tira no puede pasar de 60 px). */}
      <div className="soc-drill soc-drill--idle soc-drill__actions" data-testid="drill-idle">
        {error !== null && (
          <span className="soc-user__error" role="alert">
            {error.toUpperCase()}
          </span>
        )}
        {canStart && drill === null && (
          <button
            type="button"
            className="soc-btn soc-btn--ghost"
            disabled={pending}
            onClick={() => setModalOpen(true)}
            title="Banner NO-real + voceo en los gabinetes elegidos; cero relés"
          >
            INICIAR SIMULACRO
          </button>
        )}
        <button
          type="button"
          className="soc-btn soc-btn--ghost"
          onClick={() => setHistoryOpen(true)}
        >
          HISTORIAL
        </button>
      </div>

      {modalOpen && (
        <DrillModal
          pending={pending}
          error={error}
          onSubmit={(input) => {
            start(input);
            setModalOpen(false);
          }}
          onClose={() => setModalOpen(false)}
        />
      )}
      {historyOpen && <DrillHistory onClose={() => setHistoryOpen(false)} />}
    </div>
  );
}

/** `N/M ACUSADOS` + las causas que NO son "no acusó" (regla de oro 7). */
function ackLine(drill: Parameters<typeof drillAckReport>[0]): string {
  const r = drillAckReport(drill);
  const parts = [`${r.acked}/${r.commanded} ACUSADOS`];
  if (r.noGateway > 0) parts.push(`${r.noGateway} SIN GABINETE COMANDABLE`);
  if (r.notSent > 0) parts.push(`${r.notSent} SIN COMANDO EMITIDO`);
  return parts.join(" · ");
}

function RunningBanner({
  endsAt,
  siteCount,
  ackLine: ack,
  canStop,
  pending,
  onStop,
}: {
  endsAt: number;
  siteCount: number;
  ackLine: string;
  canStop: boolean;
  pending: boolean;
  onStop: () => void;
}) {
  return (
    <div className="soc-drill soc-drill--on" role="status" data-testid="drill-banner">
      <AlertTriangle size={16} aria-hidden />
      <span>
        🔶 SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL · {siteCount} SITIO(S) · {ack} · TERMINA{" "}
        {utcClock(endsAt)} UTC
      </span>
      {canStop && (
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={pending}
          onClick={onStop}
        >
          TERMINAR
        </button>
      )}
    </div>
  );
}

function ArmedBanner({
  scheduledAt,
  siteCount,
  note,
  due,
  canAct,
  pending,
  onRun,
  onCancel,
}: {
  scheduledAt: number;
  siteCount: number;
  note: string | null;
  due: boolean;
  canAct: boolean;
  pending: boolean;
  onRun: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="soc-drill soc-drill--armed" role="status" data-testid="drill-armed">
      <CalendarClock size={16} aria-hidden />
      <span>
        SIMULACRO ARMADO · PROGRAMADO PARA {utcClock(scheduledAt)} UTC · {siteCount} SITIO(S)
        {note ? ` · ${note}` : ""}
      </span>
      {canAct && (
        <>
          <button
            type="button"
            className="soc-btn soc-btn--primary"
            /* Antes de la hora el botón está a la vista pero inerte: el aviso es
               la información, el disparo es el acto. Se habilita a T−0 y sigue
               siendo un clic humano — nunca un temporizador. */
            disabled={!due || pending}
            title={
              due
                ? "Emite el simulacro AHORA a los sitios programados"
                : "Se habilita a la hora programada"
            }
            onClick={onRun}
          >
            EJECUTAR AHORA
          </button>
          <button
            type="button"
            className="soc-btn soc-btn--secondary"
            disabled={pending}
            onClick={onCancel}
          >
            CANCELAR
          </button>
        </>
      )}
    </div>
  );
}
