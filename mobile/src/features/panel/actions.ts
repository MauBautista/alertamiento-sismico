// Fusión PURA de la traza REST con los frames live del topic incidents:
// mismo dato que la consola (el frame lo re-consulta el hub tras RLS); el
// replay de un frame ya visto se deduplica por action_id.
import type { IncidentActionFrame, IncidentActionOut } from "@takab/sdk";

export function mergeAction(
  actions: IncidentActionOut[],
  frame: IncidentActionFrame,
  incidentId: string,
): IncidentActionOut[] {
  if (String(frame.incident_id) !== incidentId) {
    return actions; // acción de otro incidente: no contamina la traza
  }
  if (actions.some((a) => a.action_id === frame.action_id)) {
    return actions; // replay/reconexión: idempotente
  }
  return [
    ...actions,
    {
      action_id: frame.action_id,
      incident_id: frame.incident_id,
      tenant_id: frame.tenant_id,
      ts: frame.ts,
      kind: frame.kind,
      actor: frame.actor,
      payload: frame.payload ?? {},
    },
  ];
}
