// Bitácora del incidente (T-2.40).
//
// `incident_actions` es evidencia inmutable (blueprint §9) y la pantalla se limitaba a
// contarla: "12 ACCIONES REGISTRADAS". Doce acciones son doce decisiones —quién acusó,
// cuándo sonó la sirena, quién pidió el dictamen— y contarlas sin mostrarlas convierte
// el registro que existe precisamente para reconstruir lo ocurrido en un número.
//
// Orden cronológico del SERVIDOR: no se reordena en cliente. Una bitácora que el
// cliente reordena deja de ser una bitácora.

import {
  ACTION_STATE,
  ACTUATOR_CHANNELS,
  CHANNEL_LABEL,
  INCIDENT_ACTION_KINDS,
  isSimulatedAction,
} from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";

/**
 * [T-2.127] Rótulos de los kinds de ACTUADOR, derivados de `ACTUATOR_CHANNELS`
 * — el mismo registro del que el checklist BMS saca `ACTION_STATE` y
 * `CHANNEL_LABEL` (`shared/sdk-ts/src/bms.ts`, T-2.119).
 *
 * Aquí había dos entradas a mano —`siren_on` y `siren_off`— y NADA MÁS, así que
 * los otros ocho kinds de actuador caían en el fallback crudo: la bitácora que
 * un perito lee para reconstruir lo ocurrido decía «GAS_CLOSED». Escribir los
 * ocho que faltaban habría sido repetir el error de `T-1.50`, que es el que
 * `T-2.119` acaba de pagar: dos listas de canales, una de ellas con tres
 * nombres que ningún productor escribe jamás, y gas/ascensores/puertas meses en
 * el fallback verde.
 *
 * El rótulo es `«CANAL» + «lo que ese VERBO afirma»`: `gas_closed` ⇒ «VÁLVULAS
 * DE GAS CERRADAS». Ni el canal ni el vocabulario se escriben aquí; los dos
 * salen del registro, y `ACTION_STATE[kind].state` ya resuelve si el verbo
 * protege o suelta (incluidos los `legacyKinds`), así que tampoco se duplica esa
 * decisión.
 *
 * OJO A LA DIFERENCIA CON EL CHECKLIST, que es lo que esta función NO hace: el
 * checklist prefiere `payload.channel_state` sobre el verbo porque una fila suya
 * afirma «cómo está el canal AHORA». Una línea de la bitácora afirma otra cosa
 * —«a esta hora se ejecutó esta orden»— y es cronológica y append-only. Dejar
 * que el censo del relé reescribiera el rótulo convertiría la evidencia en un
 * estado con marca de tiempo.
 */
function actuatorKindLabels(): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const spec of Object.values(ACTUATOR_CHANNELS)) {
    for (const kind of [...Object.keys(spec.kinds), ...Object.keys(spec.legacyKinds)]) {
      labels[kind] = `${CHANNEL_LABEL[kind]} ${ACTION_STATE[kind].state}`;
    }
  }
  return labels;
}

/**
 * [T-2.144] Y LOS QUE NO SON DE ACTUADOR, DEL MISMO REGISTRO.
 *
 * Aquí vivía la tercera lista escrita a mano (`KIND_LABEL`), con nueve entradas.
 * Le faltaban cinco verbos que la API escribe de verdad —`fail_open`,
 * `in_review`, `close`, `dictamen_signed` y `notify_delivered`— y le sobraban
 * dos que nadie escribe nunca (ver la nota de abajo). Ahora el verbo sale de
 * `INCIDENT_ACTION_KINDS.logLabel`, el mismo registro del que el checklist saca
 * la fila: un kind nuevo entra en las dos superficies o en ninguna.
 *
 * Sigue siendo un texto DISTINTO del de la fila del checklist, y esa es la razón
 * de que `logLabel` exista: «PASE DE LISTA · CERRADO» describe un estado;
 * «PASE DE LISTA CERRADO» describe un hecho fechado. La bitácora es lo segundo.
 */
function kindLabels(): Record<string, string> {
  return {
    ...actuatorKindLabels(),
    ...Object.fromEntries(Object.entries(INCIDENT_ACTION_KINDS).map(([k, s]) => [k, s.logLabel])),
  };
}

/**
 * La derivación es PEREZOSA, y no es una micro-optimización: hacerla al cargar
 * el módulo tumbaba dos suites enteras.
 *
 * `useFleet.test.tsx` y `useSiteRelays.test.tsx` sustituyen `@takab/sdk`
 * COMPLETO (`vi.mock("@takab/sdk", () => mocks)`, sin `importOriginal`), y
 * alcanzan este fichero de rebote por `TriageDetail` → `renderRoutes`. Leer
 * `ACTUATOR_CHANNELS` en el cuerpo del módulo reventaba la carga —«No
 * "ACTUATOR_CHANNELS" export is defined on the "@takab/sdk" mock»— y las dos
 * suites pasaban de verdes a «0 test», sin que ninguna asserción hablara de
 * rótulos. `isSimulatedAction` ya se importaba aquí y nunca dio guerra porque
 * sólo se INVOCA dentro de `kindLabel`; esto se comporta igual.
 */
let KIND_LABEL: Record<string, string> | null = null;

function labelDelRegistro(kind: string): string | undefined {
  KIND_LABEL ??= kindLabels();
  return KIND_LABEL[kind];
}

/*
 * [T-2.144] `drill_start` Y `drill_stop` SE RETIRARON DE ESTE MAPA, y la razón
 * va escrita para que nadie los devuelva "por si acaso" — es el mismo trato que
 * `T-2.133` le dio a `siren_test`, y por el mismo motivo.
 *
 * Estaban rotulados aquí («SIMULACRO INICIADO» / «SIMULACRO TERMINADO») y
 * **ningún productor los escribe jamás en `incident_actions`**: son valores de
 * `commands.action` —comandos FIRMADOS al gabinete por el canal lógico
 * `system`— y su acuse lo procesa `handle_command_ack`, que toca `commands` y
 * `audit_log` y jamás esta tabla. El propio `api/src/takab_api/queries/mobile.py`
 * lo dice al filtrar la alarma del inmueble: «`drill_start`/`drill_stop` con
 * `channel='system'`, así que ninguno entra».
 *
 * No se conservan como legado, y la diferencia con `gas_valve_close`,
 * `elevator_recall` y `door_release` importa: aquéllos son nombres de CANAL y el
 * registro tiene que poder rotular una fila antigua de un canal. Éstos no
 * pertenecen a ninguna fila de `incident_actions` que exista, ni haya existido:
 * conservarlos no protege evidencia, protege una hipótesis. Lo que un simulacro
 * SÍ deja en la tabla son los kinds de actuador de los relés que movió, y ésos
 * ya se rotulan.
 *
 * La guardia que impide que vuelvan es el censo inverso de
 * `web/src/features/console/incidentActionKinds.test.ts`: todo kind del registro
 * tiene que tener un productor resuelto.
 */

export interface TimelineAction {
  action_id: string;
  ts: string;
  kind: string;
  actor: string;
  /** [T-2.75] Evidencia del desenlace; lleva la bandera `simulated`. */
  payload?: Record<string, unknown>;
}

/**
 * Verbo de la acción. La bandera `simulated` del payload manda sobre el mapa:
 * un rótulo que enumera se queda ciego ante el canal siguiente, y ese canal
 * caería en el fallback crudo sin decir que nadie lo recibió.
 */
export function kindLabel(action: TimelineAction): string {
  // [T-2.144] El fallback tampoco calla aquí. La bitácora no tiene color, así
  // que no podía mentir en verde — pero sí podía hacer pasar por un verbo de
  // TAKAB el nombre en bruto de una constante. «SIN CLASIFICAR» es lo único
  // cierto que la consola sabe de una fila que su registro no reconoce, y es lo
  // que un perito necesita leer antes de darla por interpretada.
  const base = labelDelRegistro(action.kind) ?? `${action.kind.toUpperCase()} · SIN CLASIFICAR`;
  if (isSimulatedAction({ payload: action.payload ?? {} }) && !base.includes("SIMULAD")) {
    return `${base} · SIMULADA, NADIE LA RECIBIÓ`;
  }
  return base;
}

/** ¿Esta línea documenta algo que NO llegó a nadie? (marca visual propia) */
function isUndelivered(action: TimelineAction): boolean {
  return (
    isSimulatedAction({ payload: action.payload ?? {} }) ||
    action.kind === "notify_failed" ||
    // [T-2.133] La marca no dice «hubo una avería», dice «esto no llegó a
    // nadie». Un sitio sin teléfonos registrados es exactamente ese caso.
    action.kind === "notify_no_recipients"
  );
}

export interface IncidentTimelineProps {
  actions: {
    data: TimelineAction[] | undefined;
    loading: boolean;
    error: string | null;
    /**
     * [T-2.82.a] Epoch ms de la última respuesta buena cuando ya es vieja; el
     * `Resource<T>` de `useIncidentDetail` la trae ya resuelta. Se declara en el
     * mismo objeto que el dato a propósito: una bitácora y su edad no se pueden
     * separar sin que alguien acabe pintando la una sin la otra.
     */
    staleSince: number | null;
  };
  onRetry: () => void;
}

/** Actor legible: `user:<uuid>` es ruido; `system:*` sí dice algo. */
export function actorLabel(actor: string): string {
  if (actor.startsWith("user:")) {
    return `OPERADOR ${actor.slice(5, 13)}`;
  }
  if (actor.startsWith("system:")) {
    return actor.slice(7).toUpperCase();
  }
  return actor.toUpperCase();
}

export default function IncidentTimeline({ actions, onRetry }: IncidentTimelineProps) {
  return (
    <div className="soc-card timeline" data-testid="incident-timeline">
      <div className="soc-card__hd">
        <div>
          <div>Bitácora del incidente</div>
          <div className="soc-card__sub">APPEND-ONLY · SIN PODA POR RETENCIÓN</div>
        </div>
        {/* `?? 0` habría dicho "0 ACCIONES REGISTRADAS" con la consulta fallida:
            afirmar que no pasó nada cuando lo que ocurre es que no se sabe es
            exactamente lo que prohíbe la regla de oro 7. */}
        <span className="soc-bacnet">
          ⬢ {actions.data === undefined ? "S/D" : actions.data.length} ACCIONES REGISTRADAS
        </span>
      </div>
      <StateFrame
        label="BITÁCORA"
        loading={actions.loading}
        error={actions.error}
        onRetry={onRetry}
        empty={actions.data?.length === 0}
        emptyText="SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE"
        // [T-2.82.a] Esto es lo que se lee para reconstruir lo ocurrido antes de
        // firmar. Una bitácora a la que le faltan las últimas acciones porque el
        // enlace se cayó, pintada como completa, es una reconstrucción falsa de
        // un incidente; y con la lista vacía, `stale` gana a `empty` y la
        // ausencia sale FECHADA en vez de afirmada (T-2.79.d).
        staleSince={actions.staleSince}
      >
        <ol className="timeline__list">
          {(actions.data ?? []).map((a) => (
            <li key={a.action_id} className="timeline__item">
              <span className="timeline__ts soc-mono">{utcStamp(Date.parse(a.ts))}</span>
              <span
                className={`timeline__kind${isUndelivered(a) ? " timeline__kind--undelivered" : ""}`}
              >
                {kindLabel(a)}
              </span>
              <span className="timeline__actor soc-mono">{actorLabel(a.actor)}</span>
            </li>
          ))}
        </ol>
      </StateFrame>
    </div>
  );
}
