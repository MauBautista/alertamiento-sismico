// Banner del SIMULACRO (T-1.60 · reescrito en T-2.48 · al shell en T-6.01):
// rotulado NO-real, jamás confundible con la alerta.
//
// PRECEDENCIA: la decide la tabla de escena (`scene.ts`), no este componente.
// Con la ALERTA REAL mandando —una fuente que AUTORIZA: SASMEX o cuórum— el
// banner se degrada a un badge discreto (lo real siempre gana, también
// visualmente). Con un AVISO instrumental o una activación manual NO: una
// estación sola no manda sobre nada (T-2.32), y hasta T-6.01 este banner decía
// «LA ALERTA REAL DOMINA» con cualquier incidente crítico (U-28).
//
// [T-2.48] Dos correcciones de fondo que siguen en pie:
//
// 1. Los 4 estados obligatorios sobre `/drills/active` (regla de oro 7). Antes
//    ignoraba `loading` y, si la lectura fallaba con un simulacro VIVO, el
//    banner desaparecía EN SILENCIO. Un simulacro en curso que deja de
//    anunciarse es indistinguible de una alerta real para quien está dentro del
//    edificio: con último dato conocido se conserva y se rotula RETENIDO; sin
//    dato alguno se muestra el fallo con REINTENTAR. Nunca se calla.
// 2. Simulacro ARMADO: a T−15 min aparece el aviso persistente y a T−0 queda
//    precargado `EJECUTAR AHORA`. El disparo lo hace SIEMPRE una persona con la
//    sesión viva; aquí no hay temporizador que active nada (regla de oro 8).
//
// [T-6.01] Este componente ya no posee el dato: lo recibe de `SceneStrip`, que
// es el único que llama a `useActiveDrill` para PINTAR escena (lo vigila
// `src/sceneCensus.test.ts`). La tira de acciones —INICIAR SIMULACRO,
// HISTORIAL— se quedó en `/console` (`features/console/DrillControls.tsx`): en
// escena NORMAL no hay franja, sólo el botón donde ya estaba.

import { AlertTriangle, CalendarClock } from "lucide-react";
import { useMemo } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { utcClock } from "../../lib/time";
import { useNow } from "../../lib/useNow";
import { armedPhase, drillAckReport, nextArmedDrill } from "../console/drill";
import type { ActiveDrillData } from "../console/useActiveDrill";
import { DEGRADES_UNDER_ALERT, type Scene } from "./scene";

export default function DrillBanner({ data, scene }: { data: ActiveDrillData; scene: Scene }) {
  const canAct = useSessionStore((s) => s.me?.allowed_actions.drill_start === true);
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
  } = data;

  const armed = useMemo(() => nextArmedDrill(scheduled, now), [scheduled, now]);
  // "Conocido" = hay algo que el servidor ya nos dijo alguna vez. Con eso el
  // fallo degrada a RETENIDO; sin eso, el fallo ES el estado.
  const known = drill !== null || armed !== null;
  const frameError = readError !== null && !known ? readError : null;
  const staleSince = readError !== null && known ? updatedAt : null;
  // La excepción escrita, leída de la tabla: el simulacro es lo ÚNICO que se
  // degrada bajo la alerta real.
  const dominated = scene === "alert" && DEGRADES_UNDER_ALERT.drill;

  return (
    <StateFrame
      label="SIMULACRO"
      className="soc-drill__frame"
      loading={loading}
      error={frameError}
      onRetry={refetch}
      empty={!known}
      emptyText="SIN SIMULACRO EN CURSO"
      silentEmpty
      staleSince={staleSince}
    >
      {drill !== null ? (
        dominated ? (
          <span className="soc-pill soc-pill--warn" data-testid="drill-badge">
            SIMULACRO EN CURSO (LA ALERTA REAL DOMINA)
          </span>
        ) : (
          <RunningBanner
            endsAt={Date.parse(drill.started_at) + drill.duration_s * 1000}
            siteCount={drill.sites.length}
            ackLine={ackLine(drill)}
            canStop={canAct}
            pending={pending}
            onStop={() => stop(drill.drill_id)}
            fresca={staleSince === null}
          />
        )
      ) : armed !== null ? (
        <ArmedBanner
          scheduledAt={Date.parse(armed.scheduled_at as string)}
          siteCount={armed.sites.length}
          note={armed.note}
          due={armedPhase(armed, now) === "due"}
          canAct={canAct}
          pending={pending}
          onRun={() => start({ fromScheduled: armed.drill_id })}
          onCancel={() => cancel(armed.drill_id)}
        />
      ) : null}
      {/* El fallo de TERMINAR / EJECUTAR AHORA / CANCELAR, junto al botón que lo
          produjo: quien pulsa desde /fleet no tiene delante la tira de /console. */}
      {error !== null && (
        <span className="soc-user__error" role="alert">
          {error.toUpperCase()}
        </span>
      )}
    </StateFrame>
  );
}

/** `N/M ACUSADOS` + las causas que NO son "no acusó" (regla de oro 7). */
function ackLine(drill: Parameters<typeof drillAckReport>[0]): string {
  const r = drillAckReport(drill);
  const parts = [`${r.acked}/${r.commanded} ACUSADOS`];
  // [T-6.17] Un rechazo o un aborto NO son «no acusó»: el gabinete contestó, y
  // lo que contestó es justo lo que el operador tiene que leer en el banner.
  if (r.rejected > 0) parts.push(`${r.rejected} RECHAZADO(S)`);
  if (r.aborted > 0) parts.push(`${r.aborted} ABORTADO(S) POR ALERTA REAL`);
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
  fresca,
}: {
  endsAt: number;
  siteCount: number;
  ackLine: string;
  canStop: boolean;
  pending: boolean;
  onStop: () => void;
  /**
   * [T-6.10 · S3] Si lo que se anuncia es lo que el servidor afirma AHORA.
   *
   * El simulacro y la alerta real comparten forma de banner: se distinguen por
   * color y por rótulo, y esos dos siguen siendo los que mandan. La trama que
   * deriva añade un tercer canal que no repite a ninguno de los dos —dice si la
   * lectura sigue viva— y se congela con ella. Un banner que sigue corriendo
   * sobre un dato retenido afirmaría que el simulacro sigue sonando cuando lo
   * único cierto es que dejamos de saberlo (regla de oro 7).
   */
  fresca: boolean;
}) {
  return (
    <div
      className={`soc-drill soc-drill--on${fresca ? " soc-drill--fresca" : ""}`}
      role="status"
      data-testid="drill-banner"
    >
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
