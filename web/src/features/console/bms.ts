// [T-2.08] La agrupación BMS vive en @takab/sdk (compartida con el dashboard
// táctico móvil — criterio 2.1: cero transformaciones divergentes). Re-export
// para que los consumidores de la consola no cambien de import.
//
// [T-2.119] `channelEvidence` y `ACTUATOR_CHANNELS` salen por aquí por el mismo
// motivo: el estado de gas, ascensores y puertas se deriva UNA vez, con la
// polaridad fail-safe de cada canal, y las dos superficies leen esa.
//
// [T-2.144] `INCIDENT_ACTION_KINDS` es la SEGUNDA familia del mismo registro
// —ciclo de vida, dictamen, pase de lista, notificación— y `UNCLASSIFIED_VIEW`
// el fallback que dejó de ser verde. Salen por aquí por el mismo motivo que los
// canales: una sola fuente para el checklist de la consola y para la bitácora.
export {
  ACTION_STATE,
  ACTUATOR_CHANNELS,
  CHANNEL_LABEL,
  INCIDENT_ACTION_KINDS,
  UNCLASSIFIED_VIEW,
  channelEvidence,
  groupActions,
  sirenEvidence,
  type ActionStateView,
  type ActuatorChannelSpec,
  type ActuatorGroup,
  type ChannelEvidence,
  type IncidentActionSpec,
} from "@takab/sdk";
